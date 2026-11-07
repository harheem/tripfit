# Source: TripFit repository, solver/tripfit_solver.py (TripFit team).
# Original additions: per-person budget and restaurant start deadline.
# Hapui 추가: category_max upper bound (restaurant count).
"""TripFit half-day itinerary solver (Python-MIP).

Orienteering problem with time windows, adapted from planner-algo's
`Optimizer.optimize_anchor_based_itinerary`:
  - arc variables x[i][j] + flow conservation      (kept)
  - anchor POIs must be visited                     (kept -> must_include / locks)
  - same POI at most once                           (kept -> option `group`)
  - slot-based "possibility" ordering               (replaced by start-time variables,
                                                     which also eliminate subtours)
New for TripFit:
  - per-companion preference scores + max-min fairness term
  - hard walking budget, category minimums (e.g. "at least one cafe")
  - fixed start-time options for bookable products (MyRealTrip getTnaOptions)
  - locks for re-optimization ("keep what I already booked")
  - infeasibility diagnosis: which single hard constraint to relax
"""

import glob
import math
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple


def _configure_highs():
    # Optional backend (TRIPFIT_SOLVER=HIGHS). Python-MIP 1.16rc0 + highspy 1.15
    # segfaulted on this model on 2026-11-06, so CBC stays the default.
    if "PMIP_HIGHS_LIBRARY" in os.environ:
        return
    try:
        import highspy
    except ImportError:
        return
    libs = sorted(glob.glob(os.path.join(os.path.dirname(highspy.__file__), "libhighs*")))
    if libs:
        os.environ["PMIP_HIGHS_LIBRARY"] = libs[0]


_configure_highs()

from mip import BINARY, CONTINUOUS, Model, OptimizationStatus, maximize, xsum  # noqa: E402


def _default_solver() -> str:
    # Apple Silicon: needs mip==1.16rc0 (arm64 CBC) and `brew install gcc` (libgfortran).
    return os.environ.get("TRIPFIT_SOLVER", "CBC")


@contextmanager
def _quiet_native_stdout():
    # CBC's feasibility pump prints even with verbose=0; silence the C-level fd.
    import ctypes

    libc = ctypes.CDLL(None)
    sys.stdout.flush()
    saved = os.dup(1)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, 1)
        yield
    finally:
        libc.fflush(None)
        os.dup2(saved, 1)
        os.close(devnull)
        os.close(saved)


CATEGORY_KO = {
    "exhibit": "전시", "cafe": "카페", "alley": "골목", "food": "식당",
    "shop": "소품샵", "activity": "체험", "park": "공원", "heritage": "미래유산",
}
TAG_KO = {"heritage": "숨은 한 곳(서울미래유산)"}


# ---------------------------------------------------------------- data model

@dataclass
class Place:
    id: str
    name: str
    lat: float
    lng: float
    category: str  # exhibit | cafe | alley | food | shop | activity | park
    duration_min: int
    open_min: int = 0  # minutes from 00:00
    close_min: int = 24 * 60
    scores: Dict[str, float] = field(default_factory=dict)  # person -> 0..10
    group: Optional[str] = None  # options of one product share a group (<= 1 chosen)
    fixed_start_min: Optional[int] = None  # bookable time slot
    price: int = 0
    source: str = "sample"  # tmap | mrt | sample
    availability: str = "n/a"  # confirmed | unverified | n/a
    url: Optional[str] = None
    tags: List[str] = field(default_factory=list)  # e.g. "heritage" (Seoul Future Heritage)
    story: Optional[str] = None  # short copy for the story card
    credit: Optional[str] = None  # data source line shown with the story
    quality: float = 0.5  # place score Q in 0..1, independent of who visits (see place_quality)
    quality_parts: Dict[str, float] = field(default_factory=dict)


INTENSITY = {"strong": 1.0, "normal": 0.7, "weak": 0.4}  # the LLM picks the label, never the number


@dataclass
class Pref:
    """One thing a person said, as a checklist item fulfilled 0..1.

    visit: Σ affinity of visited places / `full` (how many the words asked for, default 1), capped at 1
    dwell: minutes spent at matching places / `full`
    walk:  1 at <= `full` metres, 0 at `zero` metres (linear)
    stops: 1 at <= `full` stops, 0 at `zero` stops (linear)
    """
    label: str
    kind: str
    weight: float = INTENSITY["normal"]
    quote: str = ""
    match: Dict[str, float] = field(default_factory=dict)
    full: float = 0.0
    zero: float = 0.0


