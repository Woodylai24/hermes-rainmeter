#!/usr/bin/env python3
"""
Hermes Rainmeter Plugin — Phase 1 Integration Tests

Tests the RainmeterAdapter + RainmeterWSServer end-to-end:
- Adapter lifecycle (connect/disconnect)
- Inbound messages (WS client → adapter → handle_message)
- Outbound messages (adapter.send → WS broadcast)
- Typing indicators
- Auth flow
- Multiple clients
"""

import asyncio
import json
import sys
import os
import time

# Add parent to path so we can import ws_server directly
sys.path.insert(0, os.path.dirname(__file__))

import aiohttp

# We test ws_server.py standalone (adapter.py requires Hermes gateway imports
# which aren't available outside the gateway process)
from ws_server import RainmeterWSServer

PORT = 18643  # Use non-default port for testing
TIMEOUT = 5.0

results: list[dict] = []


def record(name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    results.append({"name": name, "passed": passed, "detail": detail})
    icon = "✅" if passed else "❌"
    print(f"  {icon} {name}" + (f" — {detail}" if detail else ""))


async def drain(ws: aiohttp.ClientWebSocketResponse, expect: int = 1, timeout: float = 2.0):
    """Drain N messages from the websocket."""
    msgs = []
    for _ in range(expect):
        try:
            msg = await asyncio.wait_for(ws.receive_json(), timeout=timeout)
            msgs.append(msg)
        except asyncio.TimeoutError:
            break
    return msgs


async def connect_client(session: aiohttp.ClientSession, port: int = PORT):
    """Connect a WS client and consume the welcome + status messages."""
    ws = await session.ws_connect(f"ws://localhost:{port}/ws")
    # Drain welcome + status
    await drain(ws, expect=2, timeout=2.0)
    return ws


# ---------------------------------------------------------------------------
# Test suites
# ---------------------------------------------------------------------------


async def test_server_lifecycle():
    """Server starts and stops cleanly."""
    server = RainmeterWSServer(port=PORT)
    ok = await server.start()
    record("Server starts", ok)
    assert ok

    await server.stop()
    record("Server stops", True)

    # Verify port is released
    server2 = RainmeterWSServer(port=PORT)
    ok2 = await server2.start()
    record("Port released after stop", ok2)
    await server2.stop()


async def test_client_connect_disconnect():
    """Client can connect and receives welcome + status."""
    server = RainmeterWSServer(port=PORT)
    await server.start()

    try:
        async with aiohttp.ClientSession() as session:
            ws = await session.ws_connect(f"ws://localhost:{PORT}/ws")

            # Should get welcome
            welcome = await asyncio.wait_for(ws.receive_json(), timeout=TIMEOUT)
            record("Welcome message received", welcome.get("type") == "welcome")

            # Should get status broadcast
            status = await asyncio.wait_for(ws.receive_json(), timeout=TIMEOUT)
            record("Status broadcast received", status.get("type") == "status"
                    and status.get("connected_clients") == 1)

            # Disconnect
            await ws.close()
            await asyncio.sleep(0.3)

            record("Client count after disconnect", server.client_count == 0)
    finally:
        await server.stop()


async def test_inbound_messages():
    """Messages from WS client trigger the on_message callback."""
    received: list[tuple[str, str]] = []

    async def on_msg(text: str, session_key: str):
        received.append((text, session_key))

    server = RainmeterWSServer(port=PORT, on_message=on_msg)
    await server.start()

    try:
        async with aiohttp.ClientSession() as session:
            ws = await connect_client(session)

            # Send a message
            await ws.send_json({
                "type": "message",
                "content": "Hello from Rainmeter!",
                "session_key": "rainmeter:desktop:test",
            })
            await asyncio.sleep(0.3)

            record("Inbound message received by callback",
                    len(received) == 1 and received[0] == ("Hello from Rainmeter!", "rainmeter:desktop:test"))

            # Send with default session_key
            await ws.send_json({
                "type": "message",
                "content": "Second message",
            })
            await asyncio.sleep(0.3)

            record("Default session_key used",
                    len(received) == 2 and received[1][1] == "rainmeter:desktop:default")

            await ws.close()
    finally:
        await server.stop()


async def test_outbound_broadcast():
    """Server broadcast reaches all connected clients."""
    server = RainmeterWSServer(port=PORT)
    await server.start()

    try:
        async with aiohttp.ClientSession() as session:
            ws1 = await connect_client(session)
            ws2 = await connect_client(session)
            # Drain any status broadcasts from second client connecting
            await drain(ws1, expect=1, timeout=1.0)

            # Broadcast a message
            sent = await server.broadcast({
                "type": "message",
                "content": "Hello from Hermes!",
            })
            record("Broadcast sent to 2 clients", sent == 2)

            # Both clients receive it
            msg1 = await asyncio.wait_for(ws1.receive_json(), timeout=TIMEOUT)
            msg2 = await asyncio.wait_for(ws2.receive_json(), timeout=TIMEOUT)

            record("Client 1 received broadcast", msg1.get("content") == "Hello from Hermes!")
            record("Client 2 received broadcast", msg2.get("content") == "Hello from Hermes!")

            await ws1.close()
            await ws2.close()
    finally:
        await server.stop()


async def test_ping_pong():
    """Ping messages get pong responses."""
    server = RainmeterWSServer(port=PORT)
    await server.start()

    try:
        async with aiohttp.ClientSession() as session:
            ws = await connect_client(session)

            await ws.send_json({"type": "ping"})
            pong = await asyncio.wait_for(ws.receive_json(), timeout=TIMEOUT)
            record("Ping gets pong", pong.get("type") == "pong")

            await ws.close()
    finally:
        await server.stop()


async def test_invalid_json():
    """Non-JSON gets error response."""
    server = RainmeterWSServer(port=PORT)
    await server.start()

    try:
        async with aiohttp.ClientSession() as session:
            ws = await connect_client(session)

            await ws.send_str("not json at all")
            err = await asyncio.wait_for(ws.receive_json(), timeout=TIMEOUT)
            record("Non-JSON gets error", err.get("type") == "error")

            await ws.close()
    finally:
        await server.stop()


async def test_unknown_type():
    """Unknown message type gets error response."""
    server = RainmeterWSServer(port=PORT)
    await server.start()

    try:
        async with aiohttp.ClientSession() as session:
            ws = await connect_client(session)

            await ws.send_json({"type": "unknown_type"})
            err = await asyncio.wait_for(ws.receive_json(), timeout=TIMEOUT)
            record("Unknown type gets error", err.get("type") == "error")

            await ws.close()
    finally:
        await server.stop()


async def test_command_routing():
    """Command messages are routed as text."""
    received: list[tuple[str, str]] = []

    async def on_msg(text: str, session_key: str):
        received.append((text, session_key))

    server = RainmeterWSServer(port=PORT, on_message=on_msg)
    await server.start()

    try:
        async with aiohttp.ClientSession() as session:
            ws = await connect_client(session)

            await ws.send_json({"type": "command", "command": "/status"})
            await asyncio.sleep(0.3)

            record("Command routed to on_message",
                    len(received) == 1 and received[0][0] == "/status")

            await ws.close()
    finally:
        await server.stop()


async def test_auth_flow():
    """Token auth: reject invalid, accept valid."""
    server = RainmeterWSServer(port=PORT, auth_token="secret123")
    await server.start()

    try:
        async with aiohttp.ClientSession() as session:
            # --- Wrong token ---
            ws1 = await session.ws_connect(f"ws://localhost:{PORT}/ws")
            # Drain welcome + status
            await drain(ws1, expect=2, timeout=2.0)

            await ws1.send_json({"type": "auth", "token": "wrong"})
            resp = await asyncio.wait_for(ws1.receive_json(), timeout=TIMEOUT)
            record("Wrong token rejected", resp.get("type") == "error")
            await ws1.close()
            await asyncio.sleep(0.3)

            # --- Correct token ---
            ws2 = await session.ws_connect(f"ws://localhost:{PORT}/ws")
            # Drain welcome + status
            await drain(ws2, expect=2, timeout=2.0)

            await ws2.send_json({"type": "auth", "token": "secret123"})
            auth_ok = await asyncio.wait_for(ws2.receive_json(), timeout=TIMEOUT)
            record("Correct token accepted", auth_ok.get("type") == "auth_ok")

            # Can send messages after auth
            received: list[str] = []

            async def on_msg(text, key):
                received.append(text)

            server.on_message = on_msg

            await ws2.send_json({"type": "message", "content": "post-auth msg"})
            await asyncio.sleep(0.3)
            record("Message works after auth", len(received) == 1 and received[0] == "post-auth msg")

            await ws2.close()
    finally:
        await server.stop()


async def test_auth_timeout():
    """Client that doesn't send auth within timeout gets disconnected."""
    server = RainmeterWSServer(port=PORT, auth_token="secret123")
    await server.start()

    try:
        async with aiohttp.ClientSession() as session:
            ws = await session.ws_connect(f"ws://localhost:{PORT}/ws")
            # Drain welcome + status
            for _ in range(2):
                await asyncio.wait_for(ws.receive(), timeout=2.0)

            # Don't send auth, wait for server to close (~5s timeout + close)
            got_close = False
            for _ in range(15):
                try:
                    msg = await ws.receive(timeout=1.0)
                    if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED):
                        got_close = True
                        break
                except asyncio.TimeoutError:
                    continue
            record("Auth timeout disconnects client", got_close)
    except Exception as exc:
        record("Auth timeout disconnects client", False, str(exc))
    finally:
        await server.stop()


