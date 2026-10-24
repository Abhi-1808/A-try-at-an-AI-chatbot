"""Opt-in Anthropic adapter. Streams are private until completely validated."""

import asyncio
import json
import logging
from time import perf_counter

from anthropic import APITimeoutError, AsyncAnthropic
from anthropic.types import MessageParam

from hope_brain.context import CandidateReply, ContextBuilder
from hope_brain.contracts import BrainTurnRequest, SpeechSegment
from hope_brain.provider import ProviderBudgetExceeded
from hope_brain.settings import AnthropicSettings

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
        self.context_builder = ContextBuilder()
        self.client = client or AsyncAnthropic(
            api_key=settings.api_key.get_secret_value(),
            base_url="https://api.anthropic.com",
            max_retries=0,
            timeout=settings.timeout_seconds,
            open_telemetry=False,
        )

    async def aclose(self) -> None:
        await self.client.close()

    async def generate(self, request: BrainTurnRequest) -> list[SpeechSegment]:
        started = perf_counter()
        metrics: dict[str, int | float | str] = {"stage": "provider", "outcome": "error"}
        try:
            # Includes context, count endpoint, generation, and validation, rather
            # than resetting a read timeout for each incoming chunk.
            async with asyncio.timeout(self.settings.timeout_seconds):
                if len(request.text.encode("utf-8")) > MAX_USER_BYTES:
                    raise ValueError("input limit")
                context = self.context_builder.build(request)
                messages: list[MessageParam] = [{"role": "user", "content": context.user_text}]
                metrics["context_ms"] = round((perf_counter() - started) * 1000, 3)
                count_started = perf_counter()
                count = await self.client.messages.count_tokens(
                    model=self.settings.model, system=context.system, messages=messages
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
                segments = await self._receive(context.system, messages, started, metrics)
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
            metrics["total_ms"] = round((perf_counter() - started) * 1000, 3)
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
            thinking={"type": "disabled"},
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
        validation_started = perf_counter()
        result = CandidateReply.model_validate_json("".join(chunks)).segments
        metrics["validation_ms"] = round((perf_counter() - validation_started) * 1000, 3)
        return result
