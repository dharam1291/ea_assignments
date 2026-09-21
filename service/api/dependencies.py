import logging
from typing import Annotated

from fastapi import Depends, Header, Request

from service.core.errors import AuthenticationError
from service.identity.models import Principal

logger = logging.getLogger(__name__)


def _extract_token(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization:
        raise AuthenticationError()
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0] != "Bearer" or not parts[1].strip():
        raise AuthenticationError()
    return parts[1].strip()


def get_principal(
    request: Request,
    token: str = Depends(_extract_token),
) -> Principal:
    resolver = request.app.state.identity_resolver
    principal = resolver.resolve(token)
    if principal is None:
        raise AuthenticationError()
    return principal
