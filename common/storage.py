"""Google Sheets 를 저장소로 쓴다. 키가 없으면 로컬 JSON 으로 자동 전환.

로컬 전환이 있어야 심사자가 README 만 보고 바로 돌려볼 수 있다.
모든 쓰기는 append 로만 하고, 수정·삭제도 새 행을 쌓는다.
=> 마지막 행이 현재 상태, 이전 행이 되돌릴 대상.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LOCAL_DIR = ROOT / "data"

HEADERS = [
    "row_id", "entry_id", "revision", "status", "updated_at",
    "cafe_name", "artist", "address", "lat", "lng",
    "start_date", "end_date", "perks", "goods", "source", "note",
]


class Storage:
    """append-only 저장소. sheets 모드와 local 모드가 같은 인터페이스를 쓴다."""

    def __init__(self, worksheet: str = "cafes") -> None:
        self.worksheet = worksheet
        self.mode = os.getenv("STORAGE_MODE", "local").lower()
        self._ws = None
        if self.mode == "sheets":
            try:
                self._ws = self._open_sheet()
            except Exception as exc:  # 자격증명 문제면 조용히 로컬로
                self.mode = "local"
                self.fallback_reason = str(exc)

    # ------------------------------------------------------------ sheets
    def _open_sheet(self):
        import gspread
        from google.oauth2.service_account import Credentials

        key_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
        sheet_key = os.getenv("GSHEET_KEY")
        if not key_file or not sheet_key:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_FILE 또는 GSHEET_KEY 가 없습니다.")

        creds = Credentials.from_service_account_file(
            key_file,
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        doc = gspread.authorize(creds).open_by_key(sheet_key)
        try:
            ws = doc.worksheet(self.worksheet)
        except Exception:
            ws = doc.add_worksheet(self.worksheet, rows=1000, cols=len(HEADERS))
            ws.append_row(HEADERS)
        if not ws.row_values(1):
            ws.append_row(HEADERS)
        return ws

    # ------------------------------------------------------------- local
    @property
    def _local_path(self) -> Path:
        LOCAL_DIR.mkdir(parents=True, exist_ok=True)
        return LOCAL_DIR / f"{self.worksheet}.json"

    def _read_local(self) -> list[dict]:
        if not self._local_path.exists():
            return []
        return json.loads(self._local_path.read_text(encoding="utf-8"))

    def _write_local(self, rows: list[dict]) -> None:
        self._local_path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # -------------------------------------------------------------- API
    def all_rows(self) -> list[dict]:
        if self.mode == "sheets" and self._ws is not None:
            return self._ws.get_all_records()
        return self._read_local()

    def current_rows(self) -> list[dict]:
        """entry_id 별로 가장 최신 revision 만, 삭제된 건 제외."""
        latest: dict[str, dict] = {}
        for row in self.all_rows():
            eid = str(row.get("entry_id"))
            prev = latest.get(eid)
            if prev is None or int(row.get("revision", 0)) >= int(prev.get("revision", 0)):
                latest[eid] = row
        return [r for r in latest.values() if r.get("status") != "deleted"]

    def append(self, payload: dict[str, Any], entry_id: str | None = None,
               status: str = "active") -> dict:
        """새 등록 또는 수정. 항상 새 행이 쌓인다."""
        rows = self.all_rows()
        entry_id = entry_id or uuid.uuid4().hex[:10]
        revision = max(
            [int(r.get("revision", 0)) for r in rows if str(r.get("entry_id")) == entry_id],
            default=0,
        ) + 1

        record = {k: "" for k in HEADERS}
        record.update(payload)
        record.update({
            "row_id": uuid.uuid4().hex[:10],
            "entry_id": entry_id,
            "revision": revision,
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        for key in ("perks", "goods"):
            if isinstance(record.get(key), list):
                record[key] = ", ".join(record[key])

        if self.mode == "sheets" and self._ws is not None:
            self._ws.append_row([str(record.get(h, "")) for h in HEADERS])
        else:
            rows.append(record)
            self._write_local(rows)
        return record

    def revert(self, entry_id: str) -> dict | None:
        """직전 revision 을 새 행으로 다시 쌓아 되돌린다. 이력은 지우지 않는다."""
        history = sorted(
            [r for r in self.all_rows() if str(r.get("entry_id")) == str(entry_id)],
            key=lambda r: int(r.get("revision", 0)),
        )
        if len(history) < 2:
            return None
        target = history[-2]
        payload = {k: target.get(k, "") for k in HEADERS
                   if k not in ("row_id", "entry_id", "revision", "status", "updated_at")}
        return self.append(payload, entry_id=str(entry_id), status=target.get("status", "active"))

    def soft_delete(self, entry_id: str) -> dict:
        current = next(
            (r for r in self.current_rows() if str(r.get("entry_id")) == str(entry_id)), {}
        )
        payload = {k: current.get(k, "") for k in HEADERS
                   if k not in ("row_id", "entry_id", "revision", "status", "updated_at")}
        return self.append(payload, entry_id=str(entry_id), status="deleted")
