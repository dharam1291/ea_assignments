from typing import Any

from pydantic import BaseModel


class BillingSummaryResult(BaseModel):
    amount_due: float
    currency: str


class BillingSummaryTool:
    def __init__(self, fixture_data: dict[str, dict]) -> None:
        self._fixture_data = fixture_data

    @property
    def name(self) -> str:
        return "billing_summary"

    @property
    def result_schema(self) -> type[BaseModel]:
        return BillingSummaryResult

    def get_fixture_result(self, tenant_id: str) -> dict[str, Any]:
        return dict(self._fixture_data[tenant_id])
