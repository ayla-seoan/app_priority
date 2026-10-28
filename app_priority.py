"""주제 1 — KPI 기반 백로그 우선순위 생성기.

핵심 흐름 하나:
    [입력 화면] KPI·백로그·가용 공수(H) 등록 → [결과 화면] 가용 공수 안에 담은 우선순위 + 근거 + 뺀 항목
실행:  streamlit run app_priority.py
"""
from __future__ import annotations

import html
import random
from urllib.parse import quote
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from common import ai, board, csvio, guard, priority, ui
from common.board_component import priority_board
from common.table_component import table_editor
from common.schema import PriorityResult

load_dotenv()

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "samples" / "backlog_sample.csv"

st.set_page_config(page_title="Priority Buddy", page_icon="📋", layout="wide")

DEFAULT_KPIS = [
    {"name": "해지율 감소", "weight": 40, "keywords": "해지 이탈 방어 유지 재가입 만족도"},
    {"name": "신규 가입 전환", "weight": 35, "keywords": "가입 전환 퍼널 신청 프로모션 마케팅"},
    {"name": "운영 비용 절감", "weight": 25, "keywords": "자동화 수기 배치 집계 리포트 상담 문의"},
]

# 업로드 양식: 필수 컬럼 + 작성 예시 2행
TEMPLATE = pd.DataFrame([
    {"id": "B-001", "title": "예시) 렌탈 계약 전자서명 도입",
     "description": "무엇을 왜 하는지 한두 문장으로 적어 주세요", "effort_hours": 96, "requester": "영업팀"},
    {"id": "B-002", "title": "예시) 설치기사 일정 자동 배정",
     "description": "effort_hours 는 예상 공수(H, 시간)이며 0보다 큰 숫자여야 합니다", "effort_hours": 120, "requester": "운영팀"},
])

# 결과 화면 마우스 커서로 쓸 동물
CURSOR_ANIMALS = ["🐿️", "🐶", "🐱", "🐰", "🐹", "🐼", "🐨", "🦊", "🐻", "🐥", "🐧", "🦔"]

# 직접 입력을 시작할 때의 빈 백로그
# KPI 는 비어 있는 상태로 시작하고, 샘플 버튼을 누르면 DEFAULT_KPIS 가 들어간다
EMPTY_KPIS = pd.DataFrame({
    "name": pd.Series(dtype="object"),
    "weight": pd.Series(dtype="float"),
    "keywords": pd.Series(dtype="object"),
})

EMPTY_BACKLOG = pd.DataFrame({
    "id": pd.Series(dtype="object"),
    "title": pd.Series(dtype="object"),
    "description": pd.Series(dtype="object"),
    "effort_hours": pd.Series(dtype="float"),
    "requester": pd.Series(dtype="object"),
})

# 표 컴포넌트(common/table_component.py) 컬럼 사양. 숫자 칸은 가운데 정렬
KPI_COLUMNS = {
    "name": {"label": "KPI 이름", "width": "30%"},
    "weight": {"label": "가중치", "type": "number", "align": "center", "width": "90px"},
    "keywords": {"label": "연관 키워드"},
}
BACKLOG_COLUMNS = {
    "id": {"label": "id", "width": "84px"},
    "title": {"label": "제목", "width": "24%"},
    "description": {"label": "설명"},
    "effort_hours": {"label": "공수(H)", "type": "number", "align": "center", "width": "90px"},
    "requester": {"label": "요청 부서", "width": "110px"},
}

# 화면이 바뀌면 표 위젯 상태가 사라지므로, 편집한 내용은 *_base 에 따로 보관한다.
# 내용을 통째로 바꿀 때는 *_ver 를 올려 표를 새로 그린다.
ss = st.session_state
ss.setdefault("page", "input")
ss.setdefault("kpi_base", EMPTY_KPIS.copy())
ss.setdefault("kpi_ver", 0)
ss.setdefault("backlog_base", EMPTY_BACKLOG.copy())
ss.setdefault("backlog_ver", 0)
ss.setdefault("run_id", 0)

ui.inject_theme()

