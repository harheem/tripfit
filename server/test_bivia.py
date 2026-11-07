"""Offline decision contract, provider transport and scope safety checks."""
import asyncio
import copy
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server import bivia
from server.pay_router import router

HTTPX_SEND = httpx.AsyncClient.send

BODY = {"item": {"short_name": "서울숲 힐링 숲체험", "start": "15:00", "date": "2026-11-14"},
        "people": ["지민", "서연"],
        "lines": [{"person": p, "mandate_max": 35000, "amount": 35000} for p in ("지민", "서연")],
        "checks": [{"key": k, "ok": True, "detail": "16:50까지 남아 있어요" if k == "expiry" else "맞아요"}
                   for k in sorted(bivia.REQUIRED_CHECKS)],
        "changed": None, "merchant": {"expected": "마이리얼트립", "actual": "마이리얼트립"}}
ANSWER = {"type": "choice", "value": bivia.CHOICES[0], "probability": .97,
          "distribution": dict(zip(bivia.CHOICES, [.97, .03])), "status": "answered", "model": "dec-1"}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.delenv("A8_API_KEY", raising=False)
    monkeypatch.delenv("BIVIA_API_KEY", raising=False)

    async def forbidden(*args, **kwargs):
        raise AssertionError("Network is disabled in this test")

    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def transport(monkeypatch, answer=ANSWER, status=200):
    requests = []
    original = httpx.AsyncClient

    def handler(request):
        requests.append(request)
        return httpx.Response(status, json=answer)

    # Replace the patched send through the class's original implementation.
    monkeypatch.setattr(httpx.AsyncClient, "send", HTTPX_SEND)
    monkeypatch.delenv("BIVIA_API_KEY", raising=False)
    monkeypatch.setenv("A8_API_KEY", "private-test-token")
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    return requests


def test_no_key_rules_has_no_invented_scores(client):
    result = client.post("/api/pay/decide", json=BODY)
    assert result.status_code == 200
    data = result.json()
    assert data["provider"] == "rules" and data["final"] == "proceed"
    assert "probability" not in data and "distribution" not in data
    assert data["fallback_reason"] == "키 없음"


def test_answered_transport_and_state(client, monkeypatch):
    requests = transport(monkeypatch)
    data = client.post("/api/pay/decide", json=BODY).json()
    assert data["provider"] == "articul8-bivia" and data["final"] == "proceed"
    assert data["model"] == "dec-1" and data["probability"] == .97
    request = requests[0]
    assert str(request.url) == bivia.BIVIA_URL
    assert request.headers["authorization"] == "Bearer private-test-token"
    assert request.headers["content-type"] == "application/json"
    payload = json.loads(request.content)
    assert payload["choices"] == bivia.CHOICES and payload["mode"] == "fast" and payload["allow_abstain"] is True
    assert payload["question"] == "에이전트가 지금 이 결제를 진행해도 되는가?"
    assert all(s in payload["state"] for s in ("35,000", "15:00", "16:50", "마이리얼트립"))
    assert request.extensions["timeout"]["read"] == 8
    assert "private-test-token" not in json.dumps(data)


def test_engine_failure_overrides_bivia_proceed(client, monkeypatch):
    transport(monkeypatch)
    body = copy.deepcopy(BODY)
    body["lines"][0]["amount"] = 38000
    body["checks"][0]["ok"] = False
    body["changed"] = {"from": 35000, "to": 38000}
    data = client.post("/api/pay/decide", json=body).json()
    assert data["value"] == bivia.CHOICES[0] and data["final"] == "stop"
    assert "38,000" in data["override_reason"] and "35,000" in data["reason"]


@pytest.mark.parametrize("key", sorted(bivia.REQUIRED_CHECKS))
def test_every_engine_check_can_veto(client, monkeypatch, key):
    transport(monkeypatch)
    body = copy.deepcopy(BODY)
    next(c for c in body["checks"] if c["key"] == key)["ok"] = False
    data = client.post("/api/pay/decide", json=body).json()
    assert data["final"] == "stop" and data["override_reason"]


