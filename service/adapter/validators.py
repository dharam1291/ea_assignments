from pydantic import BaseModel, ValidationError

from service.agents.tools.billing_summary import BillingSummaryResult
from service.agents.tools.sales_offers import SalesOffersResult
from service.core.errors import InvalidToolResultError

_SCHEMA_MAP: dict[str, type[BaseModel]] = {
    "billing.summary": BillingSummaryResult,
    "sales.offers": SalesOffersResult,
}


def validate_tool_result(capability: str, raw_result: dict) -> dict:
    schema = _SCHEMA_MAP.get(capability)
    if schema is None:
        raise InvalidToolResultError("No validation schema for capability.")
    try:
        validated = schema.model_validate(raw_result)
        return validated.model_dump()
    except ValidationError:
        raise InvalidToolResultError("The tool returned an invalid result.")