def affinity(pref: "Pref", place: "Place") -> float:
    return max((pref.match.get(k, 0.0) for k in (place.category, *place.tags)), default=0.0)


def place_quality(branches: int = 1, rating: Optional[float] = None, reviews: int = 0,
                  crowd: Optional[int] = None, heritage: bool = False, prior: float = 4.5, c: int = 20):
    """Place score Q = 0.4 uniqueness + 0.3 reputation + 0.3 timing, each 0..1.

    uniqueness: 1 branch -> 1, 2-5 -> 0.5, 6+ (chain) -> 0; heritage spots count as unique
    reputation: rating shrunk toward `prior` by review count (Bayesian average); no rating -> prior
    timing:     forecast crowd level 1..4 at the planned hour -> 1 .. 0.5; unknown -> 1
    """
    u = 1.0 if heritage or branches <= 1 else 0.5 if branches <= 5 else 0.0
    r = ((reviews * rating + c * prior) / (reviews + c)) if rating is not None else prior
    r = max(0.0, min(1.0, (r - 3.0) / 2.0))
    t = 1.0 if crowd is None else 1.0 - 0.5 * (crowd - 1) / 3.0
    parts = {"uniqueness": round(u, 2), "reputation": round(r, 2), "timing": round(t, 2)}
    return round(0.4 * u + 0.3 * r + 0.3 * t, 3), parts


@dataclass
class Request:
    people: List[str]
    start: Tuple[float, float]
    end: Tuple[float, float]
    start_min: int
    deadline_min: int
    weights: Dict[str, float] = field(default_factory=dict)  # person -> weight
    must_include: List[str] = field(default_factory=list)  # place ids (or group ids)
    category_min: Dict[str, int] = field(default_factory=dict)  # e.g. {"cafe": 1}
    category_max: Dict[str, int] = field(default_factory=dict)  # Hapui 추가
    tag_min: Dict[str, int] = field(default_factory=dict)  # e.g. {"heritage": 1}: "숨은 한 곳 +1"
    budget: Optional[int] = None
    eat_by: Optional[int] = None
    max_walk_m: Optional[float] = None
    locks: Dict[str, int] = field(default_factory=dict)  # place id -> fixed start min
    exclude: List[str] = field(default_factory=list)
    walk_aversion: Dict[str, float] = field(default_factory=dict)  # person -> score lost per km
    stop_aversion: Dict[str, float] = field(default_factory=dict)  # person -> score lost per stop (pace)
    fairness_weight: float = 1.0
    min_satisfaction: Dict[str, float] = field(default_factory=dict)  # person -> floor (raw)
    sat_scale: Dict[str, float] = field(default_factory=dict)  # person -> divisor for fairness
    walk_penalty_per_km: float = 1.0
    prefs: Dict[str, List[Pref]] = field(default_factory=dict)  # checklist mode when set
    quality_weight: float = 0.0  # objective weight of Σ place quality (tie-break among equal checklists)


@dataclass
class Stop:
    place: Place
    arrive_min: int
    start_min: int
    end_min: int
    walk_m_from_prev: float
    walk_min_from_prev: float

    @property
    def wait_min(self) -> int:
        return self.start_min - self.arrive_min


@dataclass
class Plan:
    label: str
    stops: List[Stop]
    total_walk_m: float
    total_walk_min: float
    finish_min: int
    satisfaction: Dict[str, float]  # person -> raw score sum
    satisfaction_pct: Dict[str, float] = field(default_factory=dict)
    checklist: Dict[str, List[Dict]] = field(default_factory=dict)  # person -> [{label, weight, fulfilled}]

    def ids(self) -> List[str]:
        return [s.place.id for s in self.stops]


@dataclass
class Infeasible:
    reason: str
    relaxations: List[str]  # human-readable single relaxations that restore feasibility


# ---------------------------------------------------------------- travel matrix

WALK_M_PER_MIN = 70.0  # ~4.2 km/h
DETOUR_FACTOR = 1.3