if ss["page"] == "result":
    # 결과 화면 마우스 커서: 화면이 다시 그려질 때마다(버튼 클릭 등) 동물이 무작위로 바뀐다
    animal = random.choice(CURSOR_ANIMALS)
    cursor_svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='32' height='32'>"
        f"<text x='0' y='26' font-size='26'>{animal}</text></svg>"
    )
    st.markdown(
        "<style>.stApp, .stApp * { cursor: url(\"data:image/svg+xml;utf8,"
        f"{quote(cursor_svg)}\") 4 4, auto !important; }}</style>",
        unsafe_allow_html=True,
    )


def drop_blank_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """표에서 추가만 하고 비워 둔 행을 뺀다."""
    blank = frame.apply(lambda r: all(pd.isna(x) or str(x).strip() == "" for x in r), axis=1)
    return frame[~blank].reset_index(drop=True)


def editable_table(base_key: str, ver_key: str, columns: dict, empty_text: str,
                   max_rows: int | None = None) -> pd.DataFrame:
    """행마다 삭제 버튼이 있는 편집 표. 남은(빈 행은 뺀) 표를 돌려준다."""
    edited = table_editor(ss[base_key], columns, key=f"{base_key}_table_{ss[ver_key]}",
                          empty_text=empty_text, max_rows=max_rows)
    return drop_blank_rows(edited)


def is_new_file(uploaded, state_key: str) -> bool:
    """같은 업로드 파일을 매 실행마다 다시 읽어 편집 내용을 덮어쓰지 않도록."""
    if uploaded is None or ss.get(state_key) == uploaded.file_id:
        return False
    ss[state_key] = uploaded.file_id
    return True


