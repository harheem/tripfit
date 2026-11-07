"""MCP parsing and refresh regression tests; no network unless explicitly enabled."""
import copy
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from solver import mrt_live as mrt
from solver.mrt_places import read_snapshot, snapshot_places
from solver.sample_seongsu import reload_mrt, PLACES, MRT_SNAPSHOT
from server import app as server

FIXTURE = Path(__file__).parent / 'fixtures/mrt_snapshot.json'


def test_widget_search_parses_rating_price_and_deduplicates():
    widget = {'widget': {'type': 'ListView', 'children': [
        {'type': 'ListViewItem', 'children': [
            {'type': 'Text', 'value': '서울 성수 클래스'},
            {'type': 'Text', 'value': '⭐ 4.9 (1,234)'},
            {'type': 'Text', 'value': '39,000원~'},
            {'type': 'Button', 'url': 'https://experiences.myrealtrip.com/products/123'}]}]}}
    with patch.object(mrt, 'call_tool', return_value=widget):
        products = mrt.search_products(['성수', '서울숲'])
    assert products == [{'gid': '123', 'url': 'https://experiences.myrealtrip.com/products/123',
                         'name': '서울 성수 클래스', 'rating': 4.9, 'reviews': 1234, 'price': 39000}]


def test_transport_timeout_mcp_errors_and_sse():
    with patch.object(mrt.urllib.request, 'urlopen', side_effect=TimeoutError):
        assert mrt.search_products(['성수']) is None
        assert mrt.get_detail('123', 'url') is None
        assert mrt.get_options('123', 'url', '2026-11-14') is None
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'event: message\ndata: {"id":1,"result":{"tools":[]}}\n\n'
    with patch.object(mrt.urllib.request, 'urlopen', return_value=Response()) as call:
        assert mrt.rpc('tools/list') == {'tools': []}
        assert call.call_args.kwargs['timeout'] == 10
    with patch.object(mrt, 'rpc', return_value={'content': [{'type': 'text', 'text': 'automatic lookup is restricted'}]}):
        assert mrt.get_options('123', 'url', '2026-11-14') is None


def test_option_inventory_is_time_specific_and_for_two_people():
    payload = {'success': True, 'selectedDate': '2026-11-14', 'isRequestedDateAvailable': True,
               'options': [
                   {'name': '14:00', 'availablePurchaseQuantity': 0, 'salePrice': 30000},
                   {'name': '오후 3시', 'availablePurchaseQuantity': 1, 'salePrice': 31000},
                   {'name': '16:00', 'salePrice': 32000},
                   {'name': '19:00(9월 18:30,10월 18:00)', 'availablePurchaseQuantity': 4, 'salePrice': 35000}]}
    slots = mrt.parse_options(payload, '2026-11-14')
    assert [(s['start'], s['available']) for s in slots] == [
        ('14:00', False), ('15:00', False), ('16:00', None), ('19:00', True)]
    assert mrt.parse_options(payload, '2026-11-15') is None
    assert mrt.start_time('19:00(9월 18:30,10월 18:00)', '2026-10-14') == '18:00'
    sold = {**payload, 'isRequestedDateAvailable': False, 'options': [],
            'units': [{'unitItems': [{'name': '14:00'}]}]}
    assert mrt.parse_options(sold, '2026-11-14')[0]['available'] is False
    payload['options'] = [{'name': '인원 수', 'availablePurchaseQuantity': 10}]
    assert mrt.parse_options(payload, '2026-11-14') == []


def test_detail_duration_does_not_confuse_hourly_departures():
    with patch.object(mrt, 'call_tool', return_value={'widget': {'children': [
        {'type': 'Text', 'value': '시간: 12:00-20:00 (1시간 간격)'},
        {'type': 'Text', 'value': '장소: 서울 성동구 성수이로 39, 2층'}]}}):
        result = mrt.get_detail('123', 'url')
        assert result['durationMin'] == 120 and result['durationSource'] == 'default'
        assert result['meetingText'] == '서울 성동구 성수이로 39, 2층'
    with patch.object(mrt, 'call_tool', return_value='소요시간: 1시간 30분'):
        assert mrt.get_detail('123', 'url')['durationMin'] == 90


