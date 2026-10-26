"""Opt-in Anthropic adapter. Streams are private until completely validated."""

import asyncio
import json
import logging
from time import perf_counter

from anthropic import APITimeoutError, AsyncAnthropic
from anthropic.types import MessageParam, ThinkingConfigParam

from hope_brain.context import CandidateReply, ContextBuilder, TrustedContext
from hope_brain.contracts import BrainTurnRequest, SpeechSegment
from hope_brain.provider import ProviderBudgetExceeded
from hope_brain.settings import AnthropicSettings
from hope_brain.spend import SpendBudget

logger = logging.getLogger(__name__)
MAX_USER_BYTES = 16_384
MAX_RESPONSE_CHARS = 65_536


def token_count(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("invalid usage")
    return value


def quiet_sdk_logs() -> None:
    # SDK debug logging can include request bodies. Disable it even when inherited
    # environment settings request debug mode; our own logs contain only metrics.
    roots = ("anthropic", "httpx2", "httpcore2", "httpx", "httpcore")
    for name in set(roots) | set(logging.root.manager.loggerDict):
        if name.split(".")[0] in roots:
            sdk_logger = logging.getLogger(name)
            sdk_logger.setLevel(logging.CRITICAL + 1)
            sdk_logger.propagate = False
            sdk_logger.disabled = True


class AnthropicProvider:
    def __init__(
        self, settings: AnthropicSettings, *, client: AsyncAnthropic | None = None
    ) -> None:
        quiet_sdk_logs()
        self.settings = settings
        self.budget = SpendBudget(settings.session_budget_usd)
        self.last_metrics: dict[str, int | float | str] = {}
        self.context_builder = ContextBuilder(conversational=True)
        # Only text-only modes are supported by this adapter. Tools and reasoning
        # blocks need their own validated transport before enabling them.
        self.thinking: ThinkingConfigParam = (
            {"type": "between_tools"} if settings.thinking_mode == "between_tools"
            else {"type": "disabled"}
        )
        self.client = client or AsyncAnthropic(
            api_key=settings.api_key.get_secret_value(),
            base_url="https://api.anthropic.com",
            max_retries=0,
            timeout=settings.timeout_seconds,
            open_telemetry=False,
        )

    async def aclose(self) -> None:
        await self.client.close()

    async def generate(
        self, request: BrainTurnRequest, *, context: TrustedContext | None = None
    ) -> list[SpeechSegment]:
        started = perf_counter()
        metrics: dict[str, int | float | str] = {
            "stage": "provider", "outcome": "error", "generation_attempted": 0,
        }
        reservation = None
        try:
            # Includes context, count endpoint, generation, and validation, rather
            # than resetting a read timeout for each incoming chunk.
            async with asyncio.timeout(self.settings.timeout_seconds):
                if len(request.text.encode("utf-8")) > MAX_USER_BYTES:
                    raise ValueError("input limit")
                built = self.context_builder.build(request, context)
                messages: list[MessageParam] = []
                if context is not None:
                    for turn in context.history:
                        messages.append({"role": "user", "content": turn.user_text})
                        messages.append({
                            "role": "assistant",
                            "content": CandidateReply(segments=list(turn.reply)).model_dump_json(),
                        })
                messages.append({"role": "user", "content": built.user_text})
                metrics["context_ms"] = round((perf_counter() - started) * 1000, 3)
                count_started = perf_counter()
                count = await self.client.messages.count_tokens(
                    model=self.settings.model, system=built.system, messages=messages,
                    thinking=self.thinking,
                )
                if type(count.input_tokens) is not int or count.input_tokens < 0:
                    raise ValueError("invalid token count")
                # Counts are estimates. Reserve 10% plus 64 input tokens, while
                # explicitly documenting that this cannot enforce provider billing.
                reserved_input = (count.input_tokens * 11 + 9) // 10 + 64
                estimate = self.settings.estimated_cost(reserved_input, self.settings.max_tokens)
                if estimate > self.settings.turn_budget_usd:
                    raise ProviderBudgetExceeded
                metrics["count_ms"] = round((perf_counter() - count_started) * 1000, 3)
                metrics["estimated_max_usd"] = str(estimate)
                reservation = self.budget.reserve(estimate)
                metrics["generation_attempted"] = 1
                segments = await self._receive(built.system, messages, started, metrics)
                metrics["outcome"] = "completed"
                return segments
        except asyncio.CancelledError:
            metrics["outcome"] = "cancelled"
            raise
        except APITimeoutError:
            metrics["outcome"] = "timeout"
            raise TimeoutError("provider timeout") from None
        except TimeoutError:
            metrics["outcome"] = "timeout"
            raise
        except ProviderBudgetExceeded:
            metrics["outcome"] = "budget_exceeded"
            raise
        finally:
            if reservation is not None:
                usage_cost = None
                if metrics.get("usage_complete") == 1:
                    usage_cost = self.settings.estimated_cost(
                        token_count(metrics["input_tokens"]), token_count(metrics["output_tokens"])
                    )
                    metrics["usage_cost_usd"] = str(usage_cost)
                    metrics["estimate_minus_usage_usd"] = str(estimate - usage_cost)
                self.budget.settle(reservation, usage_cost)
            metrics.update(self.budget.snapshot())
            metrics["total_ms"] = round((perf_counter() - started) * 1000, 3)
            self.last_metrics = dict(metrics)
            logger.info(json.dumps(metrics, separators=(",", ":")))

    async def _receive(
        self,
        system: str,
        messages: list[MessageParam],
        started: float,
        metrics: dict[str, int | float | str],
    ) -> list[SpeechSegment]:
        stream = await self.client.messages.create(
            model=self.settings.model,
            system=system,
            messages=messages,
            max_tokens=self.settings.max_tokens,
            thinking=self.thinking,
            stream=True,
        )
        chunks: list[str] = []
        length = 0
        phase = "start"
        async with stream:
            async for event in stream:
                if "first_event_ms" not in metrics:
                    metrics["first_event_ms"] = round((perf_counter() - started) * 1000, 3)
                if event.type == "message_start" and phase == "start":
                    if (
                        event.message.usage.cache_creation_input_tokens
                        or event.message.usage.cache_read_input_tokens
                    ):
                        raise ValueError("unexpected cache usage")
                    metrics["input_tokens"] = token_count(event.message.usage.input_tokens)
                    metrics["output_tokens"] = token_count(event.message.usage.output_tokens)
                    phase = "block"
                elif event.type == "content_block_start" and phase == "block":
                    if event.index != 0 or event.content_block.type != "text":
                        raise ValueError("unexpected content")
                    chunks.append(event.content_block.text)
                    length += len(event.content_block.text)
                    phase = "text"
                elif event.type == "content_block_delta" and phase == "text":
                    if event.index != 0 or event.delta.type != "text_delta":
                        raise ValueError("unexpected delta")
                    if "first_text_ms" not in metrics:
                        metrics["first_text_ms"] = round((perf_counter() - started) * 1000, 3)
                    chunks.append(event.delta.text)
                    length += len(event.delta.text)
                elif event.type == "content_block_stop" and phase == "text" and event.index == 0:
                    phase = "finish"
                elif event.type == "message_delta" and phase == "finish":
                    if event.usage.cache_creation_input_tokens or event.usage.cache_read_input_tokens:
                        raise ValueError("unexpected cache usage")
                    if event.usage.input_tokens is not None:
                        metrics["input_tokens"] = token_count(event.usage.input_tokens)
                    metrics["output_tokens"] = token_count(event.usage.output_tokens)
                    if event.delta.stop_reason != "end_turn":
                        raise ValueError("incomplete reply")
                    phase = "stop"
                elif event.type == "message_stop" and phase == "stop":
                    phase = "done"
                    break
                else:
                    raise ValueError("unexpected stream event")
                if length > MAX_RESPONSE_CHARS:
                    raise ValueError("response limit")
        if phase != "done":
            raise ValueError("incomplete stream")
        metrics["usage_complete"] = 1
        validation_started = perf_counter()
        result = CandidateReply.model_validate_json("".join(chunks)).segments
        metrics["validation_ms"] = round((perf_counter() - validation_started) * 1000, 3)
        return result
