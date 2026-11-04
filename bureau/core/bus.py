"""异步事件总线。

每个订阅者（一个 SSE 连接）一个有界队列；队列满时丢弃最旧的事件，慢订阅者不会拖住发布方。
``publish`` 可以在任意线程调用：不在事件循环线程时通过 ``call_soon_threadsafe`` 投递。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

log = logging.getLogger("bureau.bus")


@dataclass
class Event:
    type: str
    data: Any
    ts: str = ""


@dataclass
class Subscription:
    queue: asyncio.Queue[Event]
    loop: asyncio.AbstractEventLoop
    dropped: int = 0
    closed: bool = False
    _bus: "EventBus | None" = field(default=None, repr=False)

    async def get(self, timeout: float | None = None) -> Event | None:
        try:
            if timeout is None:
                return await self.queue.get()
            return await asyncio.wait_for(self.queue.get(), timeout)
        except asyncio.TimeoutError:
            return None

    def close(self) -> None:
        if self._bus is not None:
            self._bus.unsubscribe(self)


class EventBus:
    def __init__(self, maxsize: int = 256, tz: str = "Asia/Shanghai") -> None:
        self.maxsize = maxsize
        self.tz = ZoneInfo(tz)
        self._subs: list[Subscription] = []
        self._lock = threading.Lock()
        self.published = 0

    def subscribe(self, maxsize: int | None = None) -> Subscription:
        loop = asyncio.get_running_loop()
        sub = Subscription(queue=asyncio.Queue(maxsize or self.maxsize), loop=loop, _bus=self)
        with self._lock:
            self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        sub.closed = True
        with self._lock:
            if sub in self._subs:
                self._subs.remove(sub)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subs)

    def publish(self, type_: str, data: Any = None) -> None:
        event = Event(type=type_, data=data if data is not None else {},
                      ts=datetime.now(self.tz).isoformat(timespec="seconds"))
        self.published += 1
        with self._lock:
            subs = list(self._subs)
        for sub in subs:
            if sub.closed:
                continue
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is sub.loop:
                self._put(sub, event)
            else:
                try:
                    sub.loop.call_soon_threadsafe(self._put, sub, event)
                except RuntimeError:          # 订阅者的事件循环已关闭
                    self.unsubscribe(sub)

    def _put(self, sub: Subscription, event: Event) -> None:
        if sub.closed:
            return
        while True:
            try:
                sub.queue.put_nowait(event)
                return
            except asyncio.QueueFull:
                try:
                    sub.queue.get_nowait()          # 丢弃最旧的事件
                    sub.dropped += 1
                except asyncio.QueueEmpty:
                    return
