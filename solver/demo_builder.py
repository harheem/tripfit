"""Precompute every screen of the demo from the real solver -> web/demo_data.js.

The prototype reads `window.DEMO` (a .js file so it also opens from file:// offline).
On event day the same shapes come from the FastAPI endpoints instead.
"""

import math
import time
from dataclasses import replace

if __package__:
    from .demo_extras import HISTORY, attach_fills, place_facts, recommend
    from .sample_seongsu import HIDDEN, PLACES, REQUEST, MRT_META, MRT_SNAPSHOT, hm
    from .tripfit_solver import CATEGORY_KO, TAG_KO, Infeasible, Plan, TripFitSolver, diff_plans
else:
    from demo_extras import HISTORY, attach_fills, place_facts, recommend
    from sample_seongsu import HIDDEN, PLACES, REQUEST, MRT_META, MRT_SNAPSHOT, hm
    from tripfit_solver import CATEGORY_KO, TAG_KO, Infeasible, Plan, TripFitSolver, diff_plans


MESSAGES = {
    "지민": {
        "text": "전시는 꼭 보고 싶어! 골목도 여기저기 구경하고 싶어",
        "marks": [
            {"phrase": "전시는 꼭", "chip": "전시 1곳 이상", "kind": "hard"},
            {"phrase": "골목도 여기저기", "chip": "골목 2곳", "kind": "soft"},
        ],
    },
    "서연": {
        "text": "나 오늘 많이 못 걸어ㅠ 카페에서 좀 쉬고 싶어. 소품샵은 좋아",
        "marks": [
            {"phrase": "많이 못 걸어", "chip": "도보 3.5km 이하", "kind": "hard"},
            {"phrase": "많이 못 걸어", "chip": "덜 걷기", "kind": "soft"},
            {"phrase": "카페에서 좀 쉬고", "chip": "카페 1곳 이상", "kind": "hard"},
            {"phrase": "좀 쉬고", "chip": "느긋하게", "kind": "soft"},
            {"phrase": "소품샵", "chip": "소품샵", "kind": "soft"},
        ],
    },
}

# Sample values standing in for Seoul real-time city data (citydata) on event day.
CROWD = {"cafe_onion": "붐빔", "cafe_grandpa": "여유", "cafe_bluebottle": "여유", "exh_daelim": "보통"}



