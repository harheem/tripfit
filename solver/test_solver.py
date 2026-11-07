"""Scenario tests from PRD §7. Run: python test_solver.py  (or pytest)."""

import time
from dataclasses import replace

from pathlib import Path
from sample_seongsu import HIDDEN, PLACES, REQUEST, hm, reload_mrt

reload_mrt(Path(__file__).resolve().parents[1] / "server/fixtures/mrt_snapshot.json")
from tripfit_solver import Infeasible, Plan, TripFitSolver, haversine_m, DETOUR_FACTOR, WALK_M_PER_MIN

SOLVER = TripFitSolver(PLACES)


def assert_valid(plan: Plan, req):
    """Hard constraints hold and the timeline is physically consistent."""
    assert plan.finish_min <= req.deadline_min + 1, plan.finish_min
    if req.max_walk_m is not None:
        assert plan.total_walk_m <= req.max_walk_m + 1, plan.total_walk_m
    for cat, need in req.category_min.items():
        assert sum(s.place.category == cat for s in plan.stops) >= need, cat
    for tag, need in req.tag_min.items():
        assert sum(tag in s.place.tags for s in plan.stops) >= need, tag
    prev_end = req.start_min
    prev_pt = req.start
    for s in plan.stops:
        p = s.place
        assert s.start_min >= p.open_min and s.end_min <= p.close_min, p.id
        if p.fixed_start_min is not None:
            assert s.start_min == p.fixed_start_min, p.id
        walk = haversine_m(prev_pt, (p.lat, p.lng)) * DETOUR_FACTOR / WALK_M_PER_MIN
        assert s.arrive_min >= prev_end + walk - 1.5, (p.id, s.arrive_min, prev_end, walk)
        assert s.start_min >= s.arrive_min
        prev_end, prev_pt = s.end_min, (p.lat, p.lng)
    groups = [s.place.group for s in plan.stops if s.place.group]
    assert len(groups) == len(set(groups)), "same product booked twice"


def test_alternatives_are_distinct_valid_and_fair():
    t0 = time.time()
    plans = SOLVER.alternatives(REQUEST)
    assert time.time() - t0 < 3.0
    assert len(plans) >= 2
    assert len({tuple(p.ids()) for p in plans}) == len(plans)
    for plan in plans:
        assert_valid(plan, REQUEST)
        if plan.label.endswith("우선"):
            other = [p for p in REQUEST.people if not plan.label.startswith(p)][0]
            assert plan.satisfaction_pct[other] >= 60 - 0.5, plan.satisfaction_pct


def test_booked_activity_conflicts_with_recommendation():
    """추천 장소가 좋아도 이미 예약한 일정과 충돌하면? -> keep the booking, re-route the rest."""
    req = replace(REQUEST, locks={"mrt_9000001_1400": hm("14:00")}, must_include=["exh_dmuseum"])
    out = SOLVER.solve_or_explain(req)
    if isinstance(out, Infeasible):
        assert out.relaxations
    else:
        assert_valid(out, req)
        assert "mrt_9000001_1400" in out.ids()


def test_what_if_add_reports_tradeoff():
    """체험을 넣으면 무엇이 빠지나?"""
    base = SOLVER.alternatives(REQUEST)[-1]
    plan, diff = SOLVER.what_if_add(REQUEST, "mrt_9000001_1600", base)
    assert isinstance(plan, Plan)
    assert_valid(plan, REQUEST)
    assert "mrt_9000001_1600" in plan.ids()
    assert diff["dropped"], "a 2-hour class must displace something"


def test_reoptimize_keeps_commitment():
    """여행 중 계획이 틀어지면? -> start from here/now, keep the 16:00 class."""
    req = replace(REQUEST, must_include=["mrt_9000001_1600"])
    now, here = hm("13:52"), (37.5452, 127.0566)
    plan = SOLVER.reoptimize(req, now, here, done_ids=["shop_atelier"],
                             keep={"mrt_9000001_1600": hm("16:00")})
    assert isinstance(plan, Plan), plan
    assert "shop_atelier" not in plan.ids()
    assert all(s.start_min >= now for s in plan.stops)
    leather = [s for s in plan.stops if s.place.id == "mrt_9000001_1600"]
    assert leather and leather[0].start_min == hm("16:00")


