"""Evidence payloads use solved plans and session-specific preferences."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import app as api
from solver.demo_extras import recommend
from solver.sample_seongsu import reload_mrt

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(monkeypatch):
    for key in ("OPENAI_API_KEY", "OBA_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    reload_mrt(ROOT / "data/mrt_snapshot.json")
    api._demo_cache = None
    with TestClient(api.app) as value:
        yield value
    reload_mrt()
    api._demo_cache = None


def assert_recommendation(data):
    assert data["infeasible"] and data["recommended"]["reasons"]
    for option in data["relaxations"]:
        preview = option["preview"]
        assert preview["minSat"] == min(preview["sat"].values())
        assert preview["walkM"] >= 0 and isinstance(preview["dropped"], list)
        if "plan" in option:
            assert preview["sat"] == option["plan"]["sat"]
            assert preview["walkM"] == option["plan"]["walkM"]
            assert preview["dropped"] == option["diff"]["dropped"]
    best = next(o for o in data["relaxations"] if o["id"] == data["recommended"]["id"])
    assert best["preview"]["minSat"] == max(o["preview"]["minSat"] for o in data["relaxations"])


def test_demo_poi_facts_fills_and_maxmin_preview(client):
    data = client.get("/api/demo").json()
    assert data["history"][0]["person"] == "지민"
    onion = next(p for p in data["places"] if p["id"] == "cafe_onion")
    assert onion["facts"] == {"branches": 4, "rating": None, "reviews": 0, "crowd": 3,
                              "open": 480, "close": 1320}
    plan = data["series"][data["defaultIdx"]]
    daelim = next(s for s in plan["stops"] if s["id"] == "exh_daelim")
    assert {"person": "지민", "label": "전시", "quote": "전시는 꼭 보고 싶어"} in daelim["fills"]
    for plan in data["series"]:
        for person, items in plan["checklist"].items():
            weight = sum(i["weight"] for i in items) or 1
            assert round(100 * sum(i["weight"] * i["fulfilled"] for i in items) / weight, 1) == plan["sat"][person]
    assert_recommendation(data["whatif"])
    response = client.post("/api/what-if", json={"pick": data["whatif"]["pick"]}).json()
    assert sorted(o["preview"]["minSat"] for o in response["relaxations"]) == [20.6, 58.8]
    assert_recommendation(response)
    assert response["recommended"]["id"] == "category_min:cafe"


def test_session_whatif_previews_and_fills_are_grounded(client):
    inputs = [{"name": "지민", "text": "전시는 꼭 보고 싶어 골목 여기저기"},
              {"name": "서연", "text": "많이 못 걸어 카페에서 쉬고 싶어 소품샵 좋아 느긋하게"}]
    data = client.post("/api/try", json={"people": inputs}).json()
    assert data["sessionId"] and data["places"][0]["facts"]
    result = client.post("/api/what-if", json={"sessionId": data["sessionId"],
                                              "pick": data["whatif"]["pick"]}).json()
    assert all(o["preview"]["minSat"] == min(o["preview"]["sat"].values())
               for o in result["relaxations"])
    for option in result["relaxations"]:
        selected = client.post("/api/what-if", json={"sessionId": data["sessionId"],
            "pick": data["whatif"]["pick"], "relax": option["id"]}).json()
        assert selected["plan"]["sat"] == option["preview"]["sat"]
        for stop in selected["plan"]["stops"]:
            for fill in stop["fills"]:
                assert fill["label"] in {i["label"] for i in data["prefs"][fill["person"]]}
                assert fill["quote"] in next(i["text"] for i in inputs if i["name"] == fill["person"])
    plan = client.post("/api/plan", json={"sessionId": data["sessionId"],
        "muted": [{"person": "지민", "label": "전시"}]}).json()
    assert all(not (f["person"] == "지민" and f["label"] == "전시")
               for p in plan["series"] for s in p["stops"] for f in s["fills"])
    assert_recommendation(result)


def test_history_only_breaks_maxmin_ties():
    def option(rid, owner, low):
        return {"id": rid, "owner": owner, "plan": {"sat": {"지민": low, "서연": 80}, "walkM": 100},
                "diff": {"dropped": ["카페"]}}
    history = [{"person": "서연", "place": "익선동"}]
    options = [option("j", "지민", 20), option("s", "서연", 59)]
    result = recommend(options, ["지민", "서연"], history)
    assert result["id"] == "s" and result["reasons"][1].startswith("참고")
    assert recommend([option("j", "지민", 59), option("s", "서연", 59)],
                     ["지민", "서연"], history)["id"] == "j"
