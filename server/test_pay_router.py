import sys
import types
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.pay_router import router

BODY = {"gid": "3828508", "url": "https://experiences.myrealtrip.com/products/3828508",
        "date": "2026-11-14", "start": "15:00"}


@pytest.fixture
def client(monkeypatch):
    # Never allow a test to fall through to the real network client.
    monkeypatch.setitem(sys.modules, "solver", types.ModuleType("solver"))
    monkeypatch.setitem(sys.modules, "solver.mrt_live", None)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as session:
        yield session


def inject(monkeypatch, get_options):
    module = types.ModuleType("solver.mrt_live")
    module.get_options = get_options
    monkeypatch.setitem(sys.modules, "solver.mrt_live", module)


def test_success(client, monkeypatch):
    calls = []

    def get_options(*args):
        calls.append(args)
        return [{"start": "10:00", "available": True, "price": 20000},
                {"start": "15:00", "available": True, "price": 35000,
                 "optionName": "15:00", "stock": 999}]

    inject(monkeypatch, get_options)
    response = client.post("/api/pay/recheck", json=BODY)
    assert response.status_code == 200
    data = response.json()
    assert calls == [(BODY["gid"], BODY["url"], BODY["date"])]
    assert {k: v for k, v in data.items() if k != "checked_at"} == {
        "available": True, "price": 35000, "source": "live", "option_start": "15:00"}
    assert datetime.fromisoformat(data["checked_at"]).utcoffset() == timedelta(0)


@pytest.mark.parametrize("options", [None, [], [{"start": "10:00", "available": True, "price": 35000}]])
def test_no_option(client, monkeypatch, options):
    inject(monkeypatch, lambda *args: options)
    response = client.post("/api/pay/recheck", json=BODY)
    assert response.status_code == 503
    assert "없어요" in response.json()["detail"]


def test_import_failure(client):
    response = client.post("/api/pay/recheck", json=BODY)
    assert response.status_code == 503
    assert "모듈" in response.json()["detail"]


def test_lookup_exception(client, monkeypatch):
    def broken(*args):
        raise RuntimeError("test outage")

    inject(monkeypatch, broken)
    response = client.post("/api/pay/recheck", json=BODY)
    assert response.status_code == 503
    assert "test outage" in response.json()["detail"]


def test_sold_out_without_price(client, monkeypatch):
    inject(monkeypatch, lambda *args: [{"start": "15:00", "available": False, "price": None, "stock": 0}])
    response = client.post("/api/pay/recheck", json=BODY)
    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["price"] is None


@pytest.mark.parametrize("available,price", [(None, 35000), (True, None), (True, 35000.5), (True, True), (True, -1)])
def test_unknown_or_invalid_option(client, monkeypatch, available, price):
    inject(monkeypatch, lambda *args: [{"start": "15:00", "available": available, "price": price}])
    assert client.post("/api/pay/recheck", json=BODY).status_code == 503