def test_snapshot_adapter_keeps_real_facts_and_excludes_sold_out():
    data = read_snapshot(FIXTURE)
    data['picked'][0]['options'].append({'start': '17:00', 'available': False, 'price': 60000})
    places, facts, metadata = snapshot_places(data)
    assert len(places) == 2
    assert {p.group for p in places} == {'mrt_9000001'}
    assert places[1].availability == 'unverified'
    assert places[0].url.endswith('/9000001')
    assert facts[places[0].id]['reviews'] == 120
    assert metadata['mrt_9000001_1700']['available'] is False


def test_missing_or_corrupt_snapshot_uses_sample(tmp_path):
    try:
        broken = tmp_path / 'missing.json'
        reload_mrt(broken)
        assert all(p.source == 'sample' for p in PLACES if p.category == 'activity')
        broken.write_text('{"picked": [null]}')
        assert read_snapshot(broken) is None
    finally:
        reload_mrt()


def test_refresh_deadline_is_ten_seconds():
    with patch.object(server.subprocess, 'run', side_effect=subprocess.TimeoutExpired('mrt', 10)) as run:
        with pytest.raises(subprocess.TimeoutExpired):
            server.fetch_mrt_refresh()
        assert run.call_args.kwargs['timeout'] == 10
        assert '--stdout' in run.call_args.args[0]


def test_api_refresh_success_failure_and_invalidation(tmp_path, monkeypatch):
    snapshot = read_snapshot(FIXTURE)
    path = tmp_path / 'mrt_snapshot.json'
    path.write_text(json.dumps(snapshot))
    monkeypatch.setattr(server, 'SNAPSHOT_PATH', path)
    reload_mrt(path)
    server._demo_cache = {'old': True}
    # No lifespan warming is needed for these snapshot-only routes.
    client = TestClient(server.app)
    try:
        assert client.get('/api/mrt').json()['picked'] == snapshot['picked']
        previous = path.read_bytes()
        def fail(): raise subprocess.TimeoutExpired('mrt', 10)
        monkeypatch.setattr(server, 'fetch_mrt_refresh', fail)
        response = client.post('/api/mrt/refresh').json()
        assert not response['refreshed'] and path.read_bytes() == previous
        assert server._demo_cache == {'old': True}
        updated = copy.deepcopy(snapshot)
        updated['picked'][0]['options'][0]['price'] = 12345
        monkeypatch.setattr(server, 'fetch_mrt_refresh', lambda: updated)
        assert client.post('/api/mrt/refresh').json()['refreshed']
        assert server._demo_cache is None
        assert next(p.price for p in PLACES if p.id.endswith('_1400')) == 12345
        assert MRT_SNAPSHOT == updated
        monkeypatch.setattr(server, 'fetch_mrt_refresh', lambda: {'picked': []})
        saved = path.read_bytes()
        assert not client.post('/api/mrt/refresh').json()['refreshed']
        assert path.read_bytes() == saved
    finally:
        reload_mrt()
        server._demo_cache = None


def test_builder_handles_one_and_zero_feasible_starts():
    from solver.demo_builder import build_demo
    try:
        reload_mrt(FIXTURE)
        one = [p for p in PLACES if p.category != 'activity' or p.fixed_start_min == 960]
        data = build_demo(places=one)
        assert len(data['whatif']['choices']) == 1 and data['whatif']['alt'] is None
        assert data['replan']['keep'] == data['whatif']['pick']
        zero = build_demo(places=[p for p in one if p.category != 'activity'])
        assert zero['whatif']['pick'] is None and zero['replan'] is None
    finally:
        reload_mrt()


