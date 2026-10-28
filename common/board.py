"""우선순위 결과를 스티커 보드로 바꾸고, 사람이 옮긴 결과를 다시 순위로 바꾼다.

보드 템플릿 세 가지를 지원한다.
  - "3x3"            : 영향도 3단계 x 공수 3단계
  - "impact_effort"  : 영향/노력 2x2 (Do it now / next / if time / don't)
  - "pyramid"        : 처음 순위로 4단 피라미드 (위로 갈수록 좁고 중요)

핵심 아이디어: 셀마다 우선순위 등급이 정해져 있다. 사람이 스티커를 옮기면
셀이 바뀌고, 셀 순서 + 셀 안에서의 위치로 새 순위가 다시 계산된다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from .schema import PriorityResult

# 공수(H)를 3단계로 나누는 경계. 팀 사정에 맞게 화면에서 바꿀 수 있다.
EFFORT_BANDS_3 = (40, 96)    # <=40H LOW, <=96H MEDIUM, 그 위 HIGH
EFFORT_SPLIT_2 = 64          # <=64H 저노력, 그 위 고노력

IMPACT_BANDS_3 = (34, 67)    # 점수 <34 LOW, <67 MEDIUM, 그 위 HIGH
IMPACT_SPLIT_2 = 50

# 피라미드 단을 나누는 처음 순위 경계. 1 / 2~3 / 4~6 / 7~ → Top 10 이면 1·2·3·4건
PYRAMID_TIERS = (1, 3, 6)


TEMPLATES: dict[str, dict] = {
    "3x3": {
        "label": "3x3 우선순위 지정",
        "rows": [("HIGH", "높음"), ("MEDIUM", "보통"), ("LOW", "낮음")],
        "cols": [("LOW", "낮음"), ("MEDIUM", "보통"), ("HIGH", "높음")],
        "x_axis": "공수 (Effort)",
        "y_axis": "영향도 (Impact)",
        # 셀 우선순위: 영향 큰 쪽 먼저, 같으면 공수 적은 쪽 먼저
        "order": {
            "HIGH-LOW": 1, "HIGH-MEDIUM": 2, "MEDIUM-LOW": 3,
            "HIGH-HIGH": 4, "MEDIUM-MEDIUM": 5, "LOW-LOW": 6,
            "MEDIUM-HIGH": 7, "LOW-MEDIUM": 8, "LOW-HIGH": 9,
        },
        "cell_notes": {
            "HIGH-LOW": "지금 한다", "HIGH-MEDIUM": "지금 한다", "MEDIUM-LOW": "지금 한다",
            "HIGH-HIGH": "다음에 한다", "MEDIUM-MEDIUM": "다음에 한다", "LOW-LOW": "다음에 한다",
            "MEDIUM-HIGH": "여유 있으면", "LOW-MEDIUM": "여유 있으면", "LOW-HIGH": "하지 않는다",
        },
    },
    "impact_effort": {
        "label": "영향 / 노력 매트릭스",
        "rows": [("HIGH", "영향 큼"), ("LOW", "영향 작음")],
        "cols": [("LOW", "노력 적음"), ("HIGH", "노력 많음")],
        "x_axis": "노력 (Effort)",
        "y_axis": "영향 (Impact)",
        "order": {"HIGH-LOW": 1, "HIGH-HIGH": 2, "LOW-LOW": 3, "LOW-HIGH": 4},
        "cell_notes": {
            "HIGH-LOW": "Do it now", "HIGH-HIGH": "Do it next",
            "LOW-LOW": "여유 있을 때", "LOW-HIGH": "하지 않는다",
        },
    },
    "pyramid": {
        "label": "피라미드 다이어그램",
        "shape": "pyramid",   # 보드 컴포넌트가 격자 대신 위가 좁은 단으로 그린다
        "rows": [("P1", "최우선"), ("P2", "높음"), ("P3", "보통"), ("P4", "여유")],
        "cols": [("ALL", "")],
        "x_axis": "",
        "y_axis": "우선순위",
        "order": {"P1-ALL": 1, "P2-ALL": 2, "P3-ALL": 3, "P4-ALL": 4},
        "cell_notes": {
            "P1-ALL": "최우선 · 지금 바로", "P2-ALL": "높음 · 이번 분기 핵심",
            "P3-ALL": "보통 · 다음에 한다", "P4-ALL": "여유 있으면",
        },
    },
}


@dataclass
class Sticker:
    id: str
    title: str
    kpi: str
    score: float
    effort_hours: float
    ai_rank: int
    cell: str
    reason: str = ""


def _band(value: float, bands: tuple[float, float]) -> str:
    low, mid = bands
    if value <= low:
        return "LOW"
    if value <= mid:
        return "MEDIUM"
    return "HIGH"


def impact_thresholds(scores: list[float], template: str) -> tuple[float, float]:
    """상위 항목의 점수 분포로 영향도 경계를 정한다.

    점수는 최고점을 100으로 환산한 상대값이라, 고정 경계(34/67)를 쓰면
    대부분 아래쪽 칸에 몰린다. 그래서 이번 백로그 안에서의 분위수로 나눈다.
    고정값을 쓰고 싶으면 use_relative=False 로 호출한다.
    """
    live = sorted(s for s in scores if s > 0)
    if len(live) < 3:
        return IMPACT_SPLIT_2 if template == "impact_effort" else IMPACT_BANDS_3[0], IMPACT_BANDS_3[1]
    if template == "impact_effort":
        mid = live[len(live) // 2]
        return mid, mid
    low = live[len(live) // 3]
    high = live[len(live) * 2 // 3]
    return low, max(high, low + 0.1)


def _impact_band(score: float, template: str, bands: tuple[float, float] | None = None) -> str:
    low, high = bands or (
        (IMPACT_SPLIT_2, IMPACT_SPLIT_2) if template == "impact_effort" else IMPACT_BANDS_3
    )
    if template == "impact_effort":
        return "HIGH" if score >= low else "LOW"
    if score < low:
        return "LOW"
    if score < high:
        return "MEDIUM"
    return "HIGH"


def _effort_band(hours: float, template: str) -> str:
    if template == "impact_effort":
        return "LOW" if hours <= EFFORT_SPLIT_2 else "HIGH"
    return _band(hours, EFFORT_BANDS_3)


def _pyramid_tier(rank: int) -> str:
    first, second, third = PYRAMID_TIERS
    if rank <= first:
        return "P1-ALL"
    if rank <= second:
        return "P2-ALL"
    if rank <= third:
        return "P3-ALL"
    return "P4-ALL"


def build_stickers(result: PriorityResult, df: pd.DataFrame, template: str,
                   relative_impact: bool = True,
                   include_excluded: bool = False) -> list[dict]:
    """AI 결과를 보드 위의 스티커로 바꾼다. 처음 위치는 점수와 공수로 정해진다."""
    effort_by_id = {str(r["id"]): float(r["effort_hours"]) for _, r in df.iterrows()}
    stickers: list[Sticker] = []

    bands = (
        impact_thresholds([i.score for i in result.top_items], template)
        if relative_impact else None
    )

    for item in result.top_items:
        effort = effort_by_id.get(item.item_id, 40.0)
        if template == "pyramid":
            cell = _pyramid_tier(item.rank)
        else:
            cell = f"{_impact_band(item.score, template, bands)}-{_effort_band(effort, template)}"
        stickers.append(Sticker(
            id=item.item_id, title=item.title, kpi=item.kpi, score=item.score,
            effort_hours=effort, ai_rank=item.rank, cell=cell, reason=item.reason,
        ))

    # 제외 항목은 기본적으로 올리지 않는다. 보드가 길어져서 한눈에 안 들어온다.
    # 켜면 "뺀 이유"를 보고 되살릴 수 있다.
    if not include_excluded:
        return [asdict(s) for s in stickers]

    start = len(stickers) + 1
    for offset, item in enumerate(result.excluded):
        effort = effort_by_id.get(item.item_id, 40.0)
        cell = "P4-ALL" if template == "pyramid" else f"LOW-{_effort_band(effort, template)}"
        stickers.append(Sticker(
            id=item.item_id, title=item.title, kpi="(제외)", score=0.0,
            effort_hours=effort, ai_rank=start + offset, cell=cell, reason=item.reason,
        ))

    return [asdict(s) for s in stickers]


def initial_layout(stickers: list[dict], template: str) -> dict[str, list[str]]:
    """셀별 스티커 id 목록. 셀 안에서는 처음 순위대로."""
    layout: dict[str, list[str]] = {key: [] for key in TEMPLATES[template]["order"]}
    for s in sorted(stickers, key=lambda x: x["ai_rank"]):
        layout.setdefault(s["cell"], []).append(s["id"])
    return layout


def layout_to_ranking(layout: dict[str, list[str]], stickers: list[dict],
                      template: str) -> pd.DataFrame:
    """사람이 옮긴 보드를 다시 순위표로 바꾼다."""
    order = TEMPLATES[template]["order"]
    notes = TEMPLATES[template]["cell_notes"]
    by_id = {s["id"]: s for s in stickers}

    rows = []
    for cell in sorted(layout.keys(), key=lambda c: order.get(c, 99)):
        for position, item_id in enumerate(layout[cell]):
            s = by_id.get(item_id)
            if s is None:
                continue
            rows.append({
                "id": item_id,
                "항목": s["title"],
                "칸": f"{cell} · {notes.get(cell, '')}",
                "연결 KPI": s["kpi"],
                "공수(H)": s["effort_hours"],
                "처음 순위": s["ai_rank"],
                "점수": s["score"],
                "_cell_order": order.get(cell, 99),
                "_pos": position,
            })

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows).sort_values(["_cell_order", "_pos"]).reset_index(drop=True)
    out.insert(0, "최종 순위", range(1, len(out) + 1))
    return out.drop(columns=["_cell_order", "_pos"])


def compare_ranking(final_df: pd.DataFrame, top_n: int = 10) -> dict:
    """처음 순위와 사람이 조정한 순위가 얼마나 다른지."""
    if final_df.empty:
        return {"moved": 0, "same_rank": 0, "total": 0, "agreement": 0.0}

    head = final_df.head(top_n)
    same_rank = int((head["최종 순위"] == head["처음 순위"]).sum())
    moved = int((head["최종 순위"] != head["처음 순위"]).sum())
    ai_top = set(final_df.nsmallest(top_n, "처음 순위")["id"])
    final_top = set(head["id"])
    overlap = len(ai_top & final_top)
    return {
        "moved": moved,
        "same_rank": same_rank,
        "total": len(head),
        "agreement": overlap / max(len(final_top), 1) * 100,
    }


def compare_with_ai(final_df: pd.DataFrame, ai_result: PriorityResult, top_n: int = 10) -> dict:
    """사람이 정한 순위를 AI 순위와 견준다. changes 는 AI 와 순위가 다른 상위 항목."""
    if final_df.empty:
        return {"same_rank": 0, "different": 0, "total": 0, "agreement": 0.0, "changes": []}

    ai_rank = {i.item_id: i.rank for i in ai_result.top_items}
    head = final_df.head(top_n)
    changes = [
        {"id": r["id"], "title": r["항목"], "mine": int(r["최종 순위"]), "ai": ai_rank.get(r["id"])}
        for _, r in head.iterrows()
        if ai_rank.get(r["id"]) != int(r["최종 순위"])
    ]
    overlap = len(set(head["id"]) & set(list(ai_rank)[:top_n]))
    return {
        "same_rank": len(head) - len(changes),
        "different": len(changes),
        "total": len(head),
        "agreement": overlap / max(len(head), 1) * 100,
        "changes": changes,
    }
