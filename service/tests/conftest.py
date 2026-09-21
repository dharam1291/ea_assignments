import pytest
from httpx import ASGITransport, AsyncClient

from service.core.factory import create_app


@pytest.fixture
def sleep_calls():
    calls = []

    async def mock_sleep(seconds: float) -> None:
        calls.append(seconds)

    return calls, mock_sleep


@pytest.fixture
def app(sleep_calls):
    _, mock_sleep = sleep_calls
    return create_app(sleep_fn=mock_sleep)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


ALPHA_FULL = {"Authorization": "Bearer demo-alpha-full"}
ALPHA_SALES = {"Authorization": "Bearer demo-alpha-sales"}
BETA_FULL = {"Authorization": "Bearer demo-beta-full"}


def invoke_body(capability="billing.summary", simulation="ok", conversation_id="conv-1"):
    return {
        "conversation_id": conversation_id,
        "capability": capability,
        "message": "test message",
        "simulation": simulation,
    }
