# from pay_router import router
# app.include_router(router)
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/pay")


class RecheckRequest(BaseModel):
    gid: str
    url: str
    date: str
    start: str


@router.post("/recheck")
def recheck(body: RecheckRequest):
    try:
        # TripFit's repository root must be on sys.path. No import-time I/O.
        from solver.mrt_live import get_options
    except Exception as exc:
        raise HTTPException(503, detail=f"예약 조회 모듈을 불러올 수 없어요: {exc}") from exc

    try:
        options = get_options(body.gid, body.url, body.date)
    except Exception as exc:
        raise HTTPException(503, detail=f"예약 옵션 조회에 실패했어요: {exc}") from exc
    if not isinstance(options, list) or not options:
        raise HTTPException(503, detail="예약 옵션 조회 결과가 없어요")
    option = next((o for o in options if isinstance(o, dict) and o.get("start") == body.start), None)
    if option is None:
        raise HTTPException(503, detail=f"{body.start} 예약 옵션이 없어요")
    available, price = option.get("available"), option.get("price")
    # Sold-out options may have price=None; unknown availability is not sold out.
    if not isinstance(available, bool) or not (
        (type(price) is int and 0 <= price <= 9007199254740991)
        or (available is False and price is None)
    ):
        raise HTTPException(503, detail="예약 가능 여부 또는 가격을 확인할 수 없어요")
    return {"available": available, "price": price,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "source": "live", "option_start": option["start"]}
