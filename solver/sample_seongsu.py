"""Sample half-day in Seongsu for two companions (coordinates approximate).

Stands in for what TMAP POI search + MyRealTrip searchTnas/getTnaOptions return.
Replace with live API results on event day.
"""

if __package__:
    from .tripfit_solver import INTENSITY, Place, Pref, Request, place_quality
else:
    from tripfit_solver import INTENSITY, Place, Pref, Request, place_quality


def hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


PEOPLE = ["지민", "서연"]

# 지민: "전시는 꼭 보고 싶고, 골목 구경 좋아해"
# 서연: "많이 걷기 싫고, 카페에서 좀 쉬고 싶어. 소품샵은 좋아"
PLACES = [
    Place("exh_daelim", "대림창고 전시", 37.5418, 127.0565, "exhibit", 60, hm("11:00"), hm("20:00"),
          {"지민": 9, "서연": 4}, source="tmap"),
    Place("exh_dmuseum", "디뮤지엄 기획전", 37.5466, 127.0436, "exhibit", 90, hm("10:00"), hm("18:00"),
          {"지민": 10, "서연": 5}, price=15000, source="tmap"),
    Place("alley_yeonmu", "연무장길 골목 산책", 37.5432, 127.0571, "alley", 40, 0, 24 * 60,
          {"지민": 8, "서연": 3}, source="tmap"),
    Place("alley_shoe", "성수 수제화거리", 37.5446, 127.0530, "alley", 30, 0, 24 * 60,
          {"지민": 6, "서연": 4}, source="tmap", tags=["heritage"],
          story="명동·염천교 일대 구두 공장들이 옮겨 오며 생긴 거리. 지금도 골목 안 작은 공방에서 손으로 구두를 짓는다.",
          credit="서울특별시_서울미래유산 정보(공공누리 1유형)"),
    Place("cafe_onion", "어니언 성수", 37.5447, 127.0583, "cafe", 50, hm("08:00"), hm("22:00"),
          {"지민": 4, "서연": 8}, source="tmap"),
    Place("cafe_bluebottle", "블루보틀 성수", 37.5483, 127.0457, "cafe", 50, hm("08:00"), hm("20:00"),
          {"지민": 3, "서연": 7}, source="tmap"),
    Place("cafe_grandpa", "할아버지공장", 37.5433, 127.0594, "cafe", 50, hm("11:00"), hm("22:00"),
          {"지민": 4, "서연": 7}, source="tmap"),
    Place("shop_understand", "언더스탠드에비뉴 소품샵", 37.5434, 127.0421, "shop", 40, hm("11:00"), hm("21:00"),
          {"지민": 3, "서연": 8}, source="tmap"),
    Place("shop_atelier", "성수역 소품샵 골목", 37.5452, 127.0566, "shop", 30, hm("12:00"), hm("21:00"),
          {"지민": 3, "서연": 7}, source="tmap"),
    Place("park_seoulforest", "서울숲 산책", 37.5444, 127.0374, "park", 40, 0, 24 * 60,
          {"지민": 5, "서연": 2}, source="tmap"),
    # MyRealTrip product with bookable start times (getTnaOptions -> options[].name)
    Place("mrt_leather_1400", "가죽공방 원데이클래스 14:00", 37.5440, 127.0548, "activity", 120,
          scores={"지민": 6, "서연": 9}, group="mrt_leather", fixed_start_min=hm("14:00"),
          price=55000, source="mrt", availability="confirmed"),
    Place("mrt_leather_1600", "가죽공방 원데이클래스 16:00", 37.5440, 127.0548, "activity", 120,
          scores={"지민": 6, "서연": 9}, group="mrt_leather", fixed_start_min=hm("16:00"),
          price=55000, source="mrt", availability="unverified"),
]