# ================================================================= 입력 화면
if ss["page"] == "input":
    with st.container(key="pb-topbar"):
        top_l, top_r = st.columns([3, 1])
        with top_l:
            ui.brand(
                "Priority Buddy", "무엇부터 할지, 이제 고민하지 마세요",
                "PM/PO의 의사결정을 도와주는 똑똑한 우선순위 버디",
            )
        with top_r:
            st.caption(f"AI 비교 프롬프트 버전: `{ai.load_prompt('priority')[1]}`")

    # 왼쪽은 KPI 카드, 오른쪽은 준비 상태(강조 카드)와 팁. 준비 상태는 아래에서 검증한 뒤 채운다.
    kpi_col, side_col = st.columns([7, 3], gap="medium")

    # ------------------------------------------------------------- KPI
    with kpi_col, st.container(key="pb-card-kpi"):
        st.subheader("1. 이번 분기 KPI")
        st.caption("표에서 칸을 눌러 바로 고칠 수 있습니다. 행 왼쪽 삭제 버튼으로 지우고, + 행 추가로 늘립니다.")
        kpi_a, kpi_b = st.columns([3, 1])
        with kpi_a:
            kpi_file = st.file_uploader("KPI CSV 파일 (필수 컬럼: name, weight / 선택: keywords)", type=["csv"], key="kpi_file")
        with kpi_b:
            use_sample_kpi = st.button(f"샘플 KPI {len(DEFAULT_KPIS)}개", use_container_width=True)
            st.download_button(
                "양식 다운로드",
                pd.DataFrame(DEFAULT_KPIS).to_csv(index=False).encode("utf-8-sig"),
                file_name="kpi_template.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_kpi_template",
            )

        if use_sample_kpi:
            ss["kpi_base"] = pd.DataFrame(DEFAULT_KPIS)
            ss["kpi_ver"] += 1
            st.success(f"샘플 KPI {len(DEFAULT_KPIS)}개를 불러왔습니다.")
        elif is_new_file(kpi_file, "kpi_file_id"):
            try:
                loaded = csvio.read_uploaded_csv(kpi_file)
            except Exception as exc:
                st.error(f"KPI 파일을 읽을 수 없습니다. 파일이 손상되었을 수 있습니다. ({exc})")
            else:
                check = guard.validate_kpis(loaded)
                if check.ok:
                    if "keywords" not in loaded.columns:
                        loaded["keywords"] = ""
                    loaded["keywords"] = loaded["keywords"].fillna("").astype(str)
                    loaded["weight"] = loaded["weight"].astype(float)
                    ss["kpi_base"] = loaded[["name", "weight", "keywords"]]
                    ss["kpi_ver"] += 1
                    st.success(f"KPI {len(loaded)}개를 불러왔습니다.")
                else:
                    st.error("이 KPI 파일은 쓸 수 없어 기존 KPI를 그대로 둡니다.")
                    for err in check.errors:
                        st.write(f"- {err}")

        kpi_df = editable_table("kpi_base", "kpi_ver", KPI_COLUMNS,
                                "아직 KPI가 없습니다. 오른쪽 위 샘플 KPI 버튼을 누르거나, 아래 + 행 추가로 직접 입력하세요.", max_rows=5)

    # ------------------------------------------------------------- 백로그
    with st.container(key="pb-card-backlog"):
        st.subheader("2. 백로그 등록")
        col_a, col_b = st.columns([3, 1])
        with col_a:
            uploaded = st.file_uploader(
                "CSV 파일 (필수 컬럼: id, title, description, effort_hours)", type=["csv"], key="backlog_file"
            )
        with col_b:
            use_sample = st.button("샘플 35건 불러오기", use_container_width=True)
            st.download_button(
                "양식 다운로드",
                TEMPLATE.to_csv(index=False).encode("utf-8-sig"),
                file_name="backlog_template.csv",
                mime="text/csv",
                use_container_width=True,
                key="dl_template",
                help="필수 컬럼과 작성 예시 2행이 들어 있습니다. 예시 행은 지우고 작성하세요.",
            )

        if use_sample:
            ss["backlog_base"] = pd.read_csv(SAMPLE)
            ss["backlog_ver"] += 1
            st.success(f"샘플 백로그 {len(ss['backlog_base'])}건을 불러왔습니다.")
        elif is_new_file(uploaded, "backlog_file_id"):
            try:
                ss["backlog_base"], converted = priority.normalize_effort(csvio.read_uploaded_csv(uploaded))
                ss["backlog_ver"] += 1
                if converted:
                    st.info(f"예전 양식(effort_days, 일)이라 하루 {priority.HOURS_PER_DAY}H 로 바꿔 공수(H)로 불러왔습니다.")
                if len(ss["backlog_base"]):
                    st.success(f"백로그 {len(ss['backlog_base'])}건을 불러왔습니다.")
                else:
                    st.warning("파일에 항목이 없습니다. 헤더 아래에 백로그를 한 줄 이상 적어 다시 올려 주세요.")
            except Exception as exc:
                st.error(f"CSV를 읽을 수 없습니다. 파일이 손상되었을 수 있습니다. ({exc})")

        if len(ss["backlog_base"]) == 0:
            st.markdown(
                "#### 아직 등록된 백로그가 없습니다\n"
                "- 오른쪽 위 **샘플 35건 불러오기** 로 바로 시험해 볼 수 있습니다.\n"
                "- 파일로 올리실 경우 **양식 다운로드** 로 받은 파일에 작성해 올려 주세요.\n"
                "- 아래 표에 **직접 입력**해도 됩니다. 표 아래 **+ 행 추가** 를 눌러 항목을 추가하세요."
            )
        else:
            st.caption("올린 백로그를 표에서 바로 고칠 수 있습니다. 행 왼쪽 삭제 버튼으로 지우고, + 행 추가로 늘립니다.")

        backlog_df = editable_table("backlog_base", "backlog_ver", BACKLOG_COLUMNS, "아래 + 행 추가를 눌러 직접 입력할 수 있습니다.")

    # ------------------------------------------------------------- 가용 공수
    # 우선순위 건수를 고르는 대신, 이번 분기에 쓸 수 있는 공수(H)를 먼저 정한다.
    # 점수 순으로 이 시간 안에 들어가는 항목까지 우선순위에 담긴다. 화면을 오가도 유지되도록 ss 에 보관
    total_hours = (
        float(pd.to_numeric(backlog_df["effort_hours"], errors="coerce").fillna(0).sum())
        if "effort_hours" in backlog_df.columns else 0.0
    )
    with st.container(key="pb-card-capacity"):
        st.subheader("3. 가용 공수(H) 정하기")
        cap_a, cap_b = st.columns([1, 2], vertical_alignment="bottom")
        with cap_a:
            capacity_hours = st.number_input(
                "이번 분기 가용 공수(H)", min_value=1, step=8,
                value=int(ss.get("capacity_hours", priority.CAPACITY_HOURS)),
                help="점수가 높은 항목부터 이 시간 안에 들어가는 만큼 우선순위에 담고, "
                     "남은 공수보다 큰 항목은 '이번 분기에 하지 않는 것'으로 보냅니다.",
            )
            ss["capacity_hours"] = int(capacity_hours)
        with cap_b:
            if total_hours:
                st.caption(
                    f"백로그 전체 공수는 **{total_hours:g}H** 입니다. "
                    + ("가용 공수가 더 커서 모든 항목이 우선순위에 담깁니다."
                       if capacity_hours >= total_hours
                       else f"그중 **{int(capacity_hours)}H** 안에 들어가는 항목을 점수 순으로 담습니다.")
                )
            else:
                st.caption("백로그를 등록하면 전체 공수와 비교해 볼 수 있어요. 예) 3명 × 4주 × 40H = 480H")

    # ------------------------------------------------------------- 검증
    kpi_check = guard.validate_kpis(kpi_df)
    backlog_check = guard.validate_backlog(backlog_df) if len(backlog_df) else None
    if backlog_check:
        for warning in backlog_check.warnings:
            st.warning(warning)

    problems = [f"KPI: {e}" for e in kpi_check.errors]
    if backlog_check is None:
        problems.append("백로그: 한 건 이상 등록해 주세요.")
    else:
        problems += [f"백로그: {e}" for e in backlog_check.errors]

    # ------------------------------------------------------------- 실행
    st.write("")
    _, btn_col, _ = st.columns([2, 1, 2])
    # 준비가 덜 됐어도 버튼은 눌리게 둔다(흐리게만 보임). 누르면 만들지 않고 준비 상태로 올려 빠진 것을 빨갛게 보여준다
    with btn_col, st.container(key="pb-generate-blocked" if problems else "pb-generate-ready"):
        generate = st.button("우선순위 만들기", type="primary", key="generate", use_container_width=True)
    if not problems:
        ss["ready_alert"] = False
    elif generate:
        ss["ready_alert"] = True
        ss["ready_alert_n"] = ss.get("ready_alert_n", 0) + 1
        ui.scroll_to(".pb-dark", ss["ready_alert_n"])

    # ------------------------------------------------------------- 준비 상태
    with side_col:
        if problems:
            status = "<br>".join(f"· {html.escape(p)}" for p in problems)
            if ss.get("ready_alert"):
                status = f'<span class="pb-alert"><b>아직 만들 수 없어요. 아래를 채워 주세요.</b><br>{status}</span>'
        else:
            status = "<b>준비 완료!</b> 아래 버튼을 누르면 버디가 순위를 골라 드려요."
        ui.dark_card(
            "준비 상태",
            '<div class="pb-dark-big pb-dark-stats">'
            f'<span>{len(kpi_df)}<small>개의 KPI</small></span>'
            f'<span>{len(backlog_df)}<small>건의 백로그</small></span></div>',
            f"가용 공수 {int(capacity_hours)}H<br>{status}",
        )
        st.write("")
        with st.container(key="pb-card-tip"):
            st.markdown("#### 버디의 팁")
            st.caption(
                "가중치는 합이 100이 아니어도 괜찮아요. KPI끼리의 상대적인 크기만 봅니다. "
                "연관 키워드를 채워 두면 AI 없이 계산할 때도 KPI 연결이 정확해져요."
            )

    if generate and not problems:
        kpis = [
            {"name": str(r["name"]).strip(), "weight": float(r["weight"]),
             "keywords": "" if pd.isna(r.get("keywords")) else str(r.get("keywords"))}
            for _, r in kpi_df.iterrows()
        ]
        # 처음 순위는 규칙 기반으로 바로 만든다. AI 는 결과 화면의 'AI 결과와 비교하기' 에서만 부른다
        ss["result"] = priority.rule_based(backlog_df, kpis, ss["capacity_hours"])
        ss["run_df"] = backlog_df
        ss["run_kpis"] = kpis
        ss["run_capacity"] = ss["capacity_hours"]
        # 비교 보고서는 가용 공수 안에 담긴 건수만큼을 상위로 본다
        ss["run_top_n"] = max(len(ss["result"].top_items), 1)
        ss["run_id"] += 1
        # 홈으로 돌아왔을 때 편집하던 내용을 그대로 보여주기 위해 보관
        ss["kpi_base"], ss["backlog_base"] = kpi_df, backlog_df
        ss["kpi_ver"] += 1
        ss["backlog_ver"] += 1
        ss["page"] = "result"
        st.rerun()
    st.stop()