@pytest.mark.skipif(os.getenv('RUN_NETWORK_TESTS') != '1', reason='MCP live test is opt-in')
def test_live_mcp_search_detail_options():
    products = mrt.search_products(['서울숲'])
    assert products
    product = next(p for p in products if p['gid'] == '3828508')
    assert mrt.get_detail(product['gid'], product['url'])['meetingText']
    assert mrt.get_options(product['gid'], product['url'], os.getenv('MRT_DATE', '2026-11-14')) is not None


def test_discovery_filters_foreign_results_and_never_invents_times(monkeypatch):
    from scripts import fetch_mrt_snapshot as fetcher
    monkeypatch.setattr(fetcher, 'QUERIES', ['성수 공방'])
    schema = {'tools': [{'name': name, 'inputSchema': {'properties': {key: {} for key in fields}}}
                        for name, fields in {'searchTnas': ['query'], 'getTnaDetail': ['gid', 'url'],
                                             'getTnaOptions': ['gid', 'url', 'selectedDate']}.items()]}
    monkeypatch.setattr(mrt, 'rpc', lambda *args: schema)
    def product(gid, name):
        return {'gid': gid, 'url': f'https://experiences.myrealtrip.com/products/{gid}',
                'name': name, 'price': 35000, 'rating': 5, 'reviews': 16}
    rows = [product('1', '홋카이도 치즈 공방'), product('2', '성수 통기타'), product('3', '서울숲 체험')]
    monkeypatch.setattr(mrt, 'search_products', lambda queries: rows)
    monkeypatch.setattr(mrt, 'get_detail', lambda gid, url: {
        'meetingText': '서울숲 방문자센터' if gid == '3' else '서울 성수',
        'durationMin': 120, 'durationSource': 'default'})
    monkeypatch.setattr(mrt, 'get_options', lambda gid, url, date: [] if gid == '2' else [
        {'start': '15:00', 'available': True, 'price': 35000, 'optionName': '15:00'}])
    snapshot, reason = fetcher.fetch_snapshot('2026-11-14')
    assert reason is None and [p['gid'] for p in snapshot['picked']] == ['3']
    assert {p['name'] for p in snapshot['rejected']} == {'홋카이도 치즈 공방', '성수 통기타'}
    monkeypatch.setattr(mrt, 'get_options', lambda *args: None)
    assert fetcher.fetch_snapshot('2026-11-14')[0] is None


def test_refresh_rechecks_selected_product_and_keeps_empty_inventory(monkeypatch):
    from scripts import fetch_mrt_snapshot as fetcher
    from solver import mrt_places
    previous = read_snapshot(FIXTURE)
    previous['picked'][0]['locationEvidence'] = '제목/집결지 지명: 성수'
    monkeypatch.setattr(mrt_places, 'read_snapshot', lambda: previous)
    schema = {'tools': [{'name': name, 'inputSchema': {'properties': {key: {} for key in fields}}}
                        for name, fields in {'searchTnas': ['query'], 'getTnaDetail': ['gid', 'url'],
                                             'getTnaOptions': ['gid', 'url', 'selectedDate']}.items()]}
    monkeypatch.setattr(mrt, 'rpc', lambda *args: schema)
    monkeypatch.setattr(mrt, 'search_products', lambda queries: previous['picked'])
    monkeypatch.setattr(mrt, 'get_detail', lambda *args: {
        'meetingText': previous['picked'][0]['meetingText'], 'durationMin': 90, 'durationSource': 'detail'})
    monkeypatch.setattr(mrt, 'get_options', lambda *args: [])
    snapshot, reason = fetcher.refresh_snapshot()
    assert reason is None
    assert snapshot['picked'][0]['options'] == []
    assert snapshot['picked'][0]['durationMin'] == 90
    assert snapshot['rejectedAsOf'] == previous['fetchedAt']
    monkeypatch.setattr(mrt, 'get_options', lambda *args: None)
    assert fetcher.refresh_snapshot()[0] is None
