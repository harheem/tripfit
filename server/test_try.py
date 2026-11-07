"""Arbitrary-input sessions, real CBC and no external network or keys."""
import asyncio
import copy
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from server import app as api, parsing
from server.state import Session, SessionStore, TokenBuckets
from solver.demo_builder import DemoSolver, MESSAGES
from solver.sample_seongsu import REQUEST, reload_mrt

ROOT = Path(__file__).resolve().parents[1]


def people(a="전시 꼭 보고 싶어", b="많이 못 걸어 카페에서 쉬고 싶어"):
    return [{"name": "지민", "text": a}, {"name": "서연", "text": b}]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for key in ("OPENAI_API_KEY", "OPENAI_MODEL", "OBA_API_KEY", "OBA_BASE_URL", "OBA_MODEL", "TRY_RATE_PER_MIN"):
        monkeypatch.delenv(key, raising=False)
    with api.SESSIONS.lock:
        api.SESSIONS.entries.clear()


@pytest.fixture(scope="module")
def client():
    reload_mrt(ROOT / "server/fixtures/mrt_snapshot.json")
    api._demo_cache = None
    with TestClient(api.app) as client:
        yield client
    reload_mrt()
    api._demo_cache = None


def test_try_full_demo_and_grounded_marks(client):
    inputs = people()
    response = client.post("/api/try", json={"people": inputs})
    assert response.status_code == 200
    data = response.json()
    assert set(client.get("/api/demo").json()) <= set(data)
    assert len(data["series"]) >= 1
    assert UUID(data["sessionId"]).version == 4
    assert data["source"]["provider"] == "rules"
    assert data["source"]["parseMs"] >= 0 and data["source"]["solveMs"] > 0
    assert data["unmatched"] == {"지민": [], "서연": []}
    for original, parsed in zip(inputs, data["people"]):
        assert parsed["text"] == original["text"]
        assert parsed["marks"]
        assert all(mark["phrase"] in original["text"] for mark in parsed["marks"])
    session = api.SESSIONS.get(data["sessionId"])
    assert session.request.category_min == {"exhibit": 1, "cafe": 1}
    assert [p.label for p in session.request.prefs["서연"]] == ["덜 걷기", "카페에서 쉬기"]


def test_needs_more_is_200(client):
    response = client.post("/api/try", json={"people": people(b="반가워")})
    assert response.status_code == 200
    assert response.json() == {"needsMore": True, "person": "서연",
                               "hint": "서연의 말에서 조건을 못 찾았어요. 예: '카페에서 쉬고 싶어'"}


@pytest.mark.parametrize("text,labels", [
    ("전시는 별로, 카페 말고 소품샵 꼭", ["소품샵"]),
    ("전시 안 보고 싶어, 카페는 싫어", []),
    ("전시는 보고 싶지 않아. 카페는 원하지 않아", []),
    ("걷는 건 괜찮아 전시 위주로", ["전시"]),
    ("골목 산책 느긋하게, 소품샵은 꼭", ["골목", "느긋하게", "소품샵"]),
    ("많이 못 걸어 카페에서 쉬고 싶어", ["덜 걷기", "카페에서 쉬기"]),
])
def test_rule_negation_and_local_phrases(text, labels):
    result = parsing.rule_parse(people(a=text))["people"][0]
    assert [p["label"] for p in result["prefs"]] == labels
    assert all(p["quote"] in text for p in result["prefs"])


def test_rule_strength_and_server_numbers():
    result = parsing.rule_parse(people("반드시 전시, 골목 조금, 소품샵 무조건", "카페 좀, 느긋하게"))
    prefs = result["people"][0]["prefs"]
    assert [p["weight"] for p in prefs] == [1.0, 0.4, 1.0]
    assert prefs[0]["match"] == parsing.DEFAULTS["전시"]["match"]
    request = parsing.request_from_constraints(result)
    assert request.max_walk_m is None
    walk = parsing.request_from_constraints(parsing.rule_parse(people("꼭 덜 걷기", "소품샵")))
    assert walk.max_walk_m == 3500 and walk.category_min == {}


