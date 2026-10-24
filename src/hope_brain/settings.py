"""Explicit live-provider configuration; no keys or prices are inferred."""

import os
from collections.abc import Mapping
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError


class ConfigurationError(ValueError):
    """Safe to display: contains setting names, never setting values."""


class AnthropicSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    api_key: SecretStr = Field(repr=False)
    model: str = Field(min_length=1, max_length=200, pattern=r"^\S+$")
    max_tokens: int = Field(default=256, ge=1, le=4096)
    timeout_seconds: float = Field(default=30, gt=0, le=120, allow_inf_nan=False)
    turn_budget_usd: Decimal = Field(gt=0, allow_inf_nan=False)
    session_budget_usd: Decimal = Field(gt=0, allow_inf_nan=False)
    input_usd_per_million: Decimal = Field(gt=0, allow_inf_nan=False)
    output_usd_per_million: Decimal = Field(gt=0, allow_inf_nan=False)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "AnthropicSettings":
        source = os.environ if env is None else env
        names = {
            "api_key": "ANTHROPIC_API_KEY",
            "model": "HOPE_ANTHROPIC_MODEL",
            "max_tokens": "HOPE_MAX_TOKENS",
            "timeout_seconds": "HOPE_TIMEOUT_SECONDS",
            "turn_budget_usd": "HOPE_TURN_BUDGET_USD",
            "session_budget_usd": "HOPE_SESSION_BUDGET_USD",
            "input_usd_per_million": "HOPE_INPUT_USD_PER_MILLION",
            "output_usd_per_million": "HOPE_OUTPUT_USD_PER_MILLION",
        }
        if not source.get("ANTHROPIC_API_KEY", "").strip():
            raise ConfigurationError("ANTHROPIC_API_KEY is required for --provider anthropic.")
        values = {field: source[name].strip() for field, name in names.items() if name in source}
        try:
            return cls.model_validate(values)
        except ValidationError as error:
            invalid = sorted({names[str(item["loc"][0])] for item in error.errors()})
            raise ConfigurationError(
                "Set valid live-provider settings: " + ", ".join(invalid)
            ) from None

    def estimated_cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        return (
            input_tokens * self.input_usd_per_million + output_tokens * self.output_usd_per_million
        ) / Decimal(1_000_000)
