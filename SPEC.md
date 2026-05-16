# Hermes Rainmeter Plugin — Technical Specification

## Overview

A Rainmeter desktop widget that connects to the Hermes Agent gateway via WebSocket, enabling users to interact with their Hermes AI agent directly from the Windows desktop. Includes real-time chat, status dashboard, and user-customizable skins.

**No existing solution exists** — this would be the first Rainmeter ↔ AI agent gateway integration.

---

## Architecture

```
┌─────────────────────────────────────┐
│         Rainmeter Desktop           │
│                                     │
│  ┌───────────┐    ┌──────────────┐  │
│  │ Plugin DLL│◄──►│ WebView2     │  │
│  │ (C#)      │    │ Chat Widget  │  │
│  │ WebSocket │    │ HTML/CSS/JS  │  │
│  └─────┬─────┘    └──────┬───────┘  │
│        │                 │          │
│        └────────┬────────┘          │
│                 │ WebSocket         │
└─────────────────┼───────────────────┘
                  │ ws://localhost:8643
┌─────────────────┼───────────────────┐
│        Hermes Gateway               │
│                 │                   │
│         ┌───────▼────────┐          │
│         │ Rainmeter      │          │
│         │ Platform       │          │
│         │ Adapter (py)   │          │
│         └───────┬────────┘          │
│                 │                   │
│         ┌───────▼────────┐          │
│         │   AIAgent      │          │
│         │   Core Loop    │          │
│         └────────────────┘          │
└─────────────────────────────────────┘
```

### Why WebSocket + Custom DLL

- **Real-time bidirectional** — no polling delay, messages arrive instantly
- **Event-driven** — Rainmeter's default WebParser polling is outdated for chat
- **Efficient** — persistent connection vs repeated HTTP requests
- **Remote-capable** — change the server address and it works over the internet

---

## Component 1: Hermes Side — Rainmeter Platform Adapter (Python)

### Plugin Structure

```
~/.hermes/plugins/rainmeter/
├── plugin.yaml          # Manifest (kind: platform)
├── adapter.py           # RainmeterAdapter + register() + helpers (all in one file)
└── ws_server.py         # WebSocket server
```

### Implementation Details

The Hermes gateway supports adding new platforms via plugins with **zero core code changes**. The `Platform` enum dynamically accepts plugin platform names via `_missing_()`, and `BasePlatformAdapter` handles 90% of the plumbing.

**Reference:** `gateway/platforms/ADDING_A_PLATFORM.md` in the Hermes source.

#### plugin.yaml

```yaml
name: rainmeter-platform
label: Rainmeter
kind: platform
version: 1.0.0
description: >
  Rainmeter desktop widget gateway for Hermes Agent.
  Embeds a WebSocket server that Rainmeter skins connect to,
  enabling real-time chat and status monitoring from the Windows desktop.
author: Woody
requires_env: []
optional_env:
  - name: RAINMETER_WS_PORT
    description: "WebSocket port for Rainmeter plugin (default: 8643)"
    prompt: "WebSocket port"
    password: false
  - name: RAINMETER_AUTH_TOKEN
    description: "Auth token for Rainmeter connections (optional, for remote access)"
    prompt: "Auth token (optional)"
    password: true
  - name: RAINMETER_HOME_CHANNEL
    description: "Default channel ID for Rainmeter messages"
    prompt: "Home channel ID (optional)"
    password: false
```

#### __init__.py — Registration

The registration entry point lives in `adapter.py` (not a separate `__init__.py`)
to match the canonical plugin pattern used by `plugins/platforms/irc/`.

```python
# adapter.py (bottom of file)

def register(ctx):
    """Plugin entry point: called by the Hermes plugin system."""
    ctx.register_platform(
        name="rainmeter",
        label="Rainmeter",
        adapter_factory=lambda cfg: RainmeterAdapter(cfg),
        check_fn=check_requirements,
        validate_config=validate_config,
        is_connected=is_connected,
        required_env=[],            # no mandatory env vars (port has default)
        install_hint="aiohttp is bundled with the Hermes gateway",
        env_enablement_fn=_env_enablement,
        cron_deliver_env_var="RAINMETER_HOME_CHANNEL",
        emoji="🖥️",
        platform_hint="You are chatting via a Rainmeter desktop widget.",
        allow_update_command=True,
    )

def check_requirements():
    """Verify aiohttp is available (bundled with gateway)."""
    try:
        import aiohttp
        return True
    except ImportError:
        return False

def validate_config(config):
    """Validate Rainmeter platform config."""
    extra = getattr(config, "extra", {}) or {}
    port = extra.get("ws_port", 8643)
    if not isinstance(port, int) or port < 1 or port > 65535:
        return f"Invalid ws_port: {port}"
    return None

def is_connected(config):
    """Rainmeter is always 'connected' when the WS server is running."""
    return True

def _env_enablement() -> dict | None:
    """Seed PlatformConfig.extra from env vars before adapter construction.

    Returns None when no env vars are set (plugin won't auto-enable).
    The special ``home_channel`` key is handled by the core hook —
    it becomes a proper HomeChannel dataclass on PlatformConfig.
    """
    import os
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
```