# "숨은 한 곳 +1": Seoul Future Heritage (서울미래유산) spots near Seongsu. They join the
# candidate set only when the chip is on (TripFitSolver(PLACES + HIDDEN), tag_min={"heritage": 1}).
# 성수 수제화거리 above is also a heritage spot. Coordinates approximate; story copy is a
# sample to be rewritten from the heritage CSV's history field on event day.
HIDDEN = [
    Place("heritage_gongs", "공씨책방", 37.5450, 127.0510, "heritage", 25, hm("12:00"), hm("20:00"),
          {"지민": 5, "서연": 3}, source="heritage", tags=["heritage"],
          story="수십 년을 버틴 헌책방. 임대료에 밀려 오래 있던 동네를 떠난 뒤, 성수에서 다시 책장을 채웠다.",
          credit="서울특별시_서울미래유산 정보(공공누리 1유형)"),
]

START = (37.5446, 127.0557)  # 성수역
END = (37.5436, 127.0446)  # 서울숲역

# Place score Q inputs (sample; on event day: TMAP same-name search for branches, MRT rating/reviews,
# SKT place congestion forecast for the afternoon). Level 1..4 = 여유..붐빔.
PLACE_FACTS = {
    "exh_daelim": dict(branches=1, crowd=2),
    "exh_dmuseum": dict(branches=1, crowd=2),
    "alley_yeonmu": dict(branches=1, crowd=3),
    "alley_shoe": dict(branches=1, crowd=1, heritage=True),
    "cafe_onion": dict(branches=4, crowd=3),
    "cafe_bluebottle": dict(branches=12, crowd=2),
    "cafe_grandpa": dict(branches=1, crowd=2),
    "shop_understand": dict(branches=1, crowd=2),
    "shop_atelier": dict(branches=1, crowd=2),
    "park_seoulforest": dict(branches=1, crowd=2),
    "mrt_leather_1400": dict(branches=1, rating=4.8, reviews=120),
    "mrt_leather_1600": dict(branches=1, rating=4.8, reviews=120),
    "heritage_gongs": dict(branches=1, crowd=1, heritage=True),
}
for _p in PLACES + HIDDEN:
    _p.quality, _p.quality_parts = place_quality(**PLACE_FACTS[_p.id])

# What the LLM extracts from the two messages. Hard items are constraints; every sentence also becomes
# checklist items (label + intensity label + quote). Thresholds are published defaults, not per-place numbers.
PREFS = {
    "지민": [
        Pref("전시", "visit", INTENSITY["strong"], "전시는 꼭 보고 싶어", match={"exhibit": 1.0}),
        Pref("골목 2곳", "visit", INTENSITY["normal"], "골목도 여기저기 구경하고 싶어",
             match={"alley": 1.0, "heritage": 0.5}, full=2),  # "여기저기" -> 2 places
    ],
    "서연": [
        Pref("덜 걷기", "walk", INTENSITY["strong"], "나 오늘 많이 못 걸어", full=1500, zero=3500),
        Pref("카페에서 쉬기", "dwell", INTENSITY["normal"], "카페에서 좀 쉬고 싶어", match={"cafe": 1.0}, full=50),
        Pref("느긋하게", "stops", INTENSITY["normal"], "좀 쉬고 싶어", full=3, zero=7),
        Pref("소품샵", "visit", INTENSITY["normal"], "소품샵은 좋아",
             match={"shop": 1.0, "activity": 0.5, "heritage": 0.5}),
    ],
}

REQUEST = Request(
    people=PEOPLE,
    start=START,
    end=END,
    start_min=hm("13:00"),
    deadline_min=hm("18:30"),
    category_min={"exhibit": 1, "cafe": 1},  # 지민 hard: 전시 / 서연 hard: 카페 휴식
    max_walk_m=3500,  # 서연 hard: "많이 걷기 싫어" -> 3.5km
    prefs=PREFS,
    quality_weight=2.0,  # Σ Q: picks among routes whose checklists tie (≈2%p per great place)
)
