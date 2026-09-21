from service.identity.models import Principal


class TokenResolver:
    def __init__(self, principals: dict[str, dict]) -> None:
        self._principals: dict[str, Principal] = {}
        for token, data in principals.items():
            self._principals[token] = Principal(
                user_id=data["user_id"],
                tenant_id=data["tenant_id"],
                scopes=data["scopes"],
            )

    def resolve(self, token: str) -> Principal | None:
        return self._principals.get(token)
