"""TripFit live CBC API. Run with one uvicorn worker."""
import copy
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from starlette.concurrency import run_in_threadpool

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT.parent / ".env", override=False)

from solver.demo_builder import (DemoSolver, build_demo, label_for, mark_muted,
                                 mute_request, pareto_series, plan_json)
from solver.sample_seongsu import HIDDEN, PLACES, REQUEST
from solver.tripfit_solver import CATEGORY_KO, TAG_KO, Infeasible, diff_plans
from server.parsing import ParseInput, StrictModel, parse_messages

SOLVE_LOCK = threading.Lock()
_demo_cache = None


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


class PlanInput(StrictModel):
    muted: list[MutedItem] = Field(default_factory=list, max_length=24)
    tag_min: dict[str, Annotated[int, Field(ge=0, le=20)]] = Field(default_factory=dict, max_length=10)


class WhatIfInput(StrictModel):
    pick: Literal["mrt_leather_1600", "mrt_leather_1400"]


class ReplanInput(StrictModel):
    now_min: Annotated[int, Field(ge=REQUEST.start_min, le=REQUEST.deadline_min)]
    exclude: list[str] = Field(default_factory=list, max_length=20)
    keep: dict[str, Annotated[int, Field(ge=0, le=1440)]] = Field(default_factory=dict, max_length=20)


def infeasible_json(result, request, places):
    """Structure the engine's labels without changing its diagnostic search.

    Walking diagnostics round distances to 0.1 km. Use removal of the hard
    limit (the actual tested diagnostic change), not that rounded distance.
    """
    by_id = {p.id: p.name for p in places}
    by_id.update({p.group: p.name for p in places if p.group})
    options = {}
    for category, count in request.category_min.items():
        options[f"{CATEGORY_KO.get(category, category)} 최소 {count}곳 조건 해제"] = {
            "kind": "category_min", "key": category, "from": count, "to": 0}
    for tag, count in request.tag_min.items():
        options[f"{TAG_KO.get(tag, tag)} {count}곳 조건 해제"] = {
            "kind": "tag_min", "key": tag, "from": count, "to": 0}
    for pid, start in request.locks.items():
        options[f"'{by_id.get(pid, pid)}' 시간 고정 해제"] = {
            "kind": "locks", "key": pid, "from": start, "to": None}
    for pid in request.must_include:
        options[f"'{by_id.get(pid, pid)}' 필수 방문 해제"] = {
            "kind": "must_include", "key": pid, "from": True, "to": False}
    options["종료 시간 1시간 늦추기"] = {
        "kind": "deadline_min", "from": request.deadline_min, "to": request.deadline_min + 60}
    relaxations = []
    for label in result.relaxations:
        changes, labels = [], []
        for part in label.split(" + "):
            if part.startswith("도보 한도 "):
                changes.append({"kind": "max_walk_m", "from": request.max_walk_m, "to": None})
                labels.append("도보 한도 조건 해제")
            else:
                changes.append(options[part])
                labels.append(part)
        relaxations.append({"label": " + ".join(labels), "changes": changes})
    return {"infeasible": True, "relaxations": relaxations,
            "reason": result.reason, "live": True}


@app.get("/api/health")
def health():
    return {"ok": True, "solver": "CBC", "llm": {
        "axk2": bool(os.getenv("OBA_API_KEY")), "openai": bool(os.getenv("OPENAI_API_KEY"))}}


@app.get("/api/demo")
def demo(fresh: Annotated[int, Query(ge=0, le=1)] = 0):
    return cached_demo(bool(fresh))


@app.post("/api/plan")
def plan(body: PlanInput):
    muted = [(item.person, item.label) for item in body.muted]
    try:
        request = replace(mute_request(REQUEST, muted), tag_min=body.tag_min)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    places = PLACES + HIDDEN if body.tag_min.get("heritage", 0) else PLACES
    with SOLVE_LOCK:
        started = time.perf_counter()
        solver = DemoSolver(places)
        result = solver.solve_or_explain(request)
        if isinstance(result, Infeasible):
            return infeasible_json(result, request, places)
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
                           "solveMs": ms, "live": True}, muted)


@app.post("/api/what-if")
def what_if(body: WhatIfInput):
    with SOLVE_LOCK:
        solver = DemoSolver(PLACES)
        front, _ = pareto_series(solver)
        if not front:
            result = solver.solve_or_explain(REQUEST)
            if isinstance(result, Infeasible):
                return infeasible_json(result, REQUEST, PLACES)
            front = [result]
        base = min(front, key=lambda p: abs(p.satisfaction_pct["지민"] - p.satisfaction_pct["서연"]))
        started = time.perf_counter()
        result, diff = solver.what_if_add(REQUEST, body.pick, base)
        if isinstance(result, Infeasible):
            return infeasible_json(result, replace(REQUEST, must_include=[body.pick]), PLACES)
        return {"plan": plan_json(result, "w" if body.pick.endswith("1600") else "w14",
                                  round((time.perf_counter() - started) * 1000)), "diff": diff}


@app.post("/api/replan")
def replan(body: ReplanInput):
    known = {p.id for p in PLACES}
    if (set(body.exclude) | set(body.keep)) - known:
        raise HTTPException(status_code=422, detail="Unknown place id")
    request = replace(REQUEST, exclude=body.exclude)
    with SOLVE_LOCK:
        started = time.perf_counter()
        result = DemoSolver(PLACES).reoptimize(request, body.now_min, REQUEST.start, [], body.keep)
        if isinstance(result, Infeasible):
            return infeasible_json(result, replace(request, start_min=body.now_min, locks=body.keep), PLACES)
        return {"plan": plan_json(result, "r", round((time.perf_counter() - started) * 1000))}


@app.post("/api/parse")
async def parse(body: ParseInput):
    if len({m.name for m in body.messages}) != len(body.messages):
        raise HTTPException(status_code=422, detail="Names must be unique")
    return await parse_messages(body.messages)


# Last: API routes must win over the static mount.
app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
