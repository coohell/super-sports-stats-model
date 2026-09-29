"""배당 소스 어댑터. 각 어댑터는 응답을 sssm.markets.Fixture 로 바꾼다."""
from __future__ import annotations

import requests


def check(resp: requests.Response, name: str) -> None:
    """raise_for_status 는 apiKey 가 든 URL 을 예외 메시지에 넣으므로 직접 만든다."""
    if resp.status_code >= 400:
        raise RuntimeError(f"{name} HTTP {resp.status_code}: {resp.text[:200]}")