# ================================================================= 결과 화면
result: PriorityResult | None = ss.get("result")
if not isinstance(result, PriorityResult):
    ss["page"] = "input"
    st.rerun()

df: pd.DataFrame = ss["run_df"]
kpis: list[dict] = ss["run_kpis"]
capacity_hours: int = ss.get("run_capacity", priority.CAPACITY_HOURS)
top_n: int = ss.get("run_top_n", 1)

with st.container(key="pb-topbar"):
    top_l, top_r = st.columns([5, 1])
    with top_l:
        ui.brand(
            "짜잔! 지금 가장 먼저 할 일은?",
            "KPI와 백로그를 분석해서 지금 가장 임팩트 있는 업무를 골라봤어요 🐿️",
        )
    with top_r:
        if st.button("🏠 홈으로", use_container_width=True):
            ss["page"] = "input"
            st.rerun()

# TOP 5 를 넓은 왼쪽에 크게, 안내 카드는 오른쪽에 작게
top_col, list_col = st.columns([7, 3], gap="medium")
with list_col, st.container(key="pb-card-list"):
    st.subheader("Your Priority List")
    st.markdown("지금 집중해야 할 업무")
    st.caption("목표 달성에 미치는 영향과 실행 우선순위를 확인해 보세요")
    ui.chips([
        (f"KPI {len(kpis)}개", ""),
        (f"백로그 {len(df)}건", ""),
        (f"공수 {priority.selected_hours(result, df):g} / {capacity_hours}H · {len(result.top_items)}건", ""),
        ("규칙 기반 계산", "fallback"),
    ])
    st.caption("KPI나 백로그를 고치려면 홈으로 돌아가세요. AI 순위는 아래 'AI 결과와 비교하기'에서 볼 수 있어요.")