class DemoSolver(TripFitSolver):
    """CBC-only API wrapper; a fully conceded checklist has zero satisfaction."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.solver_name = "CBC"

    def _solve(self, req, label):
        plan, status = super()._solve(req, label)
        return attach_fills(plan, req), status

    @staticmethod
    def _checklist_expr(m, prefs, places, P, y, walk_m):
        # The engine divides by total weight. Its empty-checklist branch is 0.
        active = prefs if sum(it.weight for it in prefs) else []
        return TripFitSolver._checklist_expr(m, active, places, P, y, walk_m)


def mute_request(request, muted=()):
    muted = set(muted)
    known = {(person, it.label) for person, items in request.prefs.items() for it in items}
    if muted - known:
        raise ValueError("Unknown checklist item")
    return replace(request, prefs={person: [replace(it, weight=0) if (person, it.label) in muted
                                           else replace(it) for it in items]
                                   for person, items in request.prefs.items()})


def mark_muted(data, muted=()):
    """Add flags only to conceded items, preserving the baseline JSON shape."""
    muted = set(muted)
    if isinstance(data, dict):
        for key in ("prefs", "checklist"):
            for person, items in data.get(key, {}).items():
                for item in items:
                    if (person, item["label"]) in muted:
                        item.update(weight=0, muted=True)
        for value in data.values():
            mark_muted(value, muted)
    elif isinstance(data, list):
        for value in data:
            mark_muted(value, muted)
    return data


def stop_json(s):
    p = s.place
    return {
        "id": p.id, "name": p.name, "cat": p.category, "catKo": CATEGORY_KO.get(p.category, p.category),
        "arrive": s.arrive_min, "start": s.start_min, "end": s.end_min, "wait": s.wait_min,
        "walkM": s.walk_m_from_prev, "walkMin": s.walk_min_from_prev,
        "source": p.source, "availability": p.availability, "price": p.price,
        "url": p.url, "mrt": MRT_META.get(p.id),
        "fixed": p.fixed_start_min is not None, "crowd": CROWD.get(p.id), "tags": p.tags,
        "quality": p.quality, "q": p.quality_parts,
        "fills": getattr(s, "_fills", []),
    }


def plan_json(plan: Plan, pid, solve_ms=None):
    return {
        "id": pid, "label": plan.label, "stops": [stop_json(s) for s in plan.stops],
        "walkM": plan.total_walk_m, "walkMin": plan.total_walk_min, "finish": plan.finish_min,
        "sat": plan.satisfaction_pct, "solveMs": solve_ms, "checklist": plan.checklist,
    }


def pareto_series(solver, request=REQUEST):
    """Plans for the consensus slider, ordered from 지민-leaning to 서연-leaning."""
    seen, plans = set(), []
    t0 = time.time()
    solver.alternatives(request)
    ms = round((time.time() - t0) * 1000)  # one /plan call as the API would make it
    for floor in (0.5, 0.6, 0.75, 0.9):
        for plan in solver.alternatives(request, floor=floor):
            key = tuple(plan.ids())
            if key not in seen:
                seen.add(key)
                plans.append(plan)
    plans.sort(key=lambda p: p.satisfaction_pct["지민"] - p.satisfaction_pct["서연"], reverse=True)
    # keep the Pareto-efficient ones
    front = [p for p in plans if not any(
        q is not p and q.satisfaction_pct["지민"] >= p.satisfaction_pct["지민"]
        and q.satisfaction_pct["서연"] >= p.satisfaction_pct["서연"]
        and (q.satisfaction_pct["지민"], q.satisfaction_pct["서연"]) != (p.satisfaction_pct["지민"], p.satisfaction_pct["서연"])
        for q in plans)]
    # Equal displayed satisfaction is one slider choice; prefer less walking.
    unique = {}
    for plan in front:
        pair = tuple(round(plan.satisfaction_pct[person], 1) for person in request.people)
        if pair not in unique or plan.total_walk_m < unique[pair].total_walk_m:
            unique[pair] = plan
    return list(unique.values()), ms


def label_for(plan):
    j, s = plan.satisfaction_pct["지민"], plan.satisfaction_pct["서연"]
    if abs(j - s) <= 8:
        return "균형"
    return "지민 쪽" if j > s else "서연 쪽"


def infeasible_json(result, request, places, messages=MESSAGES):
    """Translate tested engine diagnostics; attribution comes from hard message marks."""
    by_id = {p.id: p.name for p in places}
    by_id.update({p.group: p.name for p in places if p.group})

    def owner_for(prefix):
        return next((person for person, msg in messages.items()
                     if any(m["kind"] == "hard" and m["chip"].startswith(prefix)
                            for m in msg["marks"])), None)

    options = {}
    for category, count in request.category_min.items():
        name = CATEGORY_KO.get(category, category)
        options[f"{name} 최소 {count}곳 조건 해제"] = (
            "category_min", owner_for(name), f"{name} {count}곳",
            {"kind": "category_min", "key": category, "from": count, "to": 0})
    for tag, count in request.tag_min.items():
        options[f"{TAG_KO.get(tag, tag)} {count}곳 조건 해제"] = (
            "tag_min", None, f"{TAG_KO.get(tag, tag)} {count}곳",
            {"kind": "tag_min", "key": tag, "from": count, "to": 0})
    for pid, start in request.locks.items():
        options[f"'{by_id.get(pid, pid)}' 시간 고정 해제"] = (
            "locks", None, "시간 고정", {"kind": "locks", "key": pid, "from": start, "to": None})
    for pid in request.must_include:
        options[f"'{by_id.get(pid, pid)}' 필수 방문 해제"] = (
            "must", None, by_id.get(pid, pid),
            {"kind": "must_include", "key": pid, "from": True, "to": False})
    options["종료 시간 1시간 늦추기"] = (
        "deadline", owner_for("종료"), "종료 시각 1시간",
        {"kind": "deadline_min", "from": request.deadline_min, "to": request.deadline_min + 60})
    relaxations = []
    for label in result.relaxations:
        parts = []
        for part in label.split(" + "):
            if part.startswith("도보 한도 "):
                parts.append(("walk", owner_for("도보"), "도보 한도",
                              {"kind": "max_walk_m", "from": request.max_walk_m, "to": None}))
            else:
                parts.append(options[part])
        owners = {p[1] for p in parts}
        changes = [p[3] for p in parts]
        rid = "+".join(c["kind"] + (":" + c["key"] if "key" in c else "") for c in changes)
        owner = next(iter(owners)) if len(owners) == 1 else None
        text = " + ".join(p[2] for p in parts)
        relaxations.append({"id": rid, "label": f"{owner}의 '{text}'을 양보" if owner else f"{text} 양보",
                            "owner": owner, "kind": parts[0][0], "changes": changes})
    return {"infeasible": True, "relaxations": relaxations, "reason": result.reason}


def apply_relaxation(request, relaxation):
    """Apply only server-generated changes, without mutating the original request."""
    for change in relaxation["changes"]:
        kind, key, value = change["kind"], change.get("key"), change["to"]
        if kind in ("category_min", "tag_min", "locks"):
            values = dict(getattr(request, kind))
            if value is None or value == 0:
                values.pop(key, None)
            else:
                values[key] = value
            request = replace(request, **{kind: values})
        elif kind == "must_include":
            request = replace(request, must_include=[p for p in request.must_include if p != key])
        else:
            request = replace(request, **{kind: value})
    return request


def replan_for(solver, request, pick, plan):
    """Try flexible stops in itinerary order, with cafes first; keep the booking."""
    activity = next(p for p in solver.places if p.id == pick)
    now = request.start_min + 5
    for stop in sorted((s for s in plan["stops"] if not s["fixed"]), key=lambda s: s["cat"] != "cafe"):
        started = time.perf_counter()
        result = solver.reoptimize(replace(request, exclude=[*request.exclude, stop["id"]]),
                                   now, request.start, [], {pick: activity.fixed_start_min})
        if not isinstance(result, Infeasible):
            return {"now": now, "crowded": stop["id"],
                    "reason": f"{stop['name']} 지금 붐빔(샘플)", "done": [], "keep": pick,
                    "plan": plan_json(result, "r", round((time.perf_counter() - started) * 1000))}
    return None


def build_whatif(solver, request, pick, base, messages=MESSAGES):
    started = time.perf_counter()
    result, diff = solver.what_if_add(request, pick, base)
    required = replace(request, must_include=[*request.must_include, pick])
    payload = {"pick": pick, "product": next(p.group for p in solver.places if p.id == pick)}
    if not isinstance(result, Infeasible):
        plan = plan_json(result, "w", round((time.perf_counter() - started) * 1000))
        return {**payload, "infeasible": False, "plan": plan, "diff": diff,
                "replan": replan_for(solver, required, pick, plan)}
    diagnostic = infeasible_json(result, required, solver.places, messages)
    options = []
    activity = next(p for p in solver.places if p.id == pick)
    for option in diagnostic["relaxations"]:
        # Adding the experience is the purpose: never offer removal of that commitment.
        if any(c["kind"] == "must_include" and c["key"] in (pick, activity.group)
               for c in option["changes"]):
            continue
        relaxed = apply_relaxation(required, option)
        started = time.perf_counter()
        plan = solver.solve(relaxed, label="양보 후")
        if plan is None:
            continue
        saved = plan_json(plan, "w", round((time.perf_counter() - started) * 1000))
        options.append({**option, "plan": saved, "diff": diff_plans(base, plan, request.people),
                        "replan": replan_for(solver, relaxed, pick, saved)})
    recommended = recommend(options, request.people)
    default = next((o for o in options if o["id"] == recommended["id"]), None) if recommended else None
    chosen = ({"relaxationId": default["id"], **{k: default[k] for k in ("plan", "diff", "replan")}}
              if default else None)
    return {**payload, **diagnostic, "relaxations": options, "chosen": chosen, "recommended": recommended}


def build_demo(request=REQUEST, places=PLACES, hidden=HIDDEN, messages=MESSAGES, muted=()):
    """Compute the offline demo payload. Callers must serialize native solver calls."""
    request = mute_request(request, muted)
    solver = DemoSolver(places)
    n = len(places)
    orderings = sum(math.perm(n, k) for k in range(0, 7))

    front, ms = pareto_series(solver, request)
    if not front:
        result = solver.solve_or_explain(request)
        if isinstance(result, Infeasible):
            return {"infeasible": True,
                    "explanation": infeasible_json(result, request, places, messages)}
        front = [result]
    series = []
    for i, plan in enumerate(front):
        plan.label = label_for(plan)
        series.append(plan_json(plan, f"p{i}", ms))
    default_idx = min(range(len(front)), key=lambda i: abs(front[i].satisfaction_pct["지민"] - front[i].satisfaction_pct["서연"]))
    diffs = [diff_plans(front[i], front[i + 1], request.people) for i in range(len(front) - 1)]

    base = front[default_idx]
    # Keep time-window-compatible starts even when they need a hard concession.
    choices = []
    for activity in sorted((p for p in places if p.category == "activity" and
                            p.fixed_start_min is not None and p.availability != "unavailable"),
                           key=lambda p: p.fixed_start_min, reverse=True):
        if not request.start_min <= activity.fixed_start_min <= request.deadline_min - activity.duration_min:
            continue
        choices.append(build_whatif(solver, request, activity.id, base, messages))
        if len(choices) == 2:
            break
    primary = choices[0] if choices else {"pick": None, "product": None, "infeasible": False,
               "plan": plan_json(base, "w"), "diff": diff_plans(base, base, request.people)}
    selected = primary.get("chosen") if primary["infeasible"] else primary
    replan_data = selected.get("replan") if selected else None

    # "숨은 한 곳 +1": heritage spots join the candidate set and at least one must be visited.
    # Same balanced objective and the same %-scale as the base plan, so the numbers compare.
    scale = ({p: 1.0 for p in request.people} if request.prefs else
             {p: base.satisfaction[p] / base.satisfaction_pct[p] * 100 for p in request.people})
    t0 = time.time()
    hidden_plan = DemoSolver(places + hidden).solve(
        replace(request, tag_min={"heritage": 1}, weights={q: 0.01 for q in request.people},
                fairness_weight=100.0, sat_scale=scale), label="숨은 한 곳")
    hidden_ms = round((time.time() - t0) * 1000)
    if hidden_plan is not None and not request.prefs:
        hidden_plan.satisfaction_pct = {p: round(100 * hidden_plan.satisfaction[p] / scale[p], 1) for p in request.people}
    heritage = [p for p in places + hidden if "heritage" in p.tags]

    t0 = time.time()
    conflict = solver.solve_or_explain(replace(request, max_walk_m=1500))
    conflict_ms = round((time.time() - t0) * 1000)
    relax = conflict.relaxations if isinstance(conflict, Infeasible) else []

    place_data = [{
        "id": p.id, "name": p.name, "lat": p.lat, "lng": p.lng, "cat": p.category,
        "catKo": CATEGORY_KO.get(p.category, p.category), "source": p.source,
        "group": p.group, "fixedStart": p.fixed_start_min, "price": p.price,
        "availability": p.availability, "duration": p.duration_min, "crowd": CROWD.get(p.id),
        "tags": p.tags, "story": p.story, "credit": p.credit, "quality": p.quality, "q": p.quality_parts,
        "hidden": p in hidden, "url": p.url, "mrt": MRT_META.get(p.id),
        "facts": place_facts(p),
    } for p in places + hidden]

    prefs = {person: [{"label": it.label, "kind": it.kind, "weight": it.weight, "quote": it.quote,
                       "full": it.full, "zero": it.zero, "match": it.match} for it in items] for person, items in request.prefs.items()}
    data = {
        "history": [dict(row) for row in HISTORY],
        "prefs": prefs,
        "people": [
            {"name": "지민", "color": "#F2643D", "initial": "지", **messages["지민"]},
            {"name": "서연", "color": "#2E8FD8", "initial": "서", **messages["서연"]},
        ],
        "window": {"start": request.start_min, "end": request.deadline_min},
        "start": {"name": "성수역", "lat": request.start[0], "lng": request.start[1]},
        "end": {"name": "서울숲역", "lat": request.end[0], "lng": request.end[1]},
        "places": place_data,
        "sources": {"tmap": sum(p.source == "tmap" for p in places),
                    "mrt": len({p.group for p in places if p.source == "mrt"}),
                    "pairs": (n + 2) * (n + 1), "orderings": orderings},
        "series": series, "defaultIdx": default_idx, "diffs": diffs,
        "mrt": dict(MRT_SNAPSHOT),
        "whatif": {**primary, "choices": choices,
                   "alt": choices[1] if len(choices) > 1 else None},
        "replan": replan_data,
        "hidden": {"tag": "heritage", "label": "숨은 한 곳 +1", "source": "서울미래유산",
                   "candidates": [p.id for p in heritage],
                   "plan": plan_json(hidden_plan, "h", hidden_ms) if hidden_plan else None,
                   "diff": diff_plans(base, hidden_plan, request.people) if hidden_plan else None},
        "conflict": {"limitM": 1500, "relaxations": relax, "ms": conflict_ms},
        "pay": {"item": MRT_META.get(primary["pick"], {}).get("name", "체험 없음"),
                "price": next((p.price for p in places if p.id == primary["pick"]), 0), "people": 2},
    }
    return mark_muted(data, muted)
