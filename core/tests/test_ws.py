def test_ws_connects_and_closes(client) -> None:
    with client.websocket_connect("/ws") as ws:
        # No messages until something triggers a broadcast; keep idle.
        pass


def test_ws_receives_index_updated_after_broadcast(client) -> None:
    import asyncio

    from core.state import IndexUpdatedEvent

    with client.websocket_connect("/ws") as ws:
        app = client.app
        asyncio.run(app.state.ws_broadcaster.publish(IndexUpdatedEvent(ts="2026-04-17T12:00:00-07:00")))
        data = ws.receive_json()
        assert data == {"type": "index-updated", "ts": "2026-04-17T12:00:00-07:00"}


def test_ws_receives_live_notebook_execution_event(client) -> None:
    import asyncio

    from core.state import NotebookExecutionEvent

    event = {
        "phase": "output",
        "path": "projects/demo/notebooks/live.ipynb",
        "run_id": "run-1",
        "cell_id": "cell-1",
        "sequence": 2,
        "operation": "append",
        "output": {"type": "text", "content": "first line\n"},
    }
    with client.websocket_connect("/ws") as ws:
        asyncio.run(
            client.app.state.ws_broadcaster.publish(NotebookExecutionEvent(event))
        )
        assert ws.receive_json() == {"type": "notebook-execution", **event}


def test_broadcaster_evicts_broken_client_without_losing_healthy_client() -> None:
    import asyncio

    from core.state import IndexUpdatedEvent, WsBroadcaster

    class Healthy:
        def __init__(self) -> None:
            self.payloads = []

        async def send_json(self, payload) -> None:
            self.payloads.append(payload)

    class Broken:
        def __init__(self) -> None:
            self.calls = 0

        async def send_json(self, payload) -> None:
            self.calls += 1
            raise RuntimeError("disconnected")

    async def exercise() -> tuple[list[dict], int]:
        broadcaster = WsBroadcaster()
        healthy = Healthy()
        broken = Broken()
        await broadcaster.add(broken)
        await broadcaster.add(healthy)
        await broadcaster.publish(IndexUpdatedEvent(ts="first"))
        await broadcaster.publish(IndexUpdatedEvent(ts="second"))
        return healthy.payloads, broken.calls

    payloads, broken_calls = asyncio.run(exercise())
    assert payloads == [
        {"type": "index-updated", "ts": "first"},
        {"type": "index-updated", "ts": "second"},
    ]
    assert broken_calls == 1
