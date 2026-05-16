#!/usr/bin/env python3
"""
Hermes Rainmeter Plugin - Phase 0: WebSocket Echo Server

Standalone aiohttp WebSocket echo server for testing the Rainmeter plugin
communication layer.
"""

import argparse
import asyncio
import json
import signal
import sys
from datetime import datetime

from aiohttp import web

# Global set of connected WebSocket clients
connected_clients: set[web.WebSocketResponse] = set()


def log(msg: str) -> None:
    """Print a timestamped log message to stdout."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)


async def broadcast_status() -> None:
    """Broadcast current connection count to all connected clients."""
    if not connected_clients:
        return
    status_msg = json.dumps({
        "type": "status",
        "connected_clients": len(connected_clients),
    })
    dead = set()
    for ws in connected_clients:
        try:
            await ws.send_str(status_msg)
        except Exception:
            dead.add(ws)
    connected_clients.difference_update(dead)


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """Handle a WebSocket connection."""
    token_required: str | None = request.app["auth_token"]
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    # --- Connect ---
    connected_clients.add(ws)
    log(f"Client connected (total: {len(connected_clients)})")

    # Send welcome message
    welcome = json.dumps({
        "type": "welcome",
        "message": "Connected to Hermes echo server",
    })
    await ws.send_str(welcome)
    await broadcast_status()

    # --- Optional auth enforcement ---
    authenticated = True
    if token_required is not None:
        authenticated = False
        try:
            auth_msg = await asyncio.wait_for(ws.receive_str(), timeout=5.0)
            parsed = json.loads(auth_msg)
            if parsed.get("type") == "auth" and parsed.get("token") == token_required:
                authenticated = True
                log("Client authenticated successfully")
                await ws.send_str(json.dumps({
                    "type": "auth_ok",
                    "message": "Authentication successful",
                }))
            else:
                await ws.send_str(json.dumps({
                    "type": "error",
                    "message": "Authentication required",
                }))
                log("Client failed authentication — disconnecting")
        except asyncio.TimeoutError:
            await ws.send_str(json.dumps({
                "type": "error",
                "message": "Authentication required",
            }))
            log("Client auth timed out — disconnecting")
        except json.JSONDecodeError:
            await ws.send_str(json.dumps({
                "type": "error",
                "message": "Authentication required",
            }))
            log("Client sent non-JSON during auth — disconnecting")

    if not authenticated:
        connected_clients.discard(ws)
        await ws.close()
        await broadcast_status()
        return ws

    # --- Message loop ---
    async for msg in ws:
        if msg.type == web.WSMsgType.TEXT:
            try:
                original = msg.data
                content = json.loads(original)
                log(f"Received: {original}")

                echo = json.dumps({
                    "type": "echo",
                    "content": content,
                    "original": original,
                })
                await ws.send_str(echo)
            except json.JSONDecodeError:
                log(f"Received non-JSON: {msg.data}")
                await ws.send_str(json.dumps({
                    "type": "error",
                    "message": f"Non-JSON message received: {msg.data}",
                }))
        elif msg.type == web.WSMsgType.ERROR:
            log(f"WebSocket error: {ws.exception()}")

    # --- Disconnect ---
    connected_clients.discard(ws)
    log(f"Client disconnected (total: {len(connected_clients)})")
    await broadcast_status()
    return ws


def build_app(token: str | None = None) -> web.Application:
    """Build and return the aiohttp application."""
    app = web.Application()
    app["auth_token"] = token
    app.router.add_get("/ws", websocket_handler)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hermes WebSocket Echo Server (Phase 0 prototype)"
    )
    parser.add_argument(
        "--port", type=int, default=8643, help="Port to listen on (default: 8643)"
    )
    parser.add_argument(
        "--token", type=str, default=None, help="Optional auth token clients must send"
    )
    args = parser.parse_args()

    app = build_app(token=args.token)

    log(f"Echo server starting on port {args.port}")
    if args.token:
        log("Token authentication enabled")
    log(f"Echo server running on ws://0.0.0.0:{args.port}/ws")

    web.run_app(app, host="0.0.0.0", port=args.port, print=None)


if __name__ == "__main__":
    main()