def haversine_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    )
    return 2 * 6371000 * math.asin(math.sqrt(h))


def estimate_walk_matrix(points: List[Tuple[float, float]]):
    """Fallback when TMAP pedestrian routes are missing (same idea as planner-algo's
    euclidean fill-in for missing transport rows). Returns (meters, minutes)."""
    n = len(points)
    dist = [[0.0] * n for _ in range(n)]
    mins = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                dist[i][j] = haversine_m(points[i], points[j]) * DETOUR_FACTOR
                mins[i][j] = dist[i][j] / WALK_M_PER_MIN
    return dist, mins


def checklist_of(prefs: List[Pref], stops: List["Stop"], walk_m: float) -> List[Dict]:
    """How much of each thing a person said this route keeps (0..1), for display."""
    out = []
    for it in prefs:
        if it.kind == "visit":
            f = sum(affinity(it, s.place) for s in stops) / (it.full or 1.0)
        elif it.kind == "dwell":
            f = sum(affinity(it, s.place) * (s.end_min - s.start_min) for s in stops) / it.full
        elif it.kind == "walk":
            f = (it.zero - walk_m) / (it.zero - it.full)
        else:
            f = (it.zero - len(stops)) / (it.zero - it.full)
        out.append({"label": it.label, "weight": it.weight, "quote": it.quote,
                    "fulfilled": round(max(0.0, min(1.0, f)), 2)})
    return out


def checklist_pct(items: List[Dict]) -> float:
    w = sum(i["weight"] for i in items) or 1.0
    return round(100 * sum(i["weight"] * i["fulfilled"] for i in items) / w, 1)


# ---------------------------------------------------------------- solver