#### adapter.py — Platform Adapter

Must inherit from `BasePlatformAdapter` (defined in `gateway/platforms/base.py`).

**Required abstract methods** (must implement):

| Method | Purpose |
|--------|---------|
| `__init__(self, config)` | Parse config, init state. Call `super().__init__(config, Platform("rainmeter"))` |
| `connect() -> bool` | Start WebSocket server, return True on success |
| `disconnect()` | Stop WS server, close all client connections |
| `send(chat_id, content, ...) -> SendResult` | Push message to connected Rainmeter clients via WS |
| `get_chat_info(chat_id) -> dict` | Return `{name, type, chat_id}` |

**Optional overrides** (concrete stubs in base class, safe to skip):

| Method | Purpose |
|--------|---------|
| `send_typing(chat_id)` | Emit typing/status event to clients |
| `send_image(chat_id, image_url, caption) -> SendResult` | Send image URL to clients |

**Key patterns:**
- Use `self.build_source(...)` to construct `SessionSource` objects
- Call `self.handle_message(event)` to dispatch inbound messages to the gateway
- Use `MessageEvent`, `MessageType`, `SendResult` from `gateway/platforms/base.py`

**Reference adapter:** `gateway/platforms/api_server.py` (3,468 lines, production-grade, uses aiohttp).

#### ws_server.py — WebSocket Server

- Use `aiohttp.web` (already available in the gateway)
- Listen on configurable port (default 8643)
- Handle auth via token (optional for local connections)
- Broadcast messages to all connected clients
- Accept incoming messages and route to adapter

**WebSocket Protocol (JSON messages):**

```json
// Client → Server (Rainmeter → Hermes)
{
  "type": "message",
  "content": "Hello Hermes!",
  "session_key": "rainmeter:desktop:default"
}

{
  "type": "command",
  "command": "/status"
}

// Server → Client (Hermes → Rainmeter)
{
  "type": "message",
  "content": "Here's your answer...",
  "timestamp": "2026-05-17T00:30:00Z"
}

{
  "type": "typing",
  "status": true
}

{
  "type": "status",
  "connected": true,
  "session_id": "abc123",
  "agent_busy": true
}

{
  "type": "error",
  "message": "Connection lost"
}
```

---

## Component 2: Rainmeter Side — C# Plugin DLL

### Rainmeter C# Plugin SDK

The plugin must export these functions (from Rainmeter Plugin SDK on GitHub):

| Export | Required? | Purpose |
|--------|-----------|---------|
| `Initialize(ref IntPtr data, IntPtr rm)` | ✅ | Create measure object, init WS connection |
| `Reload(IntPtr data, IntPtr rm, ref double maxValue)` | ✅ | Read skin config (server address, auth, etc.) |
| `Update(IntPtr data) -> double` | ✅ | Return numeric value (1=connected, 0=disconnected) |
| `GetString(IntPtr data) -> IntPtr` | ✅ | Return string value (last message, status text) |
| `ExecuteBang(IntPtr data, string args)` | Optional | Handle bangs: SendMessage, Connect, Disconnect |
| `Finalize(IntPtr data)` | ✅ | Cleanup, close WebSocket |

### DLL Configuration (in skin .ini)

```ini
[Rainmeter]
Measure=Plugin
Plugin=HermesRainmeter.dll

; Connection settings
Server=ws://localhost:8643
AuthToken=
Reconnect=true
MaxReconnectAttempts=0

; Callbacks — Rainmeter bangs executed on events
OnMessage=[!SetVariable HermesLastMsg "$message$"]
OnStatusChange=[!UpdateMeter StatusIndicator]
OnConnected=[!ShowMeter StatusDot][!SetVariable HermesStatus "Connected"]
OnDisconnected=[!HideMeter StatusDot][!SetVariable HermesStatus "Disconnected"]
OnError=[!SetVariable HermesError "$message$"]
```

### Bang Commands

Users trigger these via `!CommandMeasure`:

| Bang | Description |
|------|-------------|
| `SendMessage <text>` | Send a chat message to Hermes |
| `Connect` | Manually connect to the WebSocket server |
| `Disconnect` | Close the connection |
| `ResetSession` | Start a fresh conversation |
| `SetVariable <key> <value>` | Update runtime configuration |

### Dependencies

- **websocket-sharp** — WebSocket client library (used by existing WebSocketPlugins for Rainmeter)
- **RainmeterPluginSDK** — From https://github.com/rainmeter/rainmeter-plugin-sdk
- **DllExport** — For exporting C# functions to unmanaged code

### Reference Plugins

