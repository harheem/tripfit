# from pay_router import router
# app.include_router(router)
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from typing import Annotated

from pydantic import BaseModel, Field

from server.parsing import StrictModel, generate_inquiry

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


class InquiryItem(StrictModel):
    short_name: str = Field(min_length=1, max_length=200)
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    meeting: str | None = Field(default=None, max_length=300)


class InquiryRequest(StrictModel):
    item: InquiryItem
    people: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(min_length=2, max_length=2)
    split: list[Annotated[int, Field(ge=0, le=9007199254740991)]] = Field(min_length=2, max_length=2)
    question_hints: Annotated[str, Field(max_length=1000)] | Annotated[list[Annotated[str, Field(max_length=300)]], Field(max_length=8)] | None = None


@router.post("/inquiry")
async def inquiry(body: InquiryRequest):
    return await generate_inquiry(body.model_dump(exclude_none=True))