def test_merchant_mismatch_in_state_and_rules(client):
    body = copy.deepcopy(BODY)
    body["merchant"]["actual"] = "다른 판매처"
    assert "결제 요청이 맡긴 곳이 아닌 다른 판매처에서 왔다" in bivia.state_text(body)
    data = client.post("/api/pay/decide", json=body).json()
    assert data["final"] == "stop" and "다른 판매처" in data["reason"]


@pytest.mark.parametrize("raw", [
    {"status": "abstained", "value": None, "abstain_reason": "확신이 부족해요"},
    {"result": {"type": "abstain", "abstention_reason": "확신이 부족해요", "model": "dec-1"}},
])
def test_abstained_locks_payment(client, monkeypatch, raw):
    transport(monkeypatch, raw)
    data = client.post("/api/pay/decide", json=BODY).json()
    assert data["status"] == "abstained" and data["value"] is None and data["final"] == "stop"
    assert data["reason"] == "확신이 부족해요" and data["override_reason"] is None


def test_aliases_and_distribution_shapes():
    data = bivia.parse_bivia({"data": {"choice": bivia.CHOICES[1], "confidence": .93,
        "probabilities": [{"choice": c, "probability": p} for c, p in zip(bivia.CHOICES, [.07, .93])]}})
    assert data["value"] == bivia.CHOICES[1] and data["probability"] == .93
    assert data["distribution"][bivia.CHOICES[1]] == .93
    assert bivia.parse_bivia({"selected_choice": bivia.CHOICES[0], "distribution": [.97, .03]})["distribution"] == ANSWER["distribution"]


def test_invalid_scores_are_not_fabricated():
    data = bivia.parse_bivia({**ANSWER, "probability": float("nan"), "distribution": {bivia.CHOICES[0]: 1.2}})
    assert "probability" not in data and "distribution" not in data


@pytest.mark.parametrize("raw,status", [({}, 200), ({"value": "unknown"}, 200), ({}, 503)])
def test_provider_failure_falls_back_without_scores(client, monkeypatch, raw, status):
    transport(monkeypatch, raw, status)
    data = client.post("/api/pay/decide", json=BODY).json()
    assert data["provider"] == "rules" and data["final"] == "proceed"
    assert "probability" not in data and "distribution" not in data


def test_timeout_and_alternate_key(client, monkeypatch):
    seen = []
    monkeypatch.setenv("BIVIA_API_KEY", "alternate-test-token")
    monkeypatch.setattr(bivia, "TIMEOUT_S", .01)

    async def slow(data, key):
        seen.append(key)
        await asyncio.sleep(1)

    monkeypatch.setattr(bivia, "provider_decide", slow)
    data = client.post("/api/pay/decide", json=BODY).json()
    assert seen == ["alternate-test-token"] and data["provider"] == "rules"
    assert data["ms"] < 500 and "alternate-test-token" not in json.dumps(data)


def test_response_text_cannot_expose_credentials_or_forbidden_symbols():
    data = bivia.parse_bivia({**ANSWER, "reason": "private-test-token\u2014이유\u00b7확인", "model": "private-test-token"}, "private-test-token")
    assert "private-test-token" not in json.dumps(data)
    assert all(c not in data["reason"] for c in ("\u2014", "\u00b7"))


def test_missing_checks_and_mismatched_lines(client):
    body = copy.deepcopy(BODY)
    body["checks"] = body["checks"][:1]
    assert client.post("/api/pay/decide", json=body).json()["final"] == "stop"
    body["lines"][0]["person"] = "다른 사람"
    assert client.post("/api/pay/decide", json=body).status_code == 422


def test_rate_limit_shared_with_inquiry(monkeypatch):
    from server.app import app
    monkeypatch.setenv("TRY_RATE_PER_MIN", "1")
    client = TestClient(app)
    assert client.post("/api/pay/decide", json=BODY).status_code == 200
    assert client.post("/api/pay/inquiry", json={}).status_code == 429
