import pytest
import httpx
import httpx2

@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args,**kwargs):raise AssertionError('Tests must not use network; mock MRT')
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',blocked)
    monkeypatch.setattr(httpx2.HTTPTransport,'handle_request',blocked)
    monkeypatch.setattr(httpx2.AsyncHTTPTransport,'handle_async_request',blocked)

@pytest.fixture
def scenario():
    from copy import deepcopy
    from scripts.smoke_mcp import SCENARIO
    return deepcopy(SCENARIO)

@pytest.fixture(scope='module')
def result():
    from scripts.smoke_mcp import SCENARIO
    from hapui.planner import propose
    return propose(SCENARIO)