class TripFitSolver:
    def __init__(self, places: List[Place], walk_m=None, walk_min=None, time_limit_s=5, mip_gap=0.01):
        """walk_m / walk_min: (n+2)x(n+2) matrices indexed [start, *places, end].
        If omitted they are estimated from coordinates per request."""
        self.places = places
        self._walk_m = walk_m
        self._walk_min = walk_min
        self.time_limit_s = time_limit_s
        self.mip_gap = mip_gap
        self.solver_name = _default_solver()

    # -- public API ---------------------------------------------------------

    def solve(self, req: Request, label: str = "plan") -> Optional[Plan]:
        plan, _ = self._solve(req, label)
        return plan

    def solve_or_explain(self, req: Request, label: str = "plan"):
        plan, status = self._solve(req, label)
        if plan is not None:
            return plan
        return self.diagnose(req, status)

    def alternatives(self, req: Request, floor: float = 0.6) -> List[Plan]:
        """Pareto alternatives for the group.

        "<p> 우선": maximize p's satisfaction while every other companion keeps
        at least `floor` of their own solo-optimal satisfaction (epsilon-constraint).
        "균형": maximize the minimum normalized satisfaction (max-min fairness).
        Satisfaction is reported as % of each person's solo-optimal plan."""
        ideal = {}
        for p in req.people:
            solo = self.solve(replace(req, weights={p: 1.0}, fairness_weight=0.0))
            ideal[p] = solo.satisfaction[p] if solo else 0.0
        # checklist satisfaction is already an absolute 0..100%; the old score sums are % of solo best
        scale = {p: 100.0 for p in req.people} if req.prefs else {p: max(abs(v), 1e-6) for p, v in ideal.items()}

        plans = []
        for p in req.people:
            mins = {q: floor * ideal[q] for q in req.people if q != p and ideal[q] > 0}
            plan = self.solve(
                replace(req, weights={p: 1.0}, fairness_weight=0.0, min_satisfaction=mins),
                label=f"{p} 우선",
            )
            if plan:
                plans.append(plan)
        balanced = self.solve(
            replace(req, weights={q: 0.01 for q in req.people}, fairness_weight=100.0,
                    sat_scale={q: v / 100.0 for q, v in scale.items()} if req.prefs else scale),
            label="균형",
        )
        if balanced:
            plans.append(balanced)

        unique: List[Plan] = []
        for plan in plans:
            for p in req.people:
                plan.satisfaction_pct[p] = round(100 * plan.satisfaction[p] / scale[p], 1)
            if all(plan.ids() != u.ids() for u in unique):
                unique.append(plan)
        return unique

    def what_if_add(self, req: Request, place_id: str, base: Plan):
        """Force a new place in, re-solve, and report what had to give."""
        new_req = replace(req, must_include=list(req.must_include) + [place_id])
        result = self.solve_or_explain(new_req, label=f"+{place_id}")
        if isinstance(result, Infeasible):
            return result, None
        return result, diff_plans(base, result, req.people)

    def reoptimize(
        self,
        req: Request,
        now_min: int,
        here: Tuple[float, float],
        done_ids: List[str],
        keep: Dict[str, int],
    ):
        """Re-plan mid-trip from the current position, keeping commitments (`keep`)."""
        done_groups = {self._group_of(i) for i in done_ids}
        new_req = replace(
            req,
            start=here,
            start_min=now_min,
            exclude=list(req.exclude) + [p.id for p in self.places if self._group_of(p.id) in done_groups],
            must_include=[m for m in req.must_include if m not in done_ids and m not in done_groups],
            category_min=self._remaining_category_min(req, done_ids),
            tag_min={t: n - sum(1 for p in self.places if p.id in done_ids and t in p.tags)
                     for t, n in req.tag_min.items()},
            max_walk_m=req.max_walk_m,
            locks={**req.locks, **keep},
        )
        return self.solve_or_explain(new_req, label="재계산")

    def diagnose(self, req: Request, status="INFEASIBLE") -> Infeasible:
        """Find the smallest set of hard constraints to give up (1, then 2)."""
        options = []
        if req.max_walk_m is not None:
            options.append(("walk", lambda r: replace(r, max_walk_m=None)))
        for mid in req.must_include:
            options.append((f"'{self._name(mid)}' 필수 방문 해제",
                            lambda r, mid=mid: replace(r, must_include=[x for x in r.must_include if x != mid])))
        for cat, n in req.category_min.items():
            options.append((f"{CATEGORY_KO.get(cat, cat)} 최소 {n}곳 조건 해제",
                            lambda r, cat=cat: replace(r, category_min={c: v for c, v in r.category_min.items() if c != cat})))
        for tag, n in req.tag_min.items():
            options.append((f"{TAG_KO.get(tag, tag)} {n}곳 조건 해제",
                            lambda r, tag=tag: replace(r, tag_min={t: v for t, v in r.tag_min.items() if t != tag})))
        for pid in req.locks:
            options.append((f"'{self._name(pid)}' 시간 고정 해제",
                            lambda r, pid=pid: replace(r, locks={k: v for k, v in r.locks.items() if k != pid})))
        options.append(("종료 시간 1시간 늦추기", lambda r: replace(r, deadline_min=r.deadline_min + 60)))

        def describe(labels, plan):
            out = []
            for label in labels:
                if label == "walk":
                    label = f"도보 한도 {req.max_walk_m / 1000:.1f}km → {plan.total_walk_m / 1000:.1f}km로 늘리기"
                out.append(label)
            return " + ".join(out)

        relaxations = []
        for label, fn in options:
            plan = self.solve(fn(req))
            if plan:
                relaxations.append(describe([label], plan))
        if not relaxations:
            for a in range(len(options)):
                for b in range(a + 1, len(options)):
                    plan = self.solve(options[b][1](options[a][1](req)))
                    if plan:
                        relaxations.append(describe([options[a][0], options[b][0]], plan))
        return Infeasible(reason=str(status), relaxations=relaxations)

    # -- model --------------------------------------------------------------

    def _solve(self, req: Request, label: str):
        places = [p for p in self.places if p.id not in req.exclude]
        n = len(places)
        S, E = 0, n + 1
        V = range(n + 2)
        P = range(1, n + 1)
        idx = {p.id: k + 1 for k, p in enumerate(places)}

        dist, tmin = self._matrices(req, places)
        dur = [0] + [p.duration_min for p in places] + [0]
        T0, D = req.start_min, req.deadline_min

        # earliest / latest start per node; these bound t directly and prune arcs,
        # which keeps the MTZ big-Ms small (CBC stalls on this model otherwise)
        lo, hi = [float(T0)] * (n + 2), [float(T0)] * (n + 2)
        lo[E], hi[E] = T0 + tmin[S][E], float(D)
        for k in P:
            p = places[k - 1]
            lo[k] = max(T0 + tmin[S][k], p.open_min)
            hi[k] = min(p.close_min - p.duration_min, D - p.duration_min - tmin[k][E])
            if p.fixed_start_min is not None:
                lo[k], hi[k] = max(lo[k], p.fixed_start_min), min(hi[k], p.fixed_start_min)
            if p.id in req.locks:
                lo[k], hi[k] = max(lo[k], req.locks[p.id]), min(hi[k], req.locks[p.id])
        possible = [lo[k] <= hi[k] + 1e-6 for k in V]

        m = Model(sense="MAX", solver_name=self.solver_name)
        m.verbose = 0
        m.max_seconds = self.time_limit_s
        m.max_mip_gap = self.mip_gap

        arcs = [
            (i, j) for i in V for j in V
            if i != j and i != E and j != S and possible[i] and possible[j]
            and lo[i] + dur[i] + tmin[i][j] <= hi[j] + 1e-6
        ]
        x = {(i, j): m.add_var(var_type=BINARY) for (i, j) in arcs}
        y = [m.add_var(var_type=BINARY) for _ in V]
        t = [
            m.add_var(var_type=CONTINUOUS, lb=lo[k], ub=hi[k]) if possible[k]
            else m.add_var(var_type=CONTINUOUS, lb=T0, ub=D)
            for k in V
        ]
        for k in P:
            if not possible[k]:
                m += y[k] == 0
        for (i, j) in arcs:
            if i < j and (j, i) in x:
                m += x[i, j] + x[j, i] <= 1

        # flow: leave start once, enter end once, visited nodes in == out == y
        m += xsum(x[S, j] for j in V if (S, j) in x) == 1
        m += xsum(x[i, E] for i in V if (i, E) in x) == 1
        m += y[S] == 1
        m += y[E] == 1
        for k in P:
            m += xsum(x[i, k] for i in V if (i, k) in x) == y[k]
            m += xsum(x[k, j] for j in V if (k, j) in x) == y[k]

        # time propagation (also eliminates subtours)
        # opening hours, fixed slots and the deadline live in the bounds of t
        for (i, j), var in x.items():
            big_m = hi[i] + dur[i] + tmin[i][j] - lo[j]
            if big_m > 0:
                m += t[j] >= t[i] + dur[i] + tmin[i][j] - big_m * (1 - var)

        # valid cuts that make infeasibility provable quickly
        m += xsum((dur[i] + tmin[i][j]) * var for (i, j), var in x.items()) <= D - T0
        for i in P:
            for j in P:
                if i >= j or not (possible[i] and possible[j]):
                    continue
                if (i, j) not in x and (j, i) not in x:
                    m += y[i] + y[j] <= 1  # cannot be ordered either way
        for f in P:
            if not possible[f] or hi[f] - lo[f] > 1e-6:
                continue  # only nodes with a fixed start (MRT slot or lock)
            s_f = lo[f]
            for k in P:
                if k == f or not possible[k]:
                    continue
                before_ok = lo[k] + dur[k] + tmin[k][f] <= s_f + 1e-6
                after_ok = s_f + dur[f] + tmin[f][k] <= hi[k] + 1e-6
                both = y[k] + y[f] - 1
                if not before_ok and after_ok:
                    m += t[k] >= lo[k] + (s_f + dur[f] + tmin[f][k] - lo[k]) * both
                elif before_ok and not after_ok:
                    m += t[k] <= hi[k] - (hi[k] - (s_f - dur[k] - tmin[k][f])) * both

        # same product / same POI at most once (planner-algo `same_pois`)
        groups: Dict[str, List[int]] = {}
        for k in P:
            groups.setdefault(places[k - 1].group or places[k - 1].id, []).append(k)
        for members in groups.values():
            if len(members) > 1:
                m += xsum(y[k] for k in members) <= 1

        # anchors (planner-algo `anchor_pois`): a place id or any option of a group
        for mid in req.must_include:
            members = [idx[mid]] if mid in idx else groups.get(mid, [])
            if not members:
                return None, "MISSING_MUST"
            m += xsum(y[k] for k in members) >= 1

        for pid, start in req.locks.items():
            if pid not in idx:
                return None, "MISSING_LOCK"
            m += y[idx[pid]] == 1
            m += t[idx[pid]] == start

        for cat, need in req.category_min.items():
            m += xsum(y[k] for k in P if places[k - 1].category == cat) >= need

        # Hapui 추가: cap restaurant visits without changing the original objective.
        for cat, limit in req.category_max.items():
            m += xsum(y[k] for k in P if places[k - 1].category == cat) <= limit

        for tag, need in req.tag_min.items():
            m += xsum(y[k] for k in P if tag in places[k - 1].tags) >= need

        # Hapui: only the two extra hard constraints required by PRD §3.
        if req.budget is not None:
            m += xsum(places[k - 1].price * y[k] for k in P) <= req.budget
        if req.eat_by is not None:
            early_food = []
            for k in P:
                if places[k - 1].category != "food":
                    continue
                early = m.add_var(var_type=BINARY)
                m += early <= y[k]
                # Minute-resolution contract: must start strictly before the time.
                m += t[k] <= req.eat_by - 1 + max(0, D - req.eat_by + 1) * (1 - early)
                early_food.append(early)
            m += xsum(early_food) >= 1

        walk_m = xsum(dist[i][j] * var for (i, j), var in x.items())
        if req.max_walk_m is not None:
            m += walk_m <= req.max_walk_m

        if req.prefs:
            sat = {p: self._checklist_expr(m, req.prefs.get(p, []), places, P, y, walk_m) for p in req.people}
        else:
            sat = {
                p: xsum(places[k - 1].scores.get(p, 0.0) * y[k] for k in P)
                - req.walk_aversion.get(p, 0.0) * 0.001 * walk_m
                - req.stop_aversion.get(p, 0.0) * xsum(y[k] for k in P)
                for p in req.people
            }
        weights = req.weights or {p: 1.0 for p in req.people}
        z = m.add_var(lb=-1e4)
        for p in req.people:
            m += z <= sat[p] * (1.0 / req.sat_scale.get(p, 1.0))
            if p in req.min_satisfaction:
                m += sat[p] >= req.min_satisfaction[p]

        m.objective = maximize(
            xsum(weights.get(p, 0.0) * sat[p] for p in req.people)
            + req.fairness_weight * z
            + req.quality_weight * xsum(places[k - 1].quality * y[k] for k in P)
            - req.walk_penalty_per_km * walk_m * 0.001
            - 0.001 * t[E]  # tie-break: finish earlier
        )

        with _quiet_native_stdout():
            status = m.optimize()
        if status not in (OptimizationStatus.OPTIMAL, OptimizationStatus.FEASIBLE):
            return None, status.name

        # extract route by following arcs from start
        order, cur, seen = [], S, set()
        while cur != E and cur not in seen:
            seen.add(cur)
            nxt = next(j for j in V if (cur, j) in x and x[cur, j].x >= 0.99)
            order.append((cur, nxt))
            cur = nxt

        stops, clock, total_m, total_min = [], req.start_min, 0.0, 0.0
        for i, j in order:
            total_m += dist[i][j]
            total_min += tmin[i][j]
            arrive = clock + tmin[i][j]
            if j == E:
                clock = arrive
                break
            p = places[j - 1]
            # earliest start along the chosen route; only fixed slots / locks / opening hours cause waits
            start = max(arrive, p.open_min, p.fixed_start_min or 0, req.locks.get(p.id, 0))
            stops.append(Stop(p, round(arrive), round(start), round(start + p.duration_min),
                              round(dist[i][j]), round(tmin[i][j], 1)))
            clock = start + p.duration_min

        if req.prefs:
            checklist = {p: checklist_of(req.prefs.get(p, []), stops, total_m) for p in req.people}
            satisfaction = {p: checklist_pct(items) for p, items in checklist.items()}
            plan = Plan(label, stops, round(total_m), round(total_min, 1), round(clock), satisfaction,
                        dict(satisfaction), checklist)
            return plan, status.name
        satisfaction = {
            p: round(sum(s.place.scores.get(p, 0.0) for s in stops)
                     - req.walk_aversion.get(p, 0.0) * total_m / 1000
                     - req.stop_aversion.get(p, 0.0) * len(stops), 2)
            for p in req.people
        }
        return Plan(label, stops, round(total_m), round(total_min, 1), round(clock), satisfaction), status.name

    @staticmethod
    def _checklist_expr(m, prefs, places, P, y, walk_m):
        """Satisfaction in % = weighted mean of linear 0..1 fulfilment variables."""
        if not prefs:
            return xsum([])
        total_w = sum(it.weight for it in prefs)
        terms = []
        for it in prefs:
            f = m.add_var(lb=0.0, ub=1.0)
            if it.kind == "visit":
                m += f <= xsum(affinity(it, places[k - 1]) * y[k] for k in P) * (1.0 / (it.full or 1.0))
            elif it.kind == "dwell":
                m += f <= xsum(affinity(it, places[k - 1]) * places[k - 1].duration_min / it.full * y[k] for k in P)
            elif it.kind == "walk":  # `zero` doubles as a hard ceiling because f >= 0
                m += f <= (it.zero - walk_m) * (1.0 / (it.zero - it.full))
            elif it.kind == "stops":
                m += f <= (it.zero - xsum(y[k] for k in P)) * (1.0 / (it.zero - it.full))
            terms.append(it.weight * f)
        return xsum(terms) * (100.0 / total_w)

    # -- helpers ------------------------------------------------------------

    def _matrices(self, req: Request, places: List[Place]):
        if self._walk_m is not None and len(places) == len(self.places):
            return self._walk_m, self._walk_min
        pts = [req.start] + [(p.lat, p.lng) for p in places] + [req.end]
        return estimate_walk_matrix(pts)

    def _group_of(self, pid: str) -> str:
        for p in self.places:
            if p.id == pid:
                return p.group or p.id
        return pid

    def _name(self, pid: str) -> str:
        for p in self.places:
            if p.id == pid or p.group == pid:
                return p.name
        return pid

    def _remaining_category_min(self, req: Request, done_ids: List[str]) -> Dict[str, int]:
        left = dict(req.category_min)
        for p in self.places:
            if p.id in done_ids and p.category in left:
                left[p.category] = max(0, left[p.category] - 1)
        return {c: n for c, n in left.items() if n > 0}