with top_col:
    if result.top_items:
        # 한 줄씩: 순위 · 제목 · 점수. 연결 KPI 는 마우스를 올리면 보인다
        rows = "".join(
            f'<li title="{html.escape(item.kpi)} 연결">'
            f'<span class="pb-top-rank">{item.rank}</span>'
            f'<span class="pb-top-title">{html.escape(item.title)}</span>'
            f'<span class="pb-top-score">{item.score:.0f}</span></li>'
            for item in result.top_items[:5]
        )
        ui.dark_card("우선순위 TOP 5", f'<ol class="pb-top">{rows}</ol>', large=True)
    else:
        ui.dark_card("우선순위 TOP 5", '<div class="pb-dark-title">아직 뽑힌 항목이 없어요</div>',
                     "가용 공수(H)가 가장 작은 항목보다 적을 수 있어요. 홈에서 가용 공수를 늘리거나 "
                     "KPI 키워드·백로그 설명을 보강한 뒤 다시 만들어 보세요.", large=True)

# ----------------------------------------------------------------- 보드
st.write("")
with st.container(key="pb-card-board"):
    st.subheader("보드에서 직접 조정하기")
    template_key = st.radio(
        "보드 템플릿",
        options=list(board.TEMPLATES.keys()),
        format_func=lambda k: board.TEMPLATES[k]["label"],
        horizontal=True,
        key="template_key",
    )
    tpl = board.TEMPLATES[template_key]

    opt1, opt2 = st.columns(2)
    with opt1:
        show_excluded = st.checkbox(
            "제외 항목도 보드에 올리기", value=False,
            help="켜면 이번 분기에 빼기로 한 항목까지 보입니다. 되살리려면 위 칸으로 옮기세요.",
        )
    with opt2:
        relative = st.checkbox(
            "영향도를 이번 백로그 안에서 상대 평가", value=True,
            help="끄면 점수 34/67 고정 경계를 씁니다. 그러면 대부분 아래 칸에 몰릴 수 있습니다. "
                 "피라미드는 점수 대신 처음 순위로 단을 나눠 이 설정을 쓰지 않습니다.",
            disabled=template_key == "pyramid",
        )

    stickers = board.build_stickers(
        result, df, template_key,
        relative_impact=relative, include_excluded=show_excluded,
    )
    # run_id 를 넣어 새로 계산할 때마다 보드 배치를 새 결과로 시작한다
    state_key = f"layout::{ss['run_id']}::{template_key}::{show_excluded}::{relative}"
    if state_key not in st.session_state:
        st.session_state[state_key] = board.initial_layout(stickers, template_key)

    c1, c2 = st.columns([1, 5])
    with c1:
        if st.button("처음 배치로 되돌리기", use_container_width=True):
            st.session_state[state_key] = board.initial_layout(stickers, template_key)
            st.rerun()

    # 스티커를 옮기면 보드가 새 배치를 보내며 다시 실행된다. 그 배치를 보드를 그리기 *전에* 반영해야
    # 옮긴 자리가 그대로 남는다. 그리고 나서 반영하면 보드가 옛 배치를 받아 스티커가 되돌아가 두 번 옮겨야 했다.
    # 같은 이동(at)을 두 번 반영하지 않아야 '처음 배치로 되돌리기' 뒤에 예전 이동이 되살아나지 않는다.
    board_key = f"board::{state_key}"
    moved = st.session_state.get(board_key)
    if (isinstance(moved, dict) and moved.get("layout")
            and moved.get("at") != st.session_state.get(f"{board_key}::applied")):
        st.session_state[state_key] = moved["layout"]
        st.session_state[f"{board_key}::applied"] = moved.get("at")

    priority_board(
        template={
            "rows": tpl["rows"], "cols": tpl["cols"], "order": tpl["order"],
            "cell_notes": tpl["cell_notes"], "x_axis": tpl["x_axis"], "y_axis": tpl["y_axis"],
            "shape": tpl.get("shape", "grid"),
        },
        stickers=stickers,
        layout=st.session_state[state_key],
        key=board_key,
        cursor=animal,
        file_name=f"board_{template_key}",
    )

    final_df = board.layout_to_ranking(st.session_state[state_key], stickers, template_key)

    if final_df.empty:
        st.info("보드에 올라간 항목이 없습니다.")
    else:
        # 보드 안 이미지 버튼(board_<템플릿>.png)과 같은 이름으로, 지금 보드 배치 그대로
        st.download_button(
            "📄 보드 CSV 내려받기",
            final_df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"board_{template_key}.csv",
            mime="text/csv",
            key=f"dl_board_{template_key}",
            help="보드에 보이는 배치 그대로 칸·최종 순위가 담깁니다. 이미지는 보드 오른쪽 위 버튼으로 받으세요.",
        )

