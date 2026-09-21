from typing import Any

from pydantic import BaseModel


class OfferItem(BaseModel):
    id: str
    name: str


class SalesOffersResult(BaseModel):
    offers: list[OfferItem]


class SalesOffersTool:
    def __init__(self, fixture_data: dict[str, dict]) -> None:
        self._fixture_data = fixture_data

    @property
    def name(self) -> str:
        return "sales_offers"

    @property
    def result_schema(self) -> type[BaseModel]:
        return SalesOffersResult

    def get_fixture_result(self, tenant_id: str) -> dict[str, Any]:
        return dict(self._fixture_data[tenant_id])
