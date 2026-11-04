"""事件总线：有界队列、丢弃最旧、跨线程发布。"""

from __future__ import annotations

import asyncio
import threading

from bureau.core.bus import EventBus
from bureau.core.security import host_allowed, is_loopback, token_ok


def test_slow_subscriber_drops_oldest():
    async def main():
        bus = EventBus(maxsize=3)
        sub = bus.subscribe()
        for i in range(10):
            bus.publish("tick", {"i": i})
        got = [(await sub.get(0.1)).data["i"] for _ in range(3)]
        assert got == [7, 8, 9]
        assert sub.dropped == 7
        assert await sub.get(0.05) is None
        sub.close()
        assert bus.subscriber_count == 0

    asyncio.run(main())


def test_publish_from_thread():
    async def main():
        bus = EventBus()
        sub = bus.subscribe()
        t = threading.Thread(target=lambda: bus.publish("run.log", {"message": "来自线程"}))
        t.start()
        t.join()
        ev = await sub.get(1.0)
        assert ev is not None and ev.type == "run.log" and ev.data["message"] == "来自线程"

    asyncio.run(main())


def test_security_helpers():
    assert host_allowed("127.0.0.1:8765", 8765)
    assert host_allowed("localhost:8765", 8765)
    assert not host_allowed("evil.com", 8765)
    assert not host_allowed("127.0.0.1:9999", 8765)
    assert not host_allowed(None, 8765)
    assert token_ok("abc", "abc") and not token_ok("abc", "abd") and not token_ok(None, "abc")
    assert is_loopback("127.0.0.1") and is_loopback("::1") and not is_loopback("192.168.1.2")
