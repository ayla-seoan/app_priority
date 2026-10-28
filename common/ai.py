"""OpenAI 호출 한 곳. 두 앱이 모두 이 함수만 쓴다.

여기서 책임지는 것:
  1. 프롬프트를 파일에서 버전별로 읽어온다 (AI 활용 과정 기록용)
  2. Structured Outputs 로 JSON 스키마를 강제한다
  3. 실패하면 재시도하고, 그래도 안 되면 fallback 으로 넘긴다
  4. 모든 호출을 logs/runs.jsonl 에 남긴다 (프롬프트 버전 비교용)
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parent.parent
PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
LOG_PATH = ROOT / "logs" / "runs.jsonl"

T = TypeVar("T", bound=BaseModel)


@dataclass
class AIResult:
    """AI 호출 결과. 실패해도 앱은 멈추지 않는다."""

    ok: bool
    data: Any = None
    source: str = "ai"          # "ai" | "fallback"
    error: str | None = None
    elapsed_ms: int = 0
    prompt_version: str = ""
    attempts: int = 0

    @property
    def badge(self) -> str:
        """화면에 띄울 신뢰 표시."""
        return "AI 산출" if self.source == "ai" else "규칙 기반 대체"


def load_prompt(name: str, version: str | None = None) -> tuple[str, str]:
    """common/prompts/<name>.<version>.txt 를 읽는다.

    버전을 파일명으로 관리하면 v1 → v3 비교가 git diff 로 남는다.
    """
    version = version or os.getenv("PROMPT_VERSION", "v1")
    path = PROMPT_DIR / f"{name}.{version}.txt"
    if not path.exists():
        raise FileNotFoundError(f"프롬프트 파일이 없습니다: {path}")
    return path.read_text(encoding="utf-8"), version


def _log(record: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def call_structured(
    prompt_name: str,
    user_content: str,
    schema: type[T],
    fallback: Callable[[], T] | None = None,
    version: str | None = None,
    max_attempts: int = 2,
    timeout: float = 45.0,
) -> AIResult:
    """프롬프트 + 사용자 입력 → 스키마를 통과한 객체.

    fallback 을 넘기면 AI 가 끝내 실패해도 규칙 기반 결과를 돌려준다.
    """
    system_prompt, resolved_version = load_prompt(prompt_name, version)
    run_id = uuid.uuid4().hex[:8]
    started = time.monotonic()
    last_error: str | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            parsed = _call_openai(system_prompt, user_content, schema, timeout)
            elapsed = int((time.monotonic() - started) * 1000)
            _log({
                "run_id": run_id,
                "at": datetime.now(timezone.utc).isoformat(),
                "prompt": prompt_name,
                "version": resolved_version,
                "attempt": attempt,
                "ok": True,
                "elapsed_ms": elapsed,
                "input_chars": len(user_content),
            })
            return AIResult(
                ok=True, data=parsed, source="ai", elapsed_ms=elapsed,
                prompt_version=resolved_version, attempts=attempt,
            )
        except (ValidationError, ValueError, RuntimeError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < max_attempts:
                time.sleep(1.5 * attempt)
        except Exception as exc:  # 네트워크·인증·할당량 등
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < max_attempts:
                time.sleep(1.5 * attempt)

    elapsed = int((time.monotonic() - started) * 1000)
    _log({
        "run_id": run_id,
        "at": datetime.now(timezone.utc).isoformat(),
        "prompt": prompt_name,
        "version": resolved_version,
        "attempt": max_attempts,
        "ok": False,
        "error": last_error,
        "elapsed_ms": elapsed,
    })

    if fallback is not None:
        return AIResult(
            ok=True, data=fallback(), source="fallback", error=last_error,
            elapsed_ms=elapsed, prompt_version=resolved_version, attempts=max_attempts,
        )
    return AIResult(
        ok=False, error=last_error, elapsed_ms=elapsed,
        prompt_version=resolved_version, attempts=max_attempts,
    )


def _call_openai(system_prompt: str, user_content: str, schema: type[T], timeout: float) -> T:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 가 설정되지 않았습니다.")

    from openai import OpenAI  # 지연 import: 키가 없어도 앱이 뜨게

    client = OpenAI(api_key=api_key, timeout=timeout)
    completion = client.beta.chat.completions.parse(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0,          # 재현성 지표를 위해 고정
        seed=42,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        response_format=schema,
    )
    message = completion.choices[0].message
    if getattr(message, "refusal", None):
        raise RuntimeError(f"모델이 거부했습니다: {message.refusal}")
    if message.parsed is None:
        raise ValueError("스키마를 통과한 응답이 없습니다.")
    return message.parsed
