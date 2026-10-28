"""업로드된 CSV 읽기.

한국 엑셀에서 'CSV (쉼표로 분리)' 로 저장하면 CP949 로 저장된다.
UTF-8 만 시도하면 그 파일은 '읽을 수 없음' 으로 실패하므로 차례로 시도한다.
"""
from __future__ import annotations

import io

import pandas as pd

# utf-8-sig 는 BOM 이 있든 없든 UTF-8 을 읽는다. cp949 는 euc-kr 을 포함한다.
ENCODINGS = ("utf-8-sig", "cp949")


def read_uploaded_csv(uploaded) -> pd.DataFrame:
    """Streamlit 업로드 파일(또는 바이트)을 DataFrame 으로. 모든 인코딩이 실패하면 마지막 오류를 올린다."""
    raw = uploaded.getvalue() if hasattr(uploaded, "getvalue") else bytes(uploaded)
    last_error: Exception | None = None
    for encoding in ENCODINGS:
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError("파일 인코딩을 알아볼 수 없습니다. UTF-8 또는 엑셀 CSV 로 저장해 주세요.") from last_error
