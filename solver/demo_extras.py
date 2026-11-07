"""Presentation evidence only; no changes to the optimization model."""
if __package__:
    from .sample_seongsu import PLACE_FACTS
    from .tripfit_solver import affinity
else:
    from sample_seongsu import PLACE_FACTS
    from tripfit_solver import affinity


HISTORY = [{"date": "10.12", "place": "익선동", "person": "지민", "label": "덜 걷기",
            "note": "서연 따라 많이 걸음"}]


def place_facts(place):
    return {"branches": 1, "rating": None, "reviews": 0, "crowd": None,
            **PLACE_FACTS.get(place.id, {}), "open": place.open_min, "close": place.close_min}


def attach_fills(plan, request):
    if plan is not None:
        for stop in plan.stops:
            stop._fills = [{"person": person, "label": pref.label, "quote": pref.quote}
                           for person, prefs in request.prefs.items() for pref in prefs
                           if pref.weight > 0 and pref.kind in ("visit", "dwell")
                           and affinity(pref, stop.place) > 0]
    return plan


def recommend(options, people, history=HISTORY):
    """All previews reuse solved plans. History only breaks max-min ties."""
    counts = {person: sum(row["person"] == person for row in history) for person in people}
    for option in options:
        plan = option["plan"]
        option["preview"] = {"sat": plan["sat"], "walkM": plan["walkM"],
                             "dropped": list(option["diff"]["dropped"]),
                             "minSat": min(plan["sat"].values())}
    if not options:
        return None
    best = max(options, key=lambda o: (o["preview"]["minSat"], -counts.get(o["owner"], 0)))
    pair = " 대 ".join(str(round(best["preview"]["sat"][p])) for p in people)
    reasons = [f"빼면 {pair}, 더 고르게, 둘 중 낮은 만족도 {best['preview']['minSat']:.1f}%"]
    if history:
        last = history[-1]
        due = min(people, key=lambda p: counts[p])
        prefix = "" if due == best["owner"] else "참고: "
        reasons.append(f"{prefix}지난번 {last['place']}에선 {last['person']}이 하나 뺐어요. 이번엔 {due} 차례예요")
    return {"id": best["id"], "reasons": reasons}