# ----------------------------------------------------------------- 원본 vs 조정 비교
# 화면에는 네 컬럼만, CSV 에는 전체 컬럼을 담는다
VIEW_COLUMNS = ["순위", "id", "항목"]
# 순위 칸은 좁게, 가운데 정렬. 표가 남는 폭을 칸마다 나눠 주므로 다른 칸 폭도 정해 항목 칸이 넓게 받게 한다
VIEW_CONFIG = {
    "순위": st.column_config.NumberColumn("순위", width=56, alignment="center"),
    "id": st.column_config.TextColumn("id", width=76),
    "항목": st.column_config.TextColumn("항목", width=360),
}
# 내가 조정한 결과 표에서 AI 와 순위가 다른 행 (테마 코랄을 옅게)
CHANGED_ROW_STYLE = "background-color: #FCE3DC; color: #2E3359"


def comparison_csv(ai_df: pd.DataFrame, final_df: pd.DataFrame) -> bytes:
    """AI 원본과 조정 결과를 순위별로 나란히 붙인 CSV. 두 결과의 컬럼을 모두 담는다."""
    left = ai_df.add_prefix("AI 원본 ").reset_index(drop=True)
    right = final_df.rename(columns={"최종 순위": "순위"}).add_prefix("내가 조정 ").reset_index(drop=True)
    both = pd.concat([left, right], axis=1)
    if "AI 원본 id" in both and "내가 조정 id" in both:
        same = both["AI 원본 id"].notna() & (both["AI 원본 id"] == both["내가 조정 id"])
        both.insert(0, "같은 순위", same.map({True: "O", False: ""}))
    return both.to_csv(index=False).encode("utf-8-sig")


