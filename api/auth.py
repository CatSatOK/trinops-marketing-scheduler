"""API-key auth for staff and admin endpoints.

Auth is disabled in DEMO_MODE so the public demo stays clickable. When
DEMO_MODE is false, protected endpoints require the X-API-Key header to match
ADMIN_API_KEY (set in .env). The inbound lead webhook is intentionally left
open. Comparison is constant-time.
"""

import secrets

from fastapi import Header, HTTPException, status

from marketing.config import get_settings


def require_admin(x_api_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if settings.demo_mode:
        return
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_API_KEY is not configured",
        )
    if x_api_key is None or not secrets.compare_digest(x_api_key, settings.admin_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing API key",
            headers={"WWW-Authenticate": "API-Key"},
        )
