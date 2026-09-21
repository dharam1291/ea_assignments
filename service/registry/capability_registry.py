from service.identity.models import Principal
from service.registry.models import AgentRegistration


class CapabilityRegistry:
    def __init__(self, registrations: list[AgentRegistration]) -> None:
        self._registry: dict[str, AgentRegistration] = {
            reg.capability: reg for reg in registrations
        }

    def resolve(self, capability: str) -> AgentRegistration | None:
        return self._registry.get(capability)

    def check_scope(self, registration: AgentRegistration, principal: Principal) -> bool:
        return registration.required_scope in principal.scopes
