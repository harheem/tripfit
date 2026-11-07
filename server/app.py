"""TripFit live CBC API. Run with one uvicorn worker."""
import copy
import json
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request as HTTPRequest
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from starlette.concurrency import run_in_threadpool

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT.parent / ".env", override=False)

from solver.demo_builder import (DemoSolver, build_demo, label_for, mark_muted,
                                 mute_request, pareto_series, plan_json, build_whatif,
                                 infeasible_json, apply_relaxation, MESSAGES)
from solver.sample_seongsu import HIDDEN, PLACES, REQUEST, MRT_SNAPSHOT, reload_mrt
from solver.tripfit_solver import CATEGORY_KO, TAG_KO, Infeasible, diff_plans
from solver.mrt_places import SNAPSHOT_PATH, read_snapshot
from scripts.fetch_mrt_snapshot import save_snapshot
from server.parsing import (ParseInput, TryInput, StrictModel, parse_messages,
                            request_from_constraints, messages_from_constraints)
from server.state import Session, SessionStore, TokenBuckets

SOLVE_LOCK = threading.Lock()
_demo_cache = None
SESSIONS = SessionStore()
RATE_LIMITER = TokenBuckets()


def cached_demo(fresh=False):
    global _demo_cache
    with SOLVE_LOCK:
        if fresh or _demo_cache is None:
            data = build_demo()
            _demo_cache = {**data, "live": True,
                           "computedAt": datetime.now(timezone.utc).isoformat()}
        return copy.deepcopy(_demo_cache)


@asynccontextmanager
async def lifespan(app):
    # One startup calculation warms CBC and fills the demo cache under the lock.
    await run_in_threadpool(cached_demo)
    yield


app = FastAPI(title="TripFit", lifespan=lifespan)


class MutedItem(StrictModel):
    person: str
    label: str


class SessionInput(StrictModel):
    sessionId: str | None = Field(default=None, min_length=1, max_length=100)


def session_context(session_id):
    session = SESSIONS.get(session_id) if session_id else None
    if session:
        return session, {}
    return Session(REQUEST, PLACES, MESSAGES), ({"sessionExpired": True} if session_id else {})