def test_parse_arbitrary_input_never_returns_sample(client):
    data = client.post("/api/parse", json={"messages": people("소품샵", "느긋하게")}).json()
    assert data["provider"] == "rules" and data["model"] != "demo-fixed"
    assert data["constraints"]["people"][0]["prefs"][0]["label"] == "소품샵"


def test_session_request_used_by_all_followups(client, monkeypatch):
    data = client.post("/api/try", json={"people": people("소품샵 꼭", "카페에서 쉬고 싶어")}).json()
    session_id = data["sessionId"]
    session = api.SESSIONS.get(session_id)
    assert session.request.category_min == {"cafe": 1}
    captured = []
    original = DemoSolver._solve

    def observe(self, request, *args, **kwargs):
        assert api.SOLVE_LOCK.locked()
        captured.append(copy.deepcopy(request))
        return original(self, request, *args, **kwargs)

    monkeypatch.setattr(DemoSolver, "_solve", observe)
    pick = data["whatif"]["pick"]
    for endpoint, body in [
        ("plan", {}), ("what-if", {"pick": pick}),
        ("replan", {"now_min": 785, "keep": {pick: 960}}),
    ]:
        captured.clear()
        response = client.post("/api/" + endpoint, json={"sessionId": session_id, **body})
        assert response.status_code == 200
        assert captured
        assert all("exhibit" not in r.category_min for r in captured)
        assert all([p.label for p in r.prefs["지민"]] == ["소품샵"] for r in captured)
    assert REQUEST.category_min == {"exhibit": 1, "cafe": 1}
    # A returned copy cannot mutate the stored session.
    session.request.category_min.clear()
    assert api.SESSIONS.get(session_id).request.category_min == {"cafe": 1}


def test_missing_session_falls_back_and_reports_expiry(client):
    for endpoint, body in [("plan", {}), ("what-if", {"pick": "mrt_9000001_1600"}),
                           ("replan", {"now_min": 785})]:
        response = client.post("/api/" + endpoint, json={"sessionId": "expired", **body})
        assert response.status_code == 200 and response.json()["sessionExpired"] is True


def test_session_lru_and_absolute_ttl():
    now = [0]
    store = SessionStore(capacity=100, ttl=1800, clock=lambda: now[0])
    item = Session(REQUEST, [], MESSAGES)
    ids = [store.put(item) for _ in range(100)]
    now[0] = 10
    assert store.get(ids[0])
    latest = store.put(item)
    assert len(store.entries) == 100 and store.get(ids[1]) is None
    now[0] = 1800
    assert store.get(ids[0]) is None  # access did not renew TTL
    assert store.get(latest)
    now[0] = 1810
    assert store.get(latest) is None


def test_rate_limit_shared_across_routes_and_first_forwarded_ip(client, monkeypatch):
    payload = {"people": people(b="반가워")}
    for _ in range(3):
        assert client.post("/api/try", json=payload, headers={"X-Forwarded-For": "192.0.2.1, 10.0.0.1"}).status_code == 200
        assert client.post("/api/parse", json={"messages": people()}, headers={"X-Forwarded-For": "192.0.2.1"}).status_code == 200
    result = client.post("/api/try", json=payload, headers={"X-Forwarded-For": "192.0.2.1, 10.0.0.2"})
    assert result.status_code == 429 and result.json() == {"error": "잠시 후 다시"}
    monkeypatch.setenv("TRY_RATE_PER_MIN", "1")
    assert client.post("/api/try", json=payload, headers={"X-Forwarded-For": "192.0.2.2"}).status_code == 200
    assert client.post("/api/try", json=payload, headers={"X-Forwarded-For": "192.0.2.2"}).status_code == 429


def test_token_bucket_refills():
    now = [0]
    buckets = TokenBuckets(clock=lambda: now[0])
    assert all(buckets.allow("ip", 6) for _ in range(6))
    assert not buckets.allow("ip", 6)
    now[0] = 10
    assert buckets.allow("ip", 6) and not buckets.allow("ip", 6)
    now[0] = 70
    assert all(buckets.allow("ip", 6) for _ in range(6))


