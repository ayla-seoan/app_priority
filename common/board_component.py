"""드래그 보드를 Streamlit 에 붙이는 얇은 래퍼.

React 빌드 없이, components/priority_board/index.html 을 그대로 띄운다.
"""
from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

_DIR = Path(__file__).resolve().parent.parent / "components" / "priority_board"
_component = components.declare_component("priority_board", path=str(_DIR))


def priority_board(template: dict, stickers: list[dict], layout: dict,
                   key: str = "board", cursor: str | None = None,
                   file_name: str = "board") -> dict | None:
    """스티커 보드를 그리고, 사용자가 옮기면 새 배치를 돌려준다.

    cursor 에 이모지를 주면 보드 위 커서와 끄는 동안의 그림이 그 이모지로 바뀐다.
    file_name 은 보드 안 '이미지 내려받기' 버튼이 저장할 PNG 이름(확장자 제외)이다.
    """
    return _component(template=template, stickers=stickers, layout=layout,
                      cursor=cursor, file_name=file_name, key=key, default=None)
