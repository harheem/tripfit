"""Precompute every screen of the demo from the real solver -> web/demo_data.js.

The prototype reads `window.DEMO` (a .js file so it also opens from file:// offline).
On event day the same shapes come from the FastAPI endpoints instead.
"""

import math
import time
from dataclasses import replace

if __package__:
    from .sample_seongsu import HIDDEN, PLACES, REQUEST, hm
    from .tripfit_solver import CATEGORY_KO, Infeasible, Plan, TripFitSolver, diff_plans
else:
    from sample_seongsu import HIDDEN, PLACES, REQUEST, hm
    from tripfit_solver import CATEGORY_KO, Infeasible, Plan, TripFitSolver, diff_plans


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
        "fixed": p.fixed_start_min is not None, "crowd": CROWD.get(p.id), "tags": p.tags,
        "quality": p.quality, "q": p.quality_parts,
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
    return front, ms


def label_for(plan):
    j, s = plan.satisfaction_pct["지민"], plan.satisfaction_pct["서연"]
    if abs(j - s) <= 8:
        return "균형"
    return "지민 쪽" if j > s else "서연 쪽"


def build_demo(request=REQUEST, places=PLACES, hidden=HIDDEN, messages=MESSAGES, muted=()):
    """Compute the offline demo payload. Callers must serialize native solver calls."""
    request = mute_request(request, muted)
    solver = DemoSolver(places)
    n = len(places)
    orderings = sum(math.perm(n, k) for k in range(0, 7))

    front, ms = pareto_series(solver, request)
    series = []
    for i, plan in enumerate(front):
        plan.label = label_for(plan)
        series.append(plan_json(plan, f"p{i}", ms))
    default_idx = min(range(len(front)), key=lambda i: abs(front[i].satisfaction_pct["지민"] - front[i].satisfaction_pct["서연"]))
    diffs = [diff_plans(front[i], front[i + 1], request.people) for i in range(len(front) - 1)]

    base = front[default_idx]
    t0 = time.time()
    whatif, wdiff = solver.what_if_add(request, "mrt_leather_1600", base)
    whatif_ms = round((time.time() - t0) * 1000)
    assert not isinstance(whatif, Infeasible)
    if not request.prefs:
        whatif.satisfaction_pct = {p: round(100 * whatif.satisfaction[p] / max(1e-6, base.satisfaction[p] / base.satisfaction_pct[p] * 100), 1)
                               for p in request.people}

    # the other bookable slot, so the time picker on the what-if sheet is real both ways
    alt, altdiff = solver.what_if_add(request, "mrt_leather_1400", base)
    assert not isinstance(alt, Infeasible)
    if not request.prefs:
        alt.satisfaction_pct = {p: round(100 * alt.satisfaction[p] / max(1e-6, base.satisfaction[p] / base.satisfaction_pct[p] * 100), 1)
                            for p in request.people}

    # live change: the first stop is crowded right now (Seoul real-time city data)
    crowded = whatif.stops[0].place
    now = request.start_min + 5
    t0 = time.time()
    replan = solver.reoptimize(replace(request, must_include=["mrt_leather_1600"], exclude=[crowded.id]), now,
                               request.start, [], {"mrt_leather_1600": hm("16:00")})
    replan_ms = round((time.time() - t0) * 1000)
    assert not isinstance(replan, Infeasible)

    # "숨은 한 곳 +1": heritage spots join the candidate set and at least one must be visited.
    # Same balanced objective and the same %-scale as the base plan, so the numbers compare.
    scale = ({p: 1.0 for p in request.people} if request.prefs else
             {p: base.satisfaction[p] / base.satisfaction_pct[p] * 100 for p in request.people})
    t0 = time.time()
    hidden_plan = DemoSolver(places + hidden).solve(
        replace(request, tag_min={"heritage": 1}, weights={q: 0.01 for q in request.people},
                fairness_weight=100.0, sat_scale=scale), label="숨은 한 곳")
    hidden_ms = round((time.time() - t0) * 1000)
    assert hidden_plan is not None
    if not request.prefs:
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
        "hidden": p in hidden,
    } for p in places + hidden]

    prefs = {person: [{"label": it.label, "kind": it.kind, "weight": it.weight, "quote": it.quote,
                       "full": it.full, "zero": it.zero, "match": it.match} for it in items] for person, items in request.prefs.items()}
    data = {
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
        "whatif": {"product": "mrt_leather", "pick": "mrt_leather_1600",
                   "plan": plan_json(whatif, "w", whatif_ms), "diff": wdiff,
                   "alt": {"pick": "mrt_leather_1400", "plan": plan_json(alt, "w14"), "diff": altdiff}},
        "replan": {"now": now, "crowded": crowded.id,
                   "reason": f"{crowded.name} 지금 붐빔 · 웨이팅 약 40분",
                   "done": [], "keep": "mrt_leather_1600",
                   "plan": plan_json(replan, "r", replan_ms)},
        "hidden": {"tag": "heritage", "label": "숨은 한 곳 +1", "source": "서울미래유산",
                   "candidates": [p.id for p in heritage], "plan": plan_json(hidden_plan, "h", hidden_ms),
                   "diff": diff_plans(base, hidden_plan, request.people)},
        "conflict": {"limitM": 1500, "relaxations": relax, "ms": conflict_ms},
        "pay": {"item": "가죽공방 원데이클래스", "price": 55000, "people": 2},
    }
    return mark_muted(data, muted)