@pytest.mark.parametrize("bad", [people(a=""), people(a="x" * 201), people(a="   "),
                                 [{"name": "민수", "text": "전시"}, {"name": "서연", "text": "카페"}],
                                 [{"name": "지민", "text": "전시"}] * 2])
def test_try_validation(client, bad):
    assert client.post("/api/try", json={"people": bad}).status_code == 422


def test_try_infeasible_returns_diagnostic(client, monkeypatch):
    original = parsing.request_from_constraints
    monkeypatch.setattr(api, "request_from_constraints",
                        lambda c: replace(original(c), category_min={"exhibit": 20}))
    data = client.post("/api/try", json={"people": people()}).json()
    assert data["infeasible"]
    assert data["explanation"]["reason"] and data["explanation"]["relaxations"]


@pytest.mark.parametrize("failure", ["error", "timeout"])
def test_try_provider_failure_uses_rules(client, monkeypatch, failure):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setattr(parsing, "PROVIDER_TIMEOUT_S", 0.02)

    async def fail(*args, **kwargs):
        if failure == "timeout":
            await asyncio.sleep(1)
        raise ValueError("provider failed")

    monkeypatch.setattr(parsing, "provider_parse", fail)
    data = client.post("/api/try", json={"people": people()}).json()
    assert data["source"]["provider"] == "rules" and data["series"]


def test_llm_unmatched_and_empty_preferences(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")

    async def extracted(messages, **kwargs):
        assert kwargs["model"] == "test-model"
        result = parsing.rule_parse(messages)
        result["people"][0]["unmatched"] = ["초밥도"]
        return result, "actual-model"

    monkeypatch.setattr(parsing, "provider_parse", extracted)
    data = client.post("/api/try", json={"people": people(a="전시 꼭, 초밥도")}).json()
    assert data["source"]["provider"] == "openai"
    assert data["source"]["model"] == "actual-model"
    assert data["unmatched"]["지민"] == ["초밥도"]
    assert client.post("/api/try", json={"people": people(b="안녕")}).json()["needsMore"]


def test_llm_concurrency_limit_and_timeout_releases_slots(monkeypatch):
    active = peak = 0

    async def provider(*args, **kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0.03)
            return {}, "mock"
        finally:
            active -= 1

    monkeypatch.setattr(parsing, "provider_parse", provider)

    async def run():
        await asyncio.gather(*(parsing.limited_provider_parse([]) for _ in range(6)))
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(parsing.limited_provider_parse([]), 0.001)
        await asyncio.gather(*(parsing.limited_provider_parse([]) for _ in range(2)))

    asyncio.run(run())
    assert peak == 2 and active == 0


def test_normalize_accepts_empty_prefs_and_grounded_unmatched():
    messages = [parsing.Message(**p) for p in people("초밥 먹자", "카페")]
    raw = {"people": [
        {"name": "지민", "prefs": [], "unmatched": ["초밥 먹자"]},
        {"name": "서연", "prefs": [{"label": "카페에서 쉬기", "kind": "dwell",
                                     "intensity": "normal", "quote": "카페"}]},
    ]}
    result = parsing.normalize(parsing.Extraction.model_validate(raw), messages)
    assert result["people"][0]["prefs"] == []
    assert result["people"][0]["unmatched"] == ["초밥 먹자"]
    raw["people"][0]["unmatched"] = ["원문에 없는 말"]
    with pytest.raises(ValueError, match="Ungrounded"):
        parsing.normalize(parsing.Extraction.model_validate(raw), messages)


def test_rule_invalid_quantities_keep_safe_defaults():
    result = parsing.rule_parse(people("덜 걷기 99999km", "카페 0분"))
    assert result["people"][0]["prefs"][0]["full"] == 1500
    assert result["people"][1]["prefs"][0]["full"] == 50
