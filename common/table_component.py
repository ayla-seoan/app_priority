"""행마다 삭제 버튼이 있는 편집 표를 Streamlit 에 붙이는 얇은 래퍼.

React 빌드 없이, components/table_editor/index.html 을 그대로 띄운다.
st.data_editor 는 칸 안에 버튼을 넣을 수 없어서 따로 만들었다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit.components.v1 as components

_DIR = Path(__file__).resolve().parent.parent / "components" / "table_editor"
_component = components.declare_component("table_editor", path=str(_DIR))


def table_editor(frame: pd.DataFrame, columns: dict[str, dict], key: str,
                 add_label: str = "+ 행 추가", empty_text: str = "아직 항목이 없습니다.",
                 max_rows: int | None = None) -> pd.DataFrame:
    """표를 그리고, 사용자가 고친 결과를 같은 컬럼의 DataFrame 으로 돌려준다.

    columns: 컬럼 이름 -> {"label", "type": "text"|"number", "align", "width"}.
             여기에 없는 컬럼(업로드 파일의 추가 컬럼)은 이름 그대로 글자 칸으로 보인다.
    max_rows: 이 줄 수를 넘으면 표 안에서 스크롤한다. 없으면 높이 420px 를 넘을 때 스크롤한다.
    표 내용을 통째로 바꾸려면(샘플 불러오기 등) key 를 바꿔 새 표를 띄운다.
    """
    spec = [{"key": col, "label": col, "type": "text", **columns.get(col, {})} for col in frame.columns]
    # to_json 을 거쳐 NaN -> null, numpy 숫자 -> 일반 숫자로 바꾼다
    rows = json.loads(frame.to_json(orient="records", force_ascii=False))
    value = _component(columns=spec, rows=rows, add_label=add_label, empty_text=empty_text,
                       max_rows=max_rows, key=key, default=None)
    if not value or "rows" not in value:
        return frame
    return pd.DataFrame(value["rows"], columns=list(frame.columns))
