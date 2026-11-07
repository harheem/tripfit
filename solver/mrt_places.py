"""Snapshot-to-Place adapter. Importing this module never calls the network."""
from datetime import date, datetime
import json
import os
import re
from pathlib import Path

if __package__:
    from .tripfit_solver import Place
else:
    from tripfit_solver import Place

SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / 'data/mrt_snapshot.json'


def read_snapshot(path=None):
    try:
        data = json.loads(Path(path or os.getenv('MRT_SNAPSHOT_PATH', SNAPSHOT_PATH)).read_text())
        if not isinstance(data.get('picked'), list) or not data['picked']:
            return None
        date.fromisoformat(data['date'])
        datetime.fromisoformat(data['fetchedAt'])
        for product in data['picked']:
            assert re.fullmatch(r'\d+', product['gid'])
            assert product['url'] == f"https://experiences.myrealtrip.com/products/{product['gid']}"
            assert product.get('rating') is None or 0 <= product['rating'] <= 5
            assert product.get('reviews') is None or product['reviews'] >= 0
            assert product['name'] and 0 < product['durationMin'] <= 1440
            assert -90 <= product['lat'] <= 90 and -180 <= product['lng'] <= 180
            for option in product['options']:
                assert re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', option['start'])
                assert option['available'] is None or isinstance(option['available'], bool)
                assert option['price'] is None or option['price'] >= 0
        return data
    except (OSError, ValueError, KeyError, TypeError, AttributeError, AssertionError):
        return None


def snapshot_places(snapshot):
    places, facts, metadata = [], {}, {}
    for product in snapshot['picked']:
        group = f"mrt_{product['gid']}"
        for option in product['options']:
            pid = f"{group}_{option['start'].replace(':', '')}"
            h, m = map(int, option['start'].split(':'))
            available = option['available']
            place = Place(pid, f"{product['name']} {option['start']}", product['lat'], product['lng'],
                          'activity', product['durationMin'], scores={'지민': 6, '서연': 9},
                          group=group, fixed_start_min=h * 60 + m,
                          price=option['price'] if option['price'] is not None else product.get('price') or 0,
                          source='mrt', availability='confirmed' if available is True else
                          'unavailable' if available is False else 'unverified', url=product['url'])
            metadata[pid] = {**product, 'options': None, 'isReal': True,
                             'start': option['start'], 'available': available,
                             'priceSource': 'option' if option['price'] is not None else 'search',
                             'priceKnown': option['price'] is not None or product.get('price') is not None}
            facts[pid] = dict(branches=1, rating=product.get('rating'), reviews=product.get('reviews') or 0)
            # Sold-out inventory must never enter the optimization model.
            if available is not False:
                places.append(place)
    return places, facts, metadata
