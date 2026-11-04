"""SSE：真实 uvicorn（后台线程）+ httpx 流式读取，能收到 hello、run.stage、run.finished。"""

from __future__ import annotations

import json
import socket
import threading
import time

import httpx
import uvicorn

from bureau.api import create_app


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_sse_receives_run_events(demo_app):
    port = _free_port()
    demo_app.port = port
    server = uvicorn.Server(uvicorn.Config(create_app(demo_app, background=False), host="127.0.0.1", port=port,
                                           log_config=None, access_log=False, lifespan="on"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started
    base = f"http://127.0.0.1:{port}"
    token = httpx.get(f"{base}/api/session", timeout=5).json()["token"]
    seen: list[str] = []
    stages: set[str] = set()
    finished = None
    try:
        with httpx.Client(timeout=httpx.Timeout(30, read=30)) as client:
            with client.stream("GET", f"{base}/api/events", params={"token": token}) as resp:
                assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/event-stream")
                event = None
                started_run = False
                for line in resp.iter_lines():
                    if line.startswith("event: "):
                        event = line[7:]
                    elif line.startswith("data: ") and event:
                        data = json.loads(line[6:])
                        seen.append(event)
                        if event == "hello" and not started_run:
                            r = httpx.post(f"{base}/api/runs", json={"demo": True, "dry_run": True},
                                           headers={"X-Bureau-Token": token}, timeout=10)
                            assert r.status_code == 202
                            started_run = True
                        elif event == "run.stage":
                            stages.add(data["stage"]["name"])
                            assert data["run_id"] and data["stage"]["agent"]
                        elif event == "run.finished":
                            finished = data
                            break
                        event = None
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    assert seen[0] == "hello"
    assert "run.started" in seen and "run.log" in seen
    assert len(stages) == 12
    assert finished is not None and finished["status"] == "success"
