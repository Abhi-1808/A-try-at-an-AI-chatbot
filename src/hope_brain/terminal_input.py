"""Read stdin during inference, with bounded FIFO buffering and explicit receipts."""

import asyncio
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass
from threading import Event, Thread
from time import perf_counter


@dataclass(frozen=True)
class QueuedInput:
    number: int
    text: str
    received_at: float


class TerminalInput:
    def __init__(
        self, source: Iterable[str], notice: Callable[[str], None], *, capacity: int = 32
    ) -> None:
        self._loop = asyncio.get_running_loop()
        self._queue: asyncio.Queue[QueuedInput] = asyncio.Queue(maxsize=capacity)
        self._changed = asyncio.Event()
        self._stopped = Event()
        self._done = False
        self._notice = notice

        def schedule(callback: Callable[..., None], *args: object) -> None:
            if not self._stopped.is_set():
                try:
                    self._loop.call_soon_threadsafe(callback, *args)
                except RuntimeError:
                    pass  # The CLI exited while the daemon reader was waiting for input.

        def read() -> None:
            try:
                for number, raw in enumerate(source, 1):
                    if self._stopped.is_set():
                        break
                    text = raw.strip()
                    if text:
                        schedule(self._offer, QueuedInput(number, text, perf_counter()))
            except (OSError, UnicodeError, ValueError):
                schedule(self._notice, "Input read failed; remaining input was not accepted.")
            finally:
                schedule(self._finish)

        # A blocked console read must never prevent Ctrl+C or /quit from exiting.
        Thread(target=read, name="mira-input", daemon=True).start()

    def _offer(self, item: QueuedInput) -> None:
        if self._stopped.is_set():
            return
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            self._notice(f"Input #{item.number} rejected: queue full. Please resend later.")
            return
        self._notice(f"Input #{item.number} accepted; waiting inputs: {self._queue.qsize()}.")
        self._changed.set()

    def _finish(self) -> None:
        self._done = True
        self._changed.set()

    async def __aiter__(self) -> AsyncIterator[QueuedInput]:
        while not self._done or not self._queue.empty():
            if self._queue.empty():
                await self._changed.wait()
            while not self._queue.empty():
                yield self._queue.get_nowait()
            self._changed.clear()

    def close(self) -> None:
        self._stopped.set()
        count = self._queue.qsize()
        while not self._queue.empty():
            self._queue.get_nowait()
        if count:
            self._notice(f"Chat exited; {count} pending input(s) cancelled.")
