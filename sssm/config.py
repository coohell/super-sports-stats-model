"""환경 변수 로딩. 저장소 루트의 .env 를 자동으로 읽는다."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # python-dotenv 없이도 동작
    pass


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()