async def test_broadcast_after_client_disconnect():
    """Broadcast works correctly when some clients disconnect."""
    server = RainmeterWSServer(port=PORT)
    await server.start()

    try:
        async with aiohttp.ClientSession() as session:
            ws1 = await connect_client(session)
            ws2 = await connect_client(session)
            # Drain status from second client
            await drain(ws1, expect=1, timeout=1.0)

            # Disconnect ws1
            await ws1.close()
            await asyncio.sleep(0.3)

            record("Server has 1 client after disconnect", server.client_count == 1)

            # Broadcast should only reach ws2
            sent = await server.broadcast({"type": "message", "content": "after disconnect"})
            record("Broadcast reaches remaining client", sent == 1)

            # May get a status broadcast first (from dead client cleanup)
            for _ in range(5):
                msg = await asyncio.wait_for(ws2.receive_json(), timeout=TIMEOUT)
                if msg.get("type") == "message":
                    break
            record("Remaining client gets message", msg.get("content") == "after disconnect")

            await ws2.close()
    finally:
        await server.stop()


async def test_client_connected_callback():
    """on_client_connected callback fires."""
    connected_count = [0]

    async def on_connect():
        connected_count[0] += 1

    server = RainmeterWSServer(port=PORT, on_client_connected=on_connect)
    await server.start()

    try:
        async with aiohttp.ClientSession() as session:
            ws = await connect_client(session)
            await asyncio.sleep(0.3)
            record("on_client_connected fires", connected_count[0] == 1)

            await ws.close()
    finally:
        await server.stop()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def main():
    print("\n🔬 Phase 1 Integration Tests — RainmeterWSServer\n")

    tests = [
        test_server_lifecycle,
        test_client_connect_disconnect,
        test_inbound_messages,
        test_outbound_broadcast,
        test_ping_pong,
        test_invalid_json,
        test_unknown_type,
        test_command_routing,
        test_auth_flow,
        test_auth_timeout,
        test_broadcast_after_client_disconnect,
        test_client_connected_callback,
    ]

    for test_fn in tests:
        print(f"\n📋 {test_fn.__doc__}")
        try:
            await test_fn()
        except Exception as exc:
            record(test_fn.__name__, False, str(exc))
        # Small delay between tests to ensure port is released
        await asyncio.sleep(0.5)

    # Summary
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    total = len(results)

    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print(f"{'='*50}")

    if failed > 0:
        print("\nFailed tests:")
        for r in results:
            if not r["passed"]:
                print(f"  ❌ {r['name']}: {r['detail']}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