def test_impossible_request_explains_what_to_give_up():
    """이동시간이 늘어나면 무엇부터 포기해야 할까?"""
    req = replace(REQUEST, max_walk_m=1500, must_include=["exh_dmuseum", "mrt_9000001_1400"])
    out = SOLVER.solve_or_explain(req)
    assert isinstance(out, Infeasible)
    assert out.relaxations
    assert any("도보 한도" in r for r in out.relaxations)


def test_unverified_slot_is_flagged():
    """API에서 확인하지 못한 정보는 계획에 그대로 표시된다."""
    plan, _ = SOLVER.what_if_add(REQUEST, "mrt_9000001_1600", SOLVER.solve(REQUEST))
    slot = [s for s in plan.stops if s.place.id == "mrt_9000001_1600"][0]
    assert slot.place.availability == "unverified"


def test_hidden_spot_chip_adds_heritage_without_breaking_limits():
    """'숨은 한 곳 +1': 미래유산 후보 중 최소 한 곳을 넣되, 서연의 도보 한도 등 하드 제약은 그대로."""
    req = replace(REQUEST, tag_min={"heritage": 1})
    plan = TripFitSolver(PLACES + HIDDEN).solve(req)
    assert plan is not None
    assert_valid(plan, req)
    assert any("heritage" in s.place.tags for s in plan.stops)
    impossible = replace(req, tag_min={"heritage": 5})
    result = TripFitSolver(PLACES + HIDDEN).solve_or_explain(impossible)
    assert isinstance(result, Infeasible) and any("숨은 한 곳" in r for r in result.relaxations), result


def test_real_forest_concession_and_locked_replan():
    """The real meeting point is infeasible until a named person's hard mark gives."""
    from demo_builder import build_demo
    from tripfit_solver import Stop
    root = Path(__file__).resolve().parents[1]
    try:
        reload_mrt(root / "data/mrt_snapshot.json")
        data = build_demo()
        whatif = data["whatif"]
        assert whatif["pick"] == "mrt_3828508_1500"
        assert whatif["infeasible"] is True
        assert {r["owner"] for r in whatif["relaxations"]} == {"지민", "서연"}
        assert {r["id"] for r in whatif["relaxations"]} == {"category_min:cafe", "category_min:exhibit"}
        assert not any(c["kind"] == "must_include" for r in whatif["relaxations"] for c in r["changes"])
        assert whatif["chosen"]["relaxationId"] == "category_min:cafe"
        assert whatif["chosen"]["plan"]["label"] == "하나 뺀 뒤"
        assert data["pay"]["price"] == 35000 and data["pay"]["people"] == 2
        by_id = {p.id: p for p in PLACES}
        for option in whatif["relaxations"]:
            req = replace(REQUEST, category_min={k: v for k, v in REQUEST.category_min.items()
                                                if k != option["changes"][0]["key"]},
                          must_include=[whatif["pick"]])
            for saved, check_req in ((option["plan"], req),
                    (option["replan"]["plan"], replace(req, start_min=option["replan"]["now"]))):
                plan = Plan("test", [Stop(by_id[s["id"]], s["arrive"], s["start"], s["end"],
                            s["walkM"], s["walkMin"]) for s in saved["stops"]],
                            saved["walkM"], saved["walkMin"], saved["finish"], {})
                assert_valid(plan, check_req)
                booking = next(s for s in saved["stops"] if s["id"] == whatif["pick"])
                assert booking["start"] == hm("15:00")
            assert option["replan"]["crowded"] not in {s["id"] for s in option["replan"]["plan"]["stops"]}
            flexible = [s for s in option["plan"]["stops"] if not s["fixed"]]
            preferred = sorted(flexible, key=lambda s: s["cat"] != "cafe")[0]
            assert option["replan"]["crowded"] == preferred["id"]
        assert data["replan"]["plan"] is not None
    finally:
        reload_mrt(root / "server/fixtures/mrt_snapshot.json")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        t0 = time.time()
        fn()
        print(f"PASS {fn.__name__} ({time.time() - t0:.2f}s)")
    print(f"{len(tests)} passed")
