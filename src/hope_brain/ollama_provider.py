"""Optional local chat adapter; loopback only, no keys, retries or cloud fallback."""

import asyncio
import json
import logging
from time import perf_counter

import httpx2 as httpx

from hope_brain.context import CandidateReply, ContextBuilder, TrustedContext
from hope_brain.contracts import BrainTurnRequest, SpeechSegment
from hope_brain.settings import ConfigurationError, OllamaSettings

logger = logging.getLogger(__name__)
MAX_BODY_BYTES = 262_144


class OllamaProvider:
    def __init__(
        self, settings: OllamaSettings, *, client: httpx.AsyncClient | None = None
    ) -> None:
        self.settings = settings
        self.url = f"http://127.0.0.1:{settings.port}"
        self.context_builder = ContextBuilder(conversational=True)
        self.last_metrics: dict[str, str | float | int] = {}
        # Transport debug logs can expose request content. Metrics below are redacted.
        for name in {"httpx2", "httpcore2"} | set(logging.root.manager.loggerDict):
            if name.split(".")[0] in {"httpx2", "httpcore2"}:
                transport_logger = logging.getLogger(name)
                transport_logger.disabled = True
                transport_logger.propagate = False
                transport_logger.setLevel(logging.CRITICAL + 1)
        self.client = client or httpx.AsyncClient(
            timeout=settings.timeout_seconds, trust_env=False, follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def _post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        # stream=False in the Ollama body; stream the HTTP body only to bound memory.
        async with self.client.stream("POST", self.url + path, json=payload) as response:
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_BODY_BYTES:
                    raise ValueError("local response limit")
        result = json.loads(body)
        if not isinstance(result, dict) or result.get("error"):
            raise ValueError("invalid local response")
        return result

    async def _verify_model(self) -> None:
        # Repeat before each prompt to reject a tag changed into a cloud alias.
        if "cloud" in self.settings.model.casefold():
            raise ConfigurationError("Select a locally downloaded Ollama model.")
        details = await self._post("/api/show", {"model": self.settings.model})
        if details.get("remote_host") or details.get("remote_model"):
            raise ConfigurationError("Cloud-backed Ollama models are disabled in local mode.")
        if not isinstance(details.get("model_info"), dict) or not details["model_info"]:
            raise ConfigurationError("Ollama did not report a local model. Check the download.")
        capabilities = details.get("capabilities")
        if not isinstance(capabilities, list) or "completion" not in capabilities:
            raise ConfigurationError("Select an Ollama model that supports text completion.")

    async def check_ready(self) -> None:
        """Give actionable startup errors without showing server bodies or prompts."""
        try:
            async with asyncio.timeout(10):
                await self._verify_model()
        except ConfigurationError:
            raise
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404:
                raise ConfigurationError(
                    "Local model is missing. Download it with ollama pull MODEL; "
                    "see docs/local_chat.md."
                ) from None
            raise ConfigurationError("Ollama rejected the model check. See docs/local_chat.md.") from None
        except (httpx.HTTPError, TimeoutError, ValueError):
            raise ConfigurationError(
                "Cannot use local Ollama. Start Ollama, then retry; see docs/local_chat.md."
            ) from None

    async def generate(
        self, request: BrainTurnRequest, *, context: TrustedContext | None = None
    ) -> list[SpeechSegment]:
        started = perf_counter()
        metrics: dict[str, str | float | int] = {
            "stage": "local_provider", "outcome": "error", "thinking_requested": 0,
        }
        try:
            async with asyncio.timeout(self.settings.timeout_seconds):
                if len(request.text.encode("utf-8")) > 8192:
                    raise ValueError("input limit")
                await self._verify_model()
                built = self.context_builder.build(request, context)
                messages = [{"role": "system", "content": built.system}]
                if context is not None:
                    for turn in context.history:
                        messages.append({"role": "user", "content": turn.user_text})
                        messages.append({
                            "role": "assistant",
                            "content": CandidateReply(segments=list(turn.reply)).model_dump_json(),
                        })
                messages.append({"role": "user", "content": built.user_text})
                response = await self._post("/api/chat", {
                    "model": self.settings.model, "messages": messages,
                    "format": CandidateReply.model_json_schema(), "stream": False, "think": False,
                    "options": {"num_predict": self.settings.max_tokens, "num_ctx": 8192,
                                "temperature": 0.5},
                    "keep_alive": "5m",
                })
                if (
                    response.get("done") is not True or response.get("done_reason") != "stop"
                    or response.get("remote_host") or response.get("remote_model")
                ):
                    raise ValueError("incomplete or remote local reply")
                message = response.get("message")
                if (
                    not isinstance(message, dict) or message.get("role") != "assistant"
                    or message.get("tool_calls") or not isinstance(message.get("content"), str)
                ):
                    raise ValueError("invalid local message")
                segments = CandidateReply.model_validate_json(message["content"]).segments
                metrics["thinking_output_seen"] = int(bool(message.get("thinking")))
                for name in ("load_duration", "prompt_eval_duration", "eval_duration"):
                    duration = response.get(name)
                    if type(duration) is int and duration >= 0:
                        metrics[name.removesuffix("_duration") + "_ms"] = round(duration / 1e6, 3)
                for name in ("prompt_eval_count", "eval_count"):
                    count = response.get(name)
                    if type(count) is int and count >= 0:
                        metrics[name] = count
                metrics["outcome"] = "completed"
                return segments
        except asyncio.CancelledError:
            metrics["outcome"] = "cancelled"
            raise
        except (httpx.TimeoutException, TimeoutError):
            metrics["outcome"] = "timeout"
            raise TimeoutError("local model timeout") from None
        finally:
            metrics["total_ms"] = round((perf_counter() - started) * 1000, 3)
            self.last_metrics = dict(metrics)
            logger.info(json.dumps(metrics, separators=(",", ":")))