@app.middleware("http")
async def limit_parsing(http_request: HTTPRequest, call_next):
    if http_request.method == "POST" and http_request.url.path in ("/api/try", "/api/parse"):
        forwarded = http_request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        ip = forwarded or (http_request.client.host if http_request.client else "unknown")
        try:
            rate = max(1, int(os.getenv("TRY_RATE_PER_MIN", "6")))
        except ValueError:
            rate = 6
        if not RATE_LIMITER.allow(ip, rate):
            return JSONResponse(status_code=429, content={"error": "잠시 후 다시"},
                                headers={"Retry-After": str(max(1, (60 + rate - 1) // rate))})
    return await call_next(http_request)


class PlanInput(SessionInput):
    muted: list[MutedItem] = Field(default_factory=list, max_length=24)
    tag_min: dict[str, Annotated[int, Field(ge=0, le=20)]] = Field(default_factory=dict, max_length=10)


class WhatIfInput(SessionInput):
    pick: str = Field(min_length=1, max_length=100)
    relax: str | None = Field(default=None, min_length=1, max_length=300)


class ReplanInput(SessionInput):
    pick: str | None = Field(default=None, min_length=1, max_length=100)
    relax: str | None = Field(default=None, min_length=1, max_length=300)
    now_min: Annotated[int, Field(ge=REQUEST.start_min, le=REQUEST.deadline_min)]
    exclude: list[str] = Field(default_factory=list, max_length=20)
    keep: dict[str, Annotated[int, Field(ge=0, le=1440)]] = Field(default_factory=dict, max_length=20)


@app.get("/api/health")
def health():
    return {"ok": True, "solver": "CBC", "llm": {
        "axk2": bool(os.getenv("OBA_API_KEY")), "openai": bool(os.getenv("OPENAI_API_KEY"))}}


@app.get("/api/demo")
def demo(fresh: Annotated[int, Query(ge=0, le=1)] = 0):
    return cached_demo(bool(fresh))


@app.post("/api/plan")
def plan(body: PlanInput):
    session, extra = session_context(body.sessionId)
    muted = [(item.person, item.label) for item in body.muted]
    try:
        request = replace(mute_request(session.request, muted), tag_min=body.tag_min)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    with SOLVE_LOCK:
        places = session.places + HIDDEN if body.tag_min.get("heritage", 0) else session.places
        started = time.perf_counter()
        solver = DemoSolver(places)
        result = solver.solve_or_explain(request)
        if isinstance(result, Infeasible):
            return {**infeasible_json(result, request, places, session.messages), **extra}
        front, _ = pareto_series(solver, request)
        # Preserve a feasible itinerary if epsilon alternatives yield no incumbent.
        front = front or [result]
        ms = round((time.perf_counter() - started) * 1000)
        series = []
        for i, item in enumerate(front):
            item.label = label_for(item)
            series.append(plan_json(item, f"p{i}", ms))
        default_idx = min(range(len(front)), key=lambda i: abs(
            front[i].satisfaction_pct["지민"] - front[i].satisfaction_pct["서연"]))
        return mark_muted({"series": series, "defaultIdx": default_idx,
                           "diffs": [diff_plans(a, b, request.people) for a, b in zip(front, front[1:])],
                           "solveMs": ms, "live": True, **extra}, muted)


@app.post("/api/what-if")
def what_if(body: WhatIfInput):
    session, extra = session_context(body.sessionId)
    request, places, messages = session.request, session.places, session.messages
    with SOLVE_LOCK:
        if body.pick not in {p.id for p in places if p.category == "activity" and p.availability != "unavailable"}:
            raise HTTPException(status_code=422, detail="Unknown or unavailable experience")
        solver = DemoSolver(places)
        front, _ = pareto_series(solver, request)
        if not front:
            result = solver.solve_or_explain(request)
            if isinstance(result, Infeasible):
                return {**infeasible_json(result, request, places, messages), **extra}
            front = [result]
        base = min(front, key=lambda p: abs(p.satisfaction_pct["지민"] - p.satisfaction_pct["서연"]))
        result = build_whatif(solver, request, body.pick, base, messages)
        if body.relax:
            option = next((o for o in result.get("relaxations", []) if o["id"] == body.relax), None)
            if option is None:
                raise HTTPException(status_code=422, detail="Unknown relaxation for this experience")
            return {**extra, "pick": body.pick, "infeasible": False, "relaxationId": option["id"],
                    **{k: option[k] for k in ("plan", "diff", "replan")}}
        if result["infeasible"]:
            return {**extra, "pick": body.pick, "infeasible": True, "reason": result["reason"],
                    "recommended": result.get("recommended"),
                    "relaxations": [{k: v for k, v in o.items() if k not in ("plan", "diff", "replan")}
                                    for o in result["relaxations"]]}
        return {**result, **extra}


@app.post("/api/replan")
def replan(body: ReplanInput):
    session, extra = session_context(body.sessionId)
    request, places, messages = session.request, session.places, session.messages
    with SOLVE_LOCK:
        known = {p.id for p in places}
        if (set(body.exclude) | set(body.keep)) - known:
            raise HTTPException(status_code=422, detail="Unknown place id")
        solver = DemoSolver(places)
        if body.relax:
            if body.pick not in body.keep:
                raise HTTPException(status_code=422, detail="Concession needs the booked experience")
            base = solver.solve(request)
            whatif = build_whatif(solver, request, body.pick, base, messages)
            option = next((o for o in whatif.get("relaxations", []) if o["id"] == body.relax), None)
            if option is None:
                raise HTTPException(status_code=422, detail="Unknown relaxation for this experience")
            request = apply_relaxation(request, option)
        request = replace(request, exclude=body.exclude)
        started = time.perf_counter()
        result = solver.reoptimize(request, body.now_min, request.start, [], body.keep)
        if isinstance(result, Infeasible):
            return {**infeasible_json(result, replace(request, start_min=body.now_min, locks=body.keep), places, messages), **extra}
        return {**extra, "plan": plan_json(result, "r", round((time.perf_counter() - started) * 1000))}


@app.post("/api/parse")
async def parse(body: ParseInput):
    if len({m.name for m in body.messages}) != len(body.messages):
        raise HTTPException(status_code=422, detail="Names must be unique")
    return await parse_messages(body.messages)


def solve_try(people, parsed):
    constraints = parsed["constraints"]
    for person in constraints["people"]:
        if not person["prefs"]:
            return {"needsMore": True, "person": person["name"],
                    "hint": f"{person['name']}의 말에서 조건을 못 찾았어요. 예: '카페에서 쉬고 싶어'"}
    request = request_from_constraints(constraints)
    messages = messages_from_constraints(people, constraints)
    with SOLVE_LOCK:
        places = copy.deepcopy(PLACES)
        started = time.perf_counter()
        data = build_demo(request, places, HIDDEN, messages)
        solve_ms = round((time.perf_counter() - started) * 1000)
    if data.get("infeasible"):
        return data
    session_id = SESSIONS.put(Session(request, places, messages))
    return {**data, "sessionId": session_id, "live": True,
            "computedAt": datetime.now(timezone.utc).isoformat(),
            "source": {"provider": parsed["provider"], "model": parsed["model"],
                       "parseMs": parsed["ms"], "solveMs": solve_ms},
            "unmatched": {p["name"]: p.get("unmatched", []) for p in constraints["people"]}}


@app.post("/api/try")
async def try_demo(body: TryInput):
    if {p.name for p in body.people} != {"지민", "서연"}:
        raise HTTPException(status_code=422, detail="Both 지민 and 서연 are required")
    people = sorted(body.people, key=lambda p: ("지민", "서연").index(p.name))
    parsed = await parse_messages(people, demo_fallback=False, openai_only=True)
    return await run_in_threadpool(solve_try, people, parsed)


REFRESH_LOCK = threading.Lock()


def mrt_summary():
    with SOLVE_LOCK:
        return {"snapshot": copy.deepcopy(MRT_SNAPSHOT) or None,
                "isReal": bool(MRT_SNAPSHOT), "fetchedAt": MRT_SNAPSHOT.get("fetchedAt"),
                "date": MRT_SNAPSHOT.get("date"), "picked": copy.deepcopy(MRT_SNAPSHOT.get("picked", []))}


@app.get("/api/mrt")
def get_mrt():
    return mrt_summary()


def fetch_mrt_refresh():
    # A process deadline covers the entire refresh, not just an individual HTTP call.
    # The child only prints JSON, so a timeout can never overwrite a good snapshot.
    result = subprocess.run([sys.executable, str(ROOT / "scripts/fetch_mrt_snapshot.py"), "--stdout", "--refresh"],
                            cwd=ROOT, capture_output=True, text=True, timeout=10, check=True)
    return json.loads(result.stdout)


@app.post("/api/mrt/refresh")
def refresh_mrt():
    global _demo_cache
    if not REFRESH_LOCK.acquire(blocking=False):
        return {**mrt_summary(), "refreshed": False, "reason": "이미 갱신 중"}
    try:
        try:
            snapshot = fetch_mrt_refresh()
            with tempfile.TemporaryDirectory() as directory:
                staging = Path(directory) / "snapshot.json"
                save_snapshot(snapshot, staging)
                if read_snapshot(staging) is None:
                    raise ValueError("Invalid snapshot")
            with SOLVE_LOCK:
                save_snapshot(snapshot, SNAPSHOT_PATH)
                reload_mrt(SNAPSHOT_PATH)
                _demo_cache = None
            return {**mrt_summary(), "refreshed": True}
        except (subprocess.SubprocessError, OSError, ValueError, TypeError):
            return {**mrt_summary(), "refreshed": False,
                    "reason": "MCP 갱신 실패 또는 10초 초과: 기존 스냅숏 유지"}
    finally:
        REFRESH_LOCK.release()


# Last: API routes must win over the static mount.
from server.pay_router import router as pay_router  # SKT 트랙: 같이 결제 재조회

app.include_router(pay_router)
app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