def change_table(changes: list[dict]) -> pd.DataFrame:
    """AI 와 순위가 다른 항목 표. 변화는 AI 순위보다 올렸으면 ▲, 내렸으면 ▼."""
    rows = []
    for c in changes:
        if c["ai"] is None:
            move = "새로 올림"
        else:
            gap = c["ai"] - c["mine"]
            move = f"▲ {gap}" if gap > 0 else f"▼ {-gap}"
        rows.append({
            "id": c["id"], "항목": c["title"],
            "AI 순위": f"{c['ai']}위" if c["ai"] else "상위 밖",
            "내 순위": f"{c['mine']}위", "변화": move,
        })
    return pd.DataFrame(rows)


# 표 높이: 제목 줄 + 최대 3행. 그보다 많으면 표 안에서 스크롤
CHANGE_ROWS_VISIBLE = 3
ROW_PX = 35


# 보드를 옮길 때마다 보고서가 흔들리지 않도록, 버튼을 누른 순간의 보드로 보고서를 만든다
st.write("")
_, cmp_col, _ = st.columns([2, 1, 2])
with cmp_col:
    compare_clicked = st.button("🔍 AI 결과와 비교하기", type="primary", use_container_width=True, key="compare_btn")
if compare_clicked:
    # 같은 계산(run_id)에서는 AI 를 한 번만 부르고, 다시 누르면 보드만 새로 찍는다
    if ss.get("ai_run_id") != ss["run_id"]:
        with st.spinner("AI가 우선순위를 매기는 중..."):
            ss["ai_meta"] = ai.call_structured(
                prompt_name="priority",
                user_content=priority.build_user_content(df, kpis, capacity_hours),
                schema=PriorityResult,
                fallback=lambda: priority.rule_based(df, kpis, capacity_hours),
            )
            # 스키마는 통과해도 가용 공수를 넘겨 담았으면 틀린 결과로 보고 규칙 기반으로 바꾼다
            meta = ss["ai_meta"]
            over = priority.selected_hours(meta.data, df)
            if meta.source == "ai" and over > capacity_hours:
                ss["ai_meta"] = ai.AIResult(
                    ok=True, data=priority.rule_based(df, kpis, capacity_hours), source="fallback",
                    error=f"AI가 가용 공수 {capacity_hours}H 를 넘겨 {over:g}H 를 담음",
                    elapsed_ms=meta.elapsed_ms, prompt_version=meta.prompt_version, attempts=meta.attempts,
                )
        ss["ai_run_id"] = ss["run_id"]
    ss["compare_snapshot"] = {"run_id": ss["run_id"], "template": template_key, "final_df": final_df.copy()}

snapshot = ss.get("compare_snapshot")
if not snapshot or snapshot["run_id"] != ss["run_id"]:
    st.caption("보드를 다 옮긴 뒤 위 버튼을 누르면 AI 원본과 비교한 보고서가 여기에 나옵니다.")
    st.write("")
    if st.button("🏠 홈으로", key="home_bottom"):
        ss["page"] = "input"
        st.rerun()
    st.stop()

