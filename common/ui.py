"""화면 꾸밈: 테마 CSS, 상단 바 브랜드, 강조 카드, 상태 칩.

두 앱이 같은 모양을 쓰도록 여기서만 HTML 조각을 만든다.
사용자가 넣은 글자는 반드시 html.escape 를 거친 뒤 넣는다.
"""
from __future__ import annotations

import html
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

_CSS = Path(__file__).resolve().parent / "static" / "theme.css"

# 버디 마스코트: 민트색 몸통에 배, 볼터치, 웃는 입
MASCOT_SVG = """
<svg width="54" height="54" viewBox="0 0 64 64" aria-hidden="true">
  <path d="M25 13 q3-9 8-3 q4-6 7 3" fill="#4FA893"/>
  <path d="M12 60 C6 40 9 13 32 11 C55 13 58 40 52 60 Z" fill="#5FB8A2"/>
  <ellipse cx="32" cy="46" rx="13" ry="11.5" fill="#B8E3D0"/>
  <circle cx="24.5" cy="29" r="3.4" fill="#2E3359"/>
  <circle cx="39.5" cy="29" r="3.4" fill="#2E3359"/>
  <circle cx="25.6" cy="27.8" r="1.1" fill="#fff"/>
  <circle cx="40.6" cy="27.8" r="1.1" fill="#fff"/>
  <ellipse cx="18.5" cy="35.5" rx="3.6" ry="2.2" fill="#F2A894" opacity=".75"/>
  <ellipse cx="45.5" cy="35.5" rx="3.6" ry="2.2" fill="#F2A894" opacity=".75"/>
  <path d="M27 35.5 q5 6 10 0 Z" fill="#E8836B" stroke="#2E3359" stroke-width="1.8" stroke-linejoin="round"/>
</svg>
"""


# 브라우저 자동 번역(크롬·엣지)이 화면 글자를 바꿔 끼우면, Streamlit(React)이 그 글자를
# 다시 그릴 때 'removeChild / insertBefore' 오류로 빨간 상자를 띄운다. 페이지에 번역 금지를 단다.
_NO_TRANSLATE = """
<script>
  const doc = window.parent.document;
  doc.documentElement.setAttribute("translate", "no");
  doc.documentElement.classList.add("notranslate");
  if (!doc.querySelector('meta[name="google"][content="notranslate"]')) {
    const meta = doc.createElement("meta");
    meta.name = "google";
    meta.content = "notranslate";
    doc.head.appendChild(meta);
  }
</script>
"""


def inject_theme() -> None:
    st.markdown(f"<style>{_CSS.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
    components.html(_NO_TRANSLATE, height=0)


def brand(title: str, subtitle: str, note: str = "") -> None:
    """상단 바 왼쪽: 마스코트 + 제목 + 부제."""
    note_html = f'<div class="pb-brand-note">{html.escape(note)}</div>' if note else ""
    st.markdown(
        f'<div class="pb-brand">{MASCOT_SVG}<div>'
        f'<div class="pb-brand-title">{html.escape(title)}</div>'
        f'<div class="pb-brand-sub">{html.escape(subtitle)}</div>{note_html}'
        "</div></div>",
        unsafe_allow_html=True,
    )


def dark_card(label: str, body_html: str, foot_html: str = "", large: bool = False) -> None:
    """화면마다 하나 두는 네이비 강조 카드. body_html·foot_html 은 호출하는 쪽에서 escape 한다.
    large: 넓은 칸에 둘 때 제목·목록 글자를 키운다."""
    foot = f'<div class="pb-dark-foot">{foot_html}</div>' if foot_html else ""
    cls = "pb-dark pb-dark--large" if large else "pb-dark"
    st.markdown(
        f'<div class="{cls}"><div class="pb-dark-label">{html.escape(label)}</div>{body_html}{foot}</div>',
        unsafe_allow_html=True,
    )


def scroll_to(selector: str, nonce: int) -> None:
    """selector 에 맞는 첫 요소가 화면 가운데 오도록 부드럽게 스크롤한다.
    같은 HTML 이면 Streamlit 이 iframe 을 다시 만들지 않으므로, 누를 때마다 nonce 를 바꿔 넘긴다."""
    components.html(
        f"""<script>
  // nonce {nonce}
  const el = window.parent.document.querySelector({selector!r});
  if (el) el.scrollIntoView({{behavior: "smooth", block: "center"}});
</script>""",
        height=0,
    )


def chips(items: list[tuple[str, str]]) -> None:
    """(글자, 종류) 목록. 종류: "" | "ai" | "fallback"."""
    spans = "".join(
        f'<span class="pb-chip{" pb-chip--" + kind if kind else ""}">{html.escape(text)}</span>'
        for text, kind in items
    )
    st.markdown(f'<div class="pb-chips">{spans}</div>', unsafe_allow_html=True)
