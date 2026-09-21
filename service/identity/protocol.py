from typing import Protocol

from service.identity.models import Principal


class IdentityResolver(Protocol):
    def resolve(self, token: str) -> Principal | None: ...