| Plugin | Repo | What to study |
|--------|------|---------------|
| WebSocketPlugins | https://github.com/ILikon/WebSocketPlugins | C# WebSocket client pattern in Rainmeter DLL |
| MessagePassingForRainmeter | https://github.com/tjhrulz/MessagePassingForRainmeter | Simpler WS server plugin, bang event pattern |
| PluginWebView | https://github.com/khanhas/PluginWebView | WebView2 integration, JS↔Rainmeter bridge |

---

## Component 3: Skins & WebView2 Widgets

### Why PluginWebView Changes the Game

PluginWebView embeds Microsoft Edge WebView2 into Rainmeter skins, allowing full HTML/CSS/JS rendering. This means the chat widget can be genuinely beautiful (Discord-like chat bubbles, typing indicators, code highlighting, markdown rendering) instead of being limited to Rainmeter's native meter system.

### Skin Package Structure

```
Rainmeter/Skins/Hermes/
├── @Resources/
│   ├── HermesConfig.inc         # User-configurable variables
│   │                            #   - Server URL
│   │                            #   - Auth token
│   │                            #   - Theme selection
│   │                            #   - Widget dimensions
│   ├── HermesStyles.inc         # Visual style variables (colors, fonts, sizes)
│   └── WebView/
│       ├── chat.html            # Chat widget (WebView2)
│       ├── dashboard.html       # Status dashboard (WebView2)
│       ├── css/
│       │   ├── base.css         # Shared styles
│       │   ├── theme-dark.css   # Dark theme
│       │   ├── theme-light.css  # Light theme
│       │   └── custom.css       # User overrides (documented, safe to edit)
│       └── js/
│           ├── hermes-ws.js     # WebSocket client library (reusable)
│           └── hermes-ui.js     # UI rendering logic
├── Status/
│   └── Status.ini               # Native Rainmeter status indicator (small)
├── Chat/
│   └── Chat.ini                 # WebView2-powered chat widget
├── Dashboard/
│   └── Dashboard.ini            # WebView2 status dashboard
└── QuickToggle/
    └── Toggle.ini               # Minimal on/off toggle
```

### HermesConfig.inc (User-Configurable)

```ini
; ============================================
; Hermes Rainmeter Plugin — User Configuration
; ============================================

; Connection
HermesServer=ws://localhost:8643
HermesAuthToken=
HermesReconnect=true

; Appearance
HermesTheme=dark
HermesFont=Segoe UI
HermesFontSize=12

; Chat Widget
ChatWidth=350
ChatHeight=500
ChatPositionX=1500
ChatPositionY=100

; Dashboard Widget
DashboardWidth=250
DashboardHeight=150
```

### Widget Descriptions

1. **Status** — Small native Rainmeter meter. Shows connection dot (green/red), last activity time. Minimal footprint.

2. **Chat** — WebView2 widget with:
   - Message history with scrolling
   - Input field (HTML input, not Rainmeter's limited text input)
   - Typing indicator animation
   - Markdown rendering for responses
   - Code block highlighting
   - Theme-aware styling

3. **Dashboard** — WebView2 widget with:
   - Connection status
   - Current session info
   - Agent busy/idle state
   - Quick action buttons (new session, connect, disconnect)
   - Last message preview

4. **QuickToggle** — Tiny native Rainmeter meter for showing/hiding the chat widget

### RainmeterAPI (JavaScript Interface)

PluginWebView exposes `RainmeterAPI` in JS to interact with Rainmeter:
- `RainmeterAPI.GetMeasure("MeasureName")` — Get measure values
- `RainmeterAPI.GetVariable("VarName")` — Read Rainmeter variables
- `RainmeterAPI.Bang("[!CommandMeasure ...]")` — Execute Rainmeter bangs

This allows the chat widget to trigger Rainmeter actions (e.g., hide widget, update status meter) from JavaScript.

---

## Remote Access

For remote access, users simply change the server URL:
```ini
HermesServer=wss://your-server.com:8643
```

For production remote access, recommend:
1. TLS termination via nginx/Caddy reverse proxy
2. Auth token required
3. WebSocket secure (wss://)

---

## Hermes Source Code Pointers

All paths relative to `~/.hermes/hermes-agent/`:

| What | Path |
|------|------|
| Platform adapter base class | `gateway/platforms/base.py` (line 1259) |
| Adding a platform guide | `gateway/platforms/ADDING_A_PLATFORM.md` |
| Platform enum (supports dynamic plugins) | `gateway/config.py` (line 82) |
| Platform registry | `gateway/platform_registry.py` |
| API server adapter (reference) | `gateway/platforms/api_server.py` (3,468 lines) |
| Plugin platform examples | `plugins/platforms/irc/`, `plugins/platforms/teams/`, `plugins/platforms/google_chat/` |
| Plugin system | `hermes_cli/plugins.py` — PluginManager |
| Plugin build guide | https://hermes-agent.nousresearch.com/docs/guides/build-a-hermes-plugin |
