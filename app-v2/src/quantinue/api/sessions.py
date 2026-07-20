"""Session-cookie signing key resolution."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from quantinue.core.config import Settings

_LOGGER = structlog.get_logger(__name__)

# 32바이트를 URL-safe로 인코딩하면 43자다. 테스트가 32자 이상을 요구한다.
_GENERATED_SECRET_BYTES = 32


def resolve_session_secret(settings: Settings) -> str:
    """Return the configured signing key, or mint a throwaway one with a warning.

    설정되지 않았을 때 고정 개발키로 떨어지지 않는 이유: 그 상수는 반드시
    한 번은 프로덕션에 간다. 대신 매 기동 새 키를 만든다 — 잃는 것은 재시작
    시 기존 세션이 전부 무효가 되는 것뿐이고, 그건 로그로 알려준다.
    """
    configured = settings.session_secret
    if configured is not None and configured.get_secret_value().strip():
        return configured.get_secret_value()
    _LOGGER.warning(
        "session_secret_not_configured",
        detail=(
            "QUANTINUE_SESSION_SECRET가 없어 임시 키를 생성했습니다 — "
            "재시작하면 모든 로그인 세션이 만료됩니다."
        ),
    )
    return secrets.token_urlsafe(_GENERATED_SECRET_BYTES)
