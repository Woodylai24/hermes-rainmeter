#!/usr/bin/env python3
"""
Hermes Rainmeter Plugin — Platform Adapter

A Hermes BasePlatformAdapter subclass that embeds a WebSocket server,
allowing Rainmeter desktop widgets (or any WS client) to chat with
the Hermes agent in real time.

Single-file adapter following the canonical plugin pattern
(matching plugins/platforms/irc/adapter.py).
"""

import logging
import os
import time
from typing import Any, Dict, Optional

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
)

# Import ws_server from the same plugin directory.
# The Hermes plugin loader imports us via spec_from_file_location,
# so bare imports don't work — we need a relative or path-based import.
import importlib.util as _ilu
import os as _os

_ws_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "ws_server.py")
_ws_spec = _ilu.spec_from_file_location("hermes_plugins.rainmeter_ws_server", _ws_path)
_ws_mod = _ilu.module_from_spec(_ws_spec)
_ws_spec.loader.exec_module(_ws_mod)
RainmeterWSServer = _ws_mod.RainmeterWSServer

logger = logging.getLogger("hermes.rainmeter")


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class RainmeterAdapter(BasePlatformAdapter):
    """Hermes platform adapter for Rainmeter desktop widgets."""

    def __init__(self, config: PlatformConfig, **kwargs):
        platform = Platform("rainmeter")
        super().__init__(config=config, platform=platform)

        extra = getattr(config, "extra", {}) or {}
        self._ws_port: int = extra.get("ws_port", 8643)
        self._auth_token: Optional[str] = extra.get("auth_token")

        # Determine home chat_id for inbound messages
        home = getattr(config, "home_channel", None)
        self._home_chat_id: str = "rainmeter:desktop"
        if home:
            # home_channel is a HomeChannel dataclass with chat_id attr
            self._home_chat_id = getattr(home, "chat_id", str(home))

        self._ws_server: Optional[RainmeterWSServer] = None
        self._session_counter: int = 0

    # -- BasePlatformAdapter overrides ------------------------------------

    @property
    def name(self) -> str:
        return "Rainmeter"

    async def connect(self) -> bool:
        """Start the WebSocket server."""
        logger.info(
            "Rainmeter adapter connecting (port=%d, auth=%s)",
            self._ws_port,
            "enabled" if self._auth_token else "disabled",
        )

        self._ws_server = RainmeterWSServer(
            port=self._ws_port,
            auth_token=self._auth_token,
            on_message=self._on_ws_message,
            on_client_connected=self._on_client_connected,
            on_client_disconnected=self._on_client_disconnected,
        )

        ok = await self._ws_server.start()
        if ok:
            self._mark_connected()
            logger.info("Rainmeter adapter connected")
        else:
            self._set_fatal_error(
                "ws_start_failed",
                f"Could not start WS server on port {self._ws_port}",
                retryable=True,
            )
        return ok

    async def disconnect(self) -> None:
        """Stop the WebSocket server."""
        logger.info("Rainmeter adapter disconnecting")
        if self._ws_server:
            await self._ws_server.stop()
            self._ws_server = None
        self._mark_disconnected()

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a message to Rainmeter clients via WebSocket."""
        if not self._ws_server:
            return SendResult(success=False, error="WS server not running")

        message = {
            "type": "message",
            "content": content,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if reply_to:
            message["reply_to"] = reply_to

        sent = await self._ws_server.broadcast(message)
        if sent > 0:
            return SendResult(success=True, message_id=f"ws-{int(time.time()*1000)}")
        else:
            return SendResult(
                success=False,
                error="No connected Rainmeter clients",
                retryable=True,
            )

    async def send_typing(self, chat_id: str, metadata=None) -> None:
        """Emit typing indicator to connected clients."""
        if self._ws_server:
            await self._ws_server.broadcast({
                "type": "typing",
                "status": True,
            })

    async def send_image(
        self,
        chat_id: str,
        image_url: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send an image URL to connected Rainmeter clients."""
        if not self._ws_server:
            return SendResult(success=False, error="WS server not running")

        message = {
            "type": "image",
            "url": image_url,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if caption:
            message["caption"] = caption

        sent = await self._ws_server.broadcast(message)
        if sent > 0:
            return SendResult(success=True, message_id=f"ws-img-{int(time.time()*1000)}")
        else:
            return SendResult(
                success=False,
                error="No connected Rainmeter clients",
                retryable=True,
            )

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        """Return metadata about the Rainmeter chat session."""
        return {
            "name": "Rainmeter Desktop",
            "type": "dm",
            "chat_id": chat_id,
        }

    # -- WS event handlers ------------------------------------------------

    async def _on_ws_message(self, text: str, session_key: str) -> None:
        """Handle an inbound message from a Rainmeter client."""
        self._session_counter += 1
        source = self.build_source(
            chat_id=self._home_chat_id,
            chat_name="Rainmeter Desktop",
            chat_type="dm",
            user_id="rainmeter-user",
            user_name="Rainmeter User",
        )
        event = MessageEvent(
            text=text,
            message_type=MessageType.TEXT,
            source=source,
            message_id=f"rm-{int(time.time()*1000)}-{self._session_counter}",
        )
        await self.handle_message(event)

    async def _on_client_connected(self) -> None:
        """Handle a new Rainmeter client connecting."""
        logger.info("Rainmeter client connected (total: %d)",
                     self._ws_server.client_count if self._ws_server else 0)

    async def _on_client_disconnected(self) -> None:
        """Handle a Rainmeter client disconnecting."""
        logger.info("Rainmeter client disconnected (total: %d)",
                     self._ws_server.client_count if self._ws_server else 0)


# ---------------------------------------------------------------------------
# Plugin registration (entry point called by Hermes plugin system)
# ---------------------------------------------------------------------------


def check_requirements() -> bool:
    """Verify aiohttp is available (bundled with gateway)."""
    try:
        import aiohttp  # noqa: F401
        return True
    except ImportError:
        return False


def validate_config(config) -> bool:
    """Validate Rainmeter platform config. Returns True if valid, False otherwise."""
    extra = getattr(config, "extra", {}) or {}
    port = extra.get("ws_port", 8643)
    if not isinstance(port, int) or port < 1 or port > 65535:
        return False
    return True


def is_connected(config) -> bool:
    """Rainmeter is 'connected' when the WS server is running."""
    return True


def _env_enablement() -> Optional[dict]:
    """Seed PlatformConfig.extra from env vars before adapter construction.

    Returns None when no env vars are set (plugin won't auto-enable).
    The special ``home_channel`` key is handled by the core hook —
    it becomes a proper HomeChannel dataclass on PlatformConfig.
    """
    seed: dict = {}
    port = os.getenv("RAINMETER_WS_PORT", "").strip()
    if port:
        try:
            seed["ws_port"] = int(port)
        except ValueError:
            pass
    token = os.getenv("RAINMETER_AUTH_TOKEN", "").strip()
    if token:
        seed["auth_token"] = token
    home = os.getenv("RAINMETER_HOME_CHANNEL", "").strip()
    if home:
        seed["home_channel"] = {"chat_id": home, "name": "Rainmeter Desktop"}
    return seed if seed else None


def register(ctx):
    """Plugin entry point: called by the Hermes plugin system."""
    ctx.register_platform(
        name="rainmeter",
        label="Rainmeter",
        adapter_factory=lambda cfg: RainmeterAdapter(cfg),
        check_fn=check_requirements,
        validate_config=validate_config,
        is_connected=is_connected,
        required_env=[],
        install_hint="aiohttp is bundled with the Hermes gateway",
        env_enablement_fn=_env_enablement,
        cron_deliver_env_var="RAINMETER_HOME_CHANNEL",
        emoji="🖥️",
        platform_hint="You are chatting via a Rainmeter desktop widget.",
        allow_update_command=True,
    )
