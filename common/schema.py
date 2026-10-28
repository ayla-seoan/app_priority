"""두 프로젝트가 공유하는 데이터 스키마.

AI 응답은 반드시 이 스키마를 통과해야만 저장된다.
스키마를 통과하지 못한 응답은 '실패'로 간주하고 fallback 으로 넘어간다.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- 주제 1
class ScoredItem(BaseModel):
    """우선순위가 매겨진 백로그 항목 하나."""

    item_id: str = Field(description="입력 CSV 의 id 값을 그대로")
    title: str
    rank: int = Field(ge=1, description="1 이 가장 먼저")
    score: float = Field(ge=0, le=100)
    kpi: str = Field(description="이 항목이 기여하는 KPI 이름. 입력된 KPI 중 하나여야 함")
    reason: str = Field(
        max_length=120,
        description="왜 이 순위인지 한 문장. 입력 데이터에 있는 사실만 사용",
    )


class ExcludedItem(BaseModel):
    """이번 분기에 하지 않기로 한 항목."""

    item_id: str
    title: str
    reason: str = Field(max_length=120)


class PriorityResult(BaseModel):
    top_items: list[ScoredItem]
    excluded: list[ExcludedItem]


# ---------------------------------------------------------------- 주제 2
class CafeEntry(BaseModel):
    """트윗 원문에서 뽑아낸 생일 카페 정보 한 건."""

    cafe_name: str
    artist: str
    address: str = Field(description="지도에 꽂을 수 있는 주소. 추측하지 말 것")
    start_date: date
    end_date: date
    perks: list[str] = Field(default_factory=list, description="특전. 예: 포토카드, 컵홀더")
    goods: list[str] = Field(default_factory=list, description="판매 굿즈")
    confidence: Literal["high", "low"] = Field(
        description="주소나 기간이 원문에 명확히 없으면 low",
    )


class CafeExtraction(BaseModel):
    entries: list[CafeEntry]
