"""End-to-end demo of the 1-minute pitch flow, without any external API."""

import time
from dataclasses import replace

from sample_seongsu import PLACES, REQUEST, hm
from tripfit_solver import Infeasible, TripFitSolver, diff_plans, format_plan


def main():
    solver = TripFitSolver(PLACES)
    print(f"solver backend: {solver.solver_name}\n")

    t0 = time.time()
    plans = solver.alternatives(REQUEST)
    print(f"== 1) 각자 취향 -> 대안 {len(plans)}개 ({time.time() - t0:.2f}s)")
    for p in plans:
        print(format_plan(p), "\n")

    if len(plans) >= 2:
        print("== 2) 대안 비교 (첫 안 -> 마지막 안)")
        print(diff_plans(plans[0], plans[-1], REQUEST.people), "\n")

    base = plans[-1]
    print("== 3) 활동 추가: 가죽공방 16:00 넣으면?")
    result, diff = solver.what_if_add(REQUEST, "mrt_leather_1600", base)
    if isinstance(result, Infeasible):
        print("불가능:", result.relaxations)
    else:
        print(format_plan(result))
        print("트레이드오프:", diff, "\n")

    if not isinstance(result, Infeasible) and result.stops:
        first = result.stops[0]
        late = first.end_min + 20
        print(f"== 4) 일정 중 변경: {first.place.name}에서 20분 더 머묾 ({late // 60:02d}:{late % 60:02d}). 가죽공방 16:00은 지키기")
        re = solver.reoptimize(
            replace(REQUEST, must_include=["mrt_leather_1600"]),
            now_min=late,
            here=(first.place.lat, first.place.lng),
            done_ids=[first.place.id],
            keep={"mrt_leather_1600": hm("16:00")},
        )
        print(format_plan(re) if not isinstance(re, Infeasible) else re)
        print()

    print("== 5) 조건 충돌: 도보 1.5km 한도 + 디뮤지엄 + 가죽공방 14:00")
    tight = replace(REQUEST, max_walk_m=1500, must_include=["exh_dmuseum", "mrt_leather_1400"])
    out = solver.solve_or_explain(tight)
    if isinstance(out, Infeasible):
        print("실행 불가. 다음 중 하나를 양보하면 가능:")
        for r in out.relaxations:
            print("  -", r)
    else:
        print(format_plan(out))


if __name__ == "__main__":
    main()
