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