report_df: pd.DataFrame = snapshot["final_df"]
ai_meta: ai.AIResult = ss["ai_meta"]
ai_df = priority.to_dataframe(ai_meta.data)
st.write("")
with st.container(key="pb-card-compare"):
    st.subheader("AI 원본 결과 vs 내가 조정한 결과")
    st.caption(f"‘AI 결과와 비교하기’를 누른 순간의 보드({board.TEMPLATES[snapshot['template']]['label']}) 기준입니다.")
    if snapshot["template"] != template_key or not report_df.equals(final_df):
        st.info("보드가 그 뒤로 바뀌었어요. 바뀐 배치로 보려면 ‘AI 결과와 비교하기’를 다시 눌러 주세요.")
    if ai_meta.source == "fallback":
        st.warning(f"AI 호출이 실패해 AI 순위 대신 규칙 기반 순위로 비교했습니다. ({ai_meta.error})")

    # ---------- 요약
    st.markdown("#### 요약")
    if report_df.empty:
        st.info("보드에 올라간 항목이 없습니다. 보드에 스티커를 올린 뒤 다시 비교해 주세요.")
    else:
        diff = board.compare_with_ai(report_df, ai_meta.data, top_n)
        if diff["different"] == 0:
            st.markdown(f"내 상위 {diff['total']}건의 순위가 AI 순위와 **모두 같습니다.**")
        else:
            st.markdown(
                f"내 상위 {diff['total']}건 중 **{diff['different']}건이 AI와 순위가 다르고**, "
                f"{diff['same_rank']}건은 같습니다. "
                f"내 상위 {diff['total']}건은 AI 상위 {top_n}건과 **{diff['agreement']:.0f}%** 겹칩니다."
            )
        # 요약 문장 바로 아래에 어떤 항목이 달라졌는지 보여준다
        if diff["changes"]:
            st.markdown(f"##### AI와 순위가 다른 항목 ({len(diff['changes'])}건)")
            shown = min(len(diff["changes"]), CHANGE_ROWS_VISIBLE)
            st.dataframe(
                change_table(diff["changes"]), use_container_width=True, hide_index=True,
                height=ROW_PX * (shown + 1) + 3,
                column_config={
                    "id": st.column_config.TextColumn("id", width=76),
                    "항목": st.column_config.TextColumn("항목", width=360),
                },
            )
            if len(diff["changes"]) > CHANGE_ROWS_VISIBLE:
                st.caption("표 안에서 스크롤하면 나머지 항목을 볼 수 있어요.")
        d1, d2, d3 = st.columns(3)
        d1.metric("AI와 순위가 다른 항목", f"{diff['different']} / {diff['total']}")
        d2.metric("AI와 순위가 같은 항목", f"{diff['same_rank']} / {diff['total']}")
        d3.metric(f"AI 상위 {top_n}건과 겹침", f"{diff['agreement']:.0f}%")
        st.caption("AI가 뽑은 순위와 내가 정한 순위가 얼마나 다른지. 발표에서 'AI를 어디까지 따랐는가'의 근거가 됩니다.")

    # ---------- 순위표
    st.markdown("#### 순위표 비교")
    left, right = st.columns(2)
    with left:
        st.markdown("##### AI 원본")
        st.caption(f"산출 경로: {ai_meta.badge}")
        st.dataframe(ai_df[VIEW_COLUMNS], use_container_width=True, hide_index=True, column_config=VIEW_CONFIG)
        st.download_button(
            "AI 원본 CSV 내려받기",
            ai_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="priority_result.csv",
            mime="text/csv",
            key="dl_ai",
        )
    with right:
        st.markdown("##### 내가 조정한 결과")
        st.caption("보드에서 옮긴 배치를 반영한 순위")
        if report_df.empty:
            st.info("보드에 올라간 항목이 없습니다.")
        else:
            # 요약의 'AI와 순위가 다른 항목' 과 같은 행만 코랄색으로 칠한다
            changed_ids = {c["id"] for c in diff["changes"]}
            mine = report_df.rename(columns={"최종 순위": "순위"})[VIEW_COLUMNS]
            st.dataframe(
                mine.style.apply(
                    lambda r: [CHANGED_ROW_STYLE if r["id"] in changed_ids else ""] * len(r), axis=1,
                ),
                use_container_width=True, hide_index=True, column_config=VIEW_CONFIG,
            )
            if changed_ids:
                st.caption("색칠한 행은 AI와 순위가 다른 항목입니다.")
            st.download_button(
                "조정 결과 CSV 내려받기",
                report_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="priority_final.csv",
                mime="text/csv",
                key="dl_final",
            )

    st.download_button(
        "📄 두 결과 함께 CSV 내려받기",
        comparison_csv(ai_df, report_df),
        file_name="priority_compare.csv",
        mime="text/csv",
        key="dl_compare",
        help="순위별로 AI 원본과 내가 조정한 결과를 나란히 담고, 두 결과의 모든 컬럼을 포함합니다.",
    )

    # ---------- 제외
    excluded = priority.excluded_dataframe(result)
    st.write("")
    with st.expander(f"이번 분기에 하지 않는 것 ({len(excluded)}건)"):
        if len(excluded):
            st.dataframe(excluded, use_container_width=True, hide_index=True)
        else:
            st.caption("제외된 항목이 없습니다.")

st.write("")
if st.button("🏠 홈으로", key="home_bottom"):
    ss["page"] = "input"
    st.rerun()