# ---------------------------------------------------------------- comparison

def diff_plans(a: Plan, b: Plan, people: List[str]) -> Dict:
    """Deterministic trade-off facts; the LLM only turns these into sentences."""
    a_ids, b_ids = set(a.ids()), set(b.ids())
    name = {s.place.id: s.place.name for s in a.stops + b.stops}
    rest = lambda plan: sum(s.end_min - s.start_min for s in plan.stops if s.place.category == "cafe")
    return {
        "added": [name[i] for i in b.ids() if i not in a_ids],
        "dropped": [name[i] for i in a.ids() if i not in b_ids],
        "walk_m_delta": b.total_walk_m - a.total_walk_m,
        "cafe_rest_min_delta": rest(b) - rest(a),
        "finish_delta_min": b.finish_min - a.finish_min,
        "satisfaction_delta": {p: round(b.satisfaction[p] - a.satisfaction[p], 1) for p in people},
    }


def fmt_time(minutes: float) -> str:
    minutes = int(round(minutes))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def format_plan(plan: Plan) -> str:
    lines = [f"[{plan.label}] 도보 {plan.total_walk_m / 1000:.2f}km · {plan.total_walk_min:.0f}분 · 종료 {fmt_time(plan.finish_min)}"]
    if plan.satisfaction_pct:
        lines.append("  만족도: " + ", ".join(f"{p} {v:.0f}%" for p, v in plan.satisfaction_pct.items()))
    for s in plan.stops:
        wait = f" (대기 {s.wait_min}분)" if s.wait_min > 0 else ""
        tag = " [예약가능 확인]" if s.place.availability == "confirmed" else (
            " [예약가능 미확인]" if s.place.availability == "unverified" else "")
        lines.append(
            f"  {fmt_time(s.start_min)}-{fmt_time(s.end_min)} {s.place.name}"
            f"  ← 도보 {s.walk_m_from_prev:.0f}m{wait}{tag}"
        )
    return "\n".join(lines)
