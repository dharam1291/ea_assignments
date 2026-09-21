from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    max_attempts: int = 3
    backoff_delays_ms: list[int] = field(default_factory=lambda: [50, 100])
    timeout_ms: int = 250
    trace_ttl_seconds: int = 3600
    max_conversation_id_length: int = 256
    max_capability_length: int = 256
    max_message_length: int = 2048


settings = Settings()
