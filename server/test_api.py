"""Offline integration tests: real CBC, mocked provider transport only."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from server.app import app
from server import parsing
from solver.demo_builder import MESSAGES, build_demo
from solver.sample_seongsu import PREFS

ROOT = Path(__file__).resolve().parents[1]


def without_ms(value):
    if isinstance(value, dict):
        return {k: without_ms(v) for k, v in value.items() if k not in ("solveMs", "ms")}
    if isinstance(value, list):
        return [without_ms(v) for v in value]
    return value


@pytest.fixture(scope="module")
def client():
    from server import app as module
    from solver.sample_seongsu import reload_mrt
    reload_mrt(ROOT / "server/fixtures/mrt_snapshot.json")
    module._demo_cache = None
    with TestClient(app) as client:
        yield client
    reload_mrt()
    module._demo_cache = None


@pytest.fixture
def no_keys(monkeypatch):
    for name in ("OBA_API_KEY", "OBA_BASE_URL", "OBA_MODEL", "OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)


def test_health_only_reports_key_presence(client, no_keys, monkeypatch):
    assert client.get("/api/health").json() == {
        "ok": True, "solver": "CBC", "llm": {"axk2": False, "openai": False}}
    monkeypatch.setenv("OBA_API_KEY", "secret-test-key")
    result = client.get("/api/health")
    assert result.json()["llm"]["axk2"] is True
    assert "secret-test-key" not in result.text


def test_demo_shape_content_cache_and_static(client):
    text = (ROOT / "web/demo_data.js").read_text()
    sample = json.loads(text.split("window.DEMO = ", 1)[1].rstrip(";\n"))
    first = client.get("/api/demo").json()
    assert set(first) - {"live", "computedAt"} == set(sample)
    assert first["live"] is True
    assert without_ms({k: first[k] for k in sample}) == without_ms(build_demo())
    assert client.get("/api/demo").json() == first
    response = client.get("/api/demo?fresh=1")
    assert response.status_code == 200
    fresh = response.json()
    assert fresh["computedAt"] != first["computedAt"]
    assert client.get("/api/demo").json() == fresh
    assert client.get("/").status_code == 200
    assert "text/html" in client.get("/").headers["content-type"]
    assert client.get("/demo_data.js").status_code == 200


def test_plan_muting_changes_real_solution_and_retains_item(client):
    baseline = client.post("/api/plan", json={}).json()
    result = client.post("/api/plan", json={"muted": [{"person": "서연", "label": "덜 걷기"}]}).json()
    assert result["live"] and result["solveMs"] > 0
    assert without_ms(result["series"]) != without_ms(baseline["series"])
    assert [p["sat"] for p in result["series"]] != [p["sat"] for p in baseline["series"]]
    for plan in result["series"]:
        item = next(i for i in plan["checklist"]["서연"] if i["label"] == "덜 걷기")
        assert item["muted"] is True and item["weight"] == 0
    assert PREFS["서연"][0].weight == 1.0
    assert not any("muted" in i for p in client.get("/api/demo").json()["series"]
                   for i in p["checklist"]["서연"])


def test_muted_walking_has_unique_satisfaction_pairs(client):
    response = client.post("/api/plan", json={
        "muted": [{"person": "서연", "label": "덜 걷기"}], "tag_min": {}})
    assert response.status_code == 200
    series = response.json()["series"]
    assert series
    pairs = [tuple(round(p["sat"][name], 1) for name in ("지민", "서연")) for p in series]
    assert len(pairs) == len(set(pairs))


def test_all_prefs_can_be_conceded(client):
    muted = [{"person": name, "label": pref.label} for name, prefs in PREFS.items() for pref in prefs]
    response = client.post("/api/plan", json={"muted": muted})
    assert response.status_code == 200
    for plan in response.json()["series"]:
        assert plan["sat"] == {"지민": 0.0, "서연": 0.0}
        assert all(item["muted"] for items in plan["checklist"].values() for item in items)


def test_builder_muted_checklist_and_prefs():
    result = build_demo(muted=[("서연", "덜 걷기")])
    assert next(p for p in result["prefs"]["서연"] if p["label"] == "덜 걷기")["muted"]
    for plan in result["series"] + [(result["whatif"].get("chosen") or result["whatif"])["plan"], result["replan"]["plan"], result["hidden"]["plan"]]:
        assert next(p for p in plan["checklist"]["서연"] if p["label"] == "덜 걷기")["weight"] == 0


def test_impossible_plan_has_actionable_relaxations(client):
    response = client.post("/api/plan", json={"tag_min": {"heritage": 5}})
    result = response.json()
    assert response.status_code == 200
    assert result["infeasible"] and result["relaxations"]
    assert any({"kind": "tag_min", "key": "heritage", "from": 5, "to": 0} in r["changes"]
               for r in result["relaxations"])


def test_hidden_tag_adds_candidate(client):
    result = client.post("/api/plan", json={"tag_min": {"heritage": 1}}).json()
    assert result["series"]
    assert all(any("heritage" in s["tags"] for s in p["stops"]) for p in result["series"])


@pytest.mark.parametrize("pick", ["mrt_9000001_1600", "mrt_9000001_1400"])
def test_what_if_returns_booked_plan_and_balanced_diff(client, pick):
    result = client.post("/api/what-if", json={"pick": pick}).json()
    assert any(s["id"] == pick for s in result["plan"]["stops"])
    demo = client.get("/api/demo").json()
    base = demo["series"][demo["defaultIdx"]]
    assert result["diff"]["walk_m_delta"] == result["plan"]["walkM"] - base["walkM"]
    assert result["diff"]["dropped"]


def test_replan_excludes_crowd_and_keeps_booking(client):
    result = client.post("/api/replan", json={"now_min": 785, "exclude": ["cafe_onion"],
                                             "keep": {"mrt_9000001_1600": 960}}).json()
    stops = result["plan"]["stops"]
    assert all(s["id"] != "cafe_onion" and s["start"] >= 785 for s in stops)
    assert any(s["id"] == "mrt_9000001_1600" and s["start"] == 960 for s in stops)


def test_replan_impossible_has_explanation(client):
    result = client.post("/api/replan", json={"now_min": 785, "exclude": ["mrt_9000001_1600"],
                                             "keep": {"mrt_9000001_1600": 960}}).json()
    assert result["infeasible"] and result["relaxations"]


def demo_messages():
    return [{"name": name, "text": value["text"]} for name, value in MESSAGES.items()]


def test_parse_no_keys_uses_fixed_sample(client, no_keys):
    result = client.post("/api/parse", json={"messages": demo_messages()}).json()
    assert result["fallback"] is True and result["model"] == "demo-fixed"
    assert result["constraints"] == parsing.demo_constraints()
    assert result["ms"] >= 0
    other = client.post("/api/parse", json={"messages": [{"name": "민수", "text": "공원 가자"}]}).json()
    assert other["fallback"] and other["constraints"]["clarify"]


def extracted():
    return {"people": [{"name": "지민", "prefs": [
        {"label": "전시", "kind": "visit", "intensity": "strong", "quote": "전시는 꼭 보고 싶어"},
        {"label": "골목 2곳", "kind": "visit", "intensity": "normal", "quote": "골목도 여기저기", "full": 2}]},
        {"name": "서연", "prefs": [{"label": "덜 걷기", "kind": "walk", "intensity": "strong", "quote": "많이 못 걸어"}]}]}


def configure_providers(monkeypatch):
    for name, value in {"OBA_API_KEY": "test-oba", "OBA_BASE_URL": "https://example.invalid/v1",
                        "OBA_MODEL": "axk2-test", "OPENAI_API_KEY": "test-openai",
                        "OPENAI_MODEL": "openai-test"}.items():
        monkeypatch.setenv(name, value)


def test_parse_retries_schema_then_normalizes(client, no_keys, monkeypatch):
    configure_providers(monkeypatch)
    invalid = extracted()
    invalid["people"][0]["prefs"][0]["match"] = {"exhibit": 999}
    replies = [invalid, extracted()]
    create = AsyncMock(side_effect=[SimpleNamespace(model="actual-axk2", choices=[SimpleNamespace(
        message=SimpleNamespace(content=json.dumps(r)))]) for r in replies])

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(parsing, "AsyncOpenAI", FakeClient)
    result = client.post("/api/parse", json={"messages": demo_messages()}).json()
    assert not result["fallback"] and result["model"] == "actual-axk2"
    assert create.await_count == 2
    assert create.call_args.kwargs["response_format"] == {"type": "json_object"}
    pref = result["constraints"]["people"][0]["prefs"][0]
    assert pref["match"] == {"exhibit": 1.0, "heritage": 0.5} and pref["full"] == 1


def test_provider_timeout_moves_to_openai_and_missing_model_skips(client, no_keys, monkeypatch):
    configure_providers(monkeypatch)
    calls = []
    async def provider(messages, **kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"] == "axk2-test":
            await asyncio.sleep(1)
        return parsing.demo_constraints(), "actual-openai"
    monkeypatch.setattr(parsing, "provider_parse", provider)
    monkeypatch.setattr(parsing, "PROVIDER_TIMEOUT_S", 0.02)
    result = client.post("/api/parse", json={"messages": demo_messages()}).json()
    assert calls == ["axk2-test", "openai-test"]
    assert result["model"] == "actual-openai" and not result["fallback"]
    monkeypatch.delenv("OPENAI_MODEL")
    calls.clear()
    result = client.post("/api/parse", json={"messages": demo_messages()}).json()
    assert calls == ["axk2-test"] and result["fallback"]


def test_parse_rejects_invented_quantity():
    raw = extracted()
    raw["people"][1]["prefs"][0]["full"] = 999
    with pytest.raises(ValueError):
        parsing.normalize(parsing.Extraction.model_validate(raw),
                          [parsing.Message(**m) for m in demo_messages()])


def test_schema_exhaustion_tries_both_providers_then_falls_back(client, no_keys, monkeypatch):
    configure_providers(monkeypatch)
    calls = []

    class InvalidClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        async def create(self, **kwargs):
            calls.append(kwargs["model"])
            return SimpleNamespace(model=kwargs["model"], choices=[SimpleNamespace(
                message=SimpleNamespace(content='{"people": []}'))])
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(parsing, "AsyncOpenAI", InvalidClient)
    result = client.post("/api/parse", json={"messages": demo_messages()}).json()
    assert calls == ["axk2-test", "axk2-test", "openai-test", "openai-test"]
    assert result["fallback"] and result["model"] == "demo-fixed"


def test_concurrent_solves_are_serialized(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    import time
    from server.app import DemoSolver, SOLVE_LOCK
    from solver.tripfit_solver import Plan

    active = peak = 0
    barrier = threading.Barrier(2)

    def fake_reoptimize(*args, **kwargs):
        nonlocal active, peak
        assert SOLVE_LOCK.locked()
        active += 1
        peak = max(peak, active)
        time.sleep(0.03)
        active -= 1
        return Plan("test", [], 0, 0, 800, {}, {}, {})

    def request():
        barrier.wait(timeout=5)
        return client.post("/api/replan", json={"now_min": 785})

    monkeypatch.setattr(DemoSolver, "reoptimize", fake_reoptimize)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(request) for _ in range(2)]
        assert all(f.result().status_code == 200 for f in futures)
    assert peak == 1


@pytest.mark.parametrize("url,body", [
    ("/api/plan", {"muted": [{"person": "서연", "label": "없는 항목"}]}),
    ("/api/plan", {"tag_min": {"heritage": -1}}),
    ("/api/what-if", {"pick": "unknown"}),
    ("/api/replan", {"now_min": 9999}),
    ("/api/replan", {"now_min": 785, "keep": {"unknown": 960}}),
])
def test_invalid_inputs(client, url, body):
    assert client.post(url, json=body).status_code == 422


def test_real_whatif_requires_named_concession_and_preserves_it_in_replan(client):
    from server import app as module
    from solver.sample_seongsu import reload_mrt, REQUEST
    try:
        reload_mrt(ROOT / "data/mrt_snapshot.json")
        pick = "mrt_3828508_1500"
        first = client.post("/api/what-if", json={"pick": pick})
        assert first.status_code == 200
        data = first.json()
        assert data["infeasible"] and "plan" not in data
        assert {o["owner"] for o in data["relaxations"]} == {"서연", "지민"}
        assert all(o["kind"] == "category_min" for o in data["relaxations"])
        assert not any(c["kind"] == "must_include" for o in data["relaxations"] for c in o["changes"])
        for option in data["relaxations"]:
            selected = client.post("/api/what-if", json={"pick": pick, "relax": option["id"]}).json()
            assert selected["infeasible"] is False
            plan = selected["plan"]
            assert next(s for s in plan["stops"] if s["id"] == pick)["start"] == 900
            assert plan["walkM"] <= REQUEST.max_walk_m + 1
            assert plan["finish"] <= REQUEST.deadline_min
            kept_category = "exhibit" if option["id"] == "category_min:cafe" else "cafe"
            assert any(s["cat"] == kept_category for s in plan["stops"])
            saved = selected["replan"]
            after = client.post("/api/replan", json={"now_min": saved["now"],
                "exclude": [saved["crowded"]], "keep": {pick: 900}, "pick": pick,
                "relax": option["id"]}).json()["plan"]
            assert all(s["id"] != saved["crowded"] for s in after["stops"])
            assert next(s for s in after["stops"] if s["id"] == pick)["start"] == 900
            assert any(s["cat"] == kept_category for s in after["stops"])
        assert client.post("/api/what-if", json={"pick": pick, "relax": "must_include:" + pick}).status_code == 422
        assert client.post("/api/replan", json={"now_min": 785, "relax": "category_min:cafe"}).status_code == 422
    finally:
        reload_mrt(ROOT / "server/fixtures/mrt_snapshot.json")
        module._demo_cache = None
