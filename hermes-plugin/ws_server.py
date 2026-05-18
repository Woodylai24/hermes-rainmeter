#!/usr/bin/env python3
"""
Hermes Rainmeter Plugin — WebSocket Server

aiohttp WebSocket server that bridges Rainmeter desktop widgets to the Hermes
gateway. Manages client connections, optional token auth, and message routing.

Reused from Phase 0 echo server pattern but now routes inbound messages to
the adapter instead of echoing.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Callable, Coroutine, Optional

from aiohttp import web

logger = logging.getLogger("hermes.rainmeter.ws")

# Type alias for the inbound message callback
# Receives (text: str, session_key: str) -> None
MessageCallback = Callable[[str, str], Coroutine[Any, Any, None]]


class RainmeterWSServer:
    """WebSocket server for Rainmeter client connections."""

    def __init__(
        self,
        port: int = 8643,
        auth_token: Optional[str] = None,
        on_message: Optional[MessageCallback] = None,
        on_client_connected: Optional[Callable[[], Coroutine[Any, Any, None]]] = None,
        on_client_disconnected: Optional[Callable[[], Coroutine[Any, Any, None]]] = None,
    ):
        self.port = port
        self.auth_token = auth_token
        self.on_message = on_message
        self.on_client_connected = on_client_connected
        self.on_client_disconnected = on_client_disconnected

        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._clients: set[web.WebSocketResponse] = set()
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> bool:
        """Start the WebSocket server. Returns True on success."""
        if self._running:
            logger.warning("WS server already running")
            return True

        self._app = web.Application()
        self._app["auth_token"] = self.auth_token
        self._app.router.add_get("/ws", self._websocket_handler)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        self._site = web.TCPSite(self._runner, host="0.0.0.0", port=self.port)
        try:
            await self._site.start()
        except OSError as exc:
            logger.error("Failed to start WS server on port %d: %s", self.port, exc)
            await self._runner.cleanup()
            return False

        self._running = True
        logger.info("Rainmeter WS server running on ws://0.0.0.0:%d/ws", self.port)
        if self.auth_token:
            logger.info("Token authentication enabled")
        return True

    async def stop(self) -> None:
        """Stop the server and close all client connections."""
        if not self._running:
            return

        self._running = False

        # Close all connected clients
        for ws in list(self._clients):
            try:
                await ws.close(code=1001, message=b"Server shutting down")
            except Exception:
                pass
        self._clients.clear()

        if self._runner:
            await self._runner.cleanup()
            self._runner = None

        self._site = None
        self._app = None
        logger.info("Rainmeter WS server stopped")

    # ------------------------------------------------------------------
    # Broadcasting
    # ------------------------------------------------------------------

    async def broadcast(self, message: dict) -> int:
        """Broadcast a JSON message to all connected clients.
        Returns the number of clients that received it."""
        if not self._clients:
            return 0

        raw = json.dumps(message, default=str)
        sent = 0
        dead: set[web.WebSocketResponse] = set()

        for ws in self._clients:
            try:
                await ws.send_str(raw)
                sent += 1
            except Exception:
                dead.add(ws)

        if dead:
            self._clients.difference_update(dead)
            await self._broadcast_status()

        return sent

    @property
    def client_count(self) -> int:
        """Number of currently connected clients."""
        return len(self._clients)

    # ------------------------------------------------------------------
    # WebSocket handler
    # ------------------------------------------------------------------

    async def _websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        """Handle a single WebSocket client connection."""
        token_required: Optional[str] = request.app["auth_token"]
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        # --- Connect ---
        self._clients.add(ws)
        logger.info("Client connected (total: %d)", len(self._clients))

        # Send welcome
        await ws.send_str(json.dumps({
            "type": "welcome",
            "message": "Connected to Hermes Rainmeter server",
        }))
        await self._broadcast_status()

        # --- Optional auth enforcement ---
        authenticated = True
        if token_required is not None:
            authenticated = False
            try:
                auth_raw = await asyncio.wait_for(ws.receive_str(), timeout=5.0)
                auth_msg = json.loads(auth_raw)
                if (
                    auth_msg.get("type") == "auth"
                    and auth_msg.get("token") == token_required
                ):
                    authenticated = True
                    logger.info("Client authenticated successfully")
                    await ws.send_str(json.dumps({
                        "type": "auth_ok",
                        "message": "Authentication successful",
                    }))
                else:
                    await ws.send_str(json.dumps({
                        "type": "error",
                        "message": "Authentication required",
                    }))
                    logger.warning("Client failed authentication — disconnecting")
            except asyncio.TimeoutError:
                try:
                    await ws.send_str(json.dumps({
                        "type": "error",
                        "message": "Authentication required",
                    }))
                except Exception:
                    pass
                logger.warning("Client auth timed out — disconnecting")
            except (json.JSONDecodeError, Exception) as exc:
                # Client may have disconnected during auth wait (CLOSE frame
                # causes receive_str() to raise WSMessageTypeError)
                logger.warning("Client auth failed: %s — disconnecting", exc)

        if not authenticated:
            self._clients.discard(ws)
            await ws.close()
            await self._broadcast_status()
            return ws

        # Notify adapter of new client
        if self.on_client_connected:
            await self.on_client_connected()

        # --- Message loop ---
        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    await self._handle_text(ws, msg.data)
                elif msg.type == web.WSMsgType.ERROR:
                    logger.error("WebSocket error: %s", ws.exception())
        except Exception as exc:
            logger.error("Error in message loop: %s", exc)
        finally:
            # --- Disconnect ---
            self._clients.discard(ws)
            logger.info("Client disconnected (total: %d)", len(self._clients))
            await self._broadcast_status()

            if self.on_client_disconnected:
                await self.on_client_disconnected()

        return ws

    async def _handle_text(self, ws: web.WebSocketResponse, raw: str) -> None:
        """Parse an incoming text message and route it."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            await ws.send_str(json.dumps({
                "type": "error",
                "message": f"Invalid JSON: {raw[:100]}",
            }))
            return

        msg_type = data.get("type", "")

        if msg_type == "message":
            # Inbound user message → route to adapter
            content = data.get("content", "")
            session_key = data.get("session_key", "rainmeter:desktop:default")
            if content and self.on_message:
                await self.on_message(content, session_key)
            else:
                logger.warning("Received empty message from client")

        elif msg_type == "command":
            # Command-style message (e.g., /status, /new)
            cmd = data.get("command", "")
            logger.info("Received command: %s", cmd)
            # Commands are handled as regular messages with "/" prefix
            if cmd and self.on_message:
                await self.on_message(cmd, "rainmeter:desktop:default")

        elif msg_type == "ping":
            # Keep-alive ping
            await ws.send_str(json.dumps({"type": "pong"}))

        else:
            logger.warning("Unknown message type: %s", msg_type)
            await ws.send_str(json.dumps({
                "type": "error",
                "message": f"Unknown message type: {msg_type}",
            }))

    async def _broadcast_status(self) -> None:
        """Broadcast connection count to all clients."""
        if not self._clients:
            return
        await self.broadcast({
            "type": "status",
            "connected_clients": len(self._clients),
        })
