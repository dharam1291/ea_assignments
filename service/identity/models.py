from pydantic import BaseModel, ConfigDict


class Principal(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    tenant_id: str
    scopes: list[str]
