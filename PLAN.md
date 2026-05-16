# Hermes Rainmeter Plugin — Development Plan

## Phased Approach

Each phase produces a working deliverable. Build incrementally.

---

## Phase 0: WebSocket Round-Trip Prototype

**Goal:** Validate the Rainmeter ↔ WebSocket ↔ Python boundary before building the full adapter.

**Tasks:**

1. **Standalone WS echo server** (Python, no Hermes)
   - aiohttp server on port 8643
   - Echo back any received message
   - Test with `wscat` or a simple HTML page

2. **Minimal Rainmeter test skin**
   - Use an existing WebSocket Rainmeter plugin (e.g., WebSocketPlugins) to connect
   - Send a message, verify echo arrives back
   - De-risks the C# ↔ Python WS boundary early

**Deliverable:** Proof that Rainmeter can talk to a Python WebSocket server and get responses.

---

## Phase 1: Hermes Adapter Plugin (Python)

**Goal:** Working WebSocket server as a Hermes platform plugin that can receive and send messages.

**Tasks:**

1. **Scaffold plugin directory** at `~/.hermes/plugins/rainmeter/`
   - `plugin.yaml` — manifest with `kind: platform`, env vars with `prompt`/`password` fields
   - `adapter.py` — `RainmeterAdapter(BasePlatformAdapter)` + `register()`, `check_requirements()`, `_env_enablement()` etc. (all in one file, matching the IRC plugin pattern)
   - `ws_server.py` — aiohttp WebSocket server

2. **Implement WebSocket server** (`ws_server.py`)
   - aiohttp server on configurable port (default 8643)
   - Handle client connections, track connected clients
   - Parse incoming JSON messages → route to adapter
   - Broadcast outgoing messages to all connected clients
   - Optional token auth

3. **Implement adapter** (`adapter.py`)
   - `connect()` — start WS server
   - `disconnect()` — stop WS server, close connections
   - `send()` — push message to clients via WS
   - `send_typing()` — emit typing event
   - `get_chat_info()` — return desktop session metadata
   - Inbound message handling: WS message → `MessageEvent` → `self.handle_message()`

4. **Test with a simple WS client** (wscat or Python script)
   - Send a message to Hermes via WebSocket
   - Verify Hermes response arrives back via WebSocket
   - Test typing indicators
   - Test connection/disconnection

**Deliverable:** Hermes gateway accepts Rainmeter as a platform. You can chat with Hermes from any WebSocket client.

**Reference files:**
- `~/.hermes/hermes-agent/gateway/platforms/base.py` — BasePlatformAdapter
- `~/.hermes/hermes-agent/gateway/platforms/api_server.py` — Full reference adapter
- `~/.hermes/hermes-agent/gateway/platforms/ADDING_A_PLATFORM.md` — Step-by-step guide
- `~/.hermes/hermes-agent/plugins/platforms/irc/` — Minimal plugin platform example

---

## Phase 2: Rainmeter C# Plugin DLL

**Goal:** A Rainmeter plugin DLL that connects to the Hermes WS server and exposes measures/bangs.

**Tasks:**

1. **Set up C# project**
   - Use RainmeterPluginSDK from https://github.com/rainmeter/rainmeter-plugin-sdk
   - Add websocket-sharp dependency (NuGet)
   - Configure DllExport for Rainmeter compatibility
   - Target .NET Framework 4.6+ (Rainmeter requirement) or whatever the SDK uses

2. **Implement WebSocket client**
   - Connect to configurable WS server address
   - Auto-reconnect with configurable retry
   - Parse incoming JSON messages → trigger Rainmeter bangs
   - Handle disconnection events

3. **Implement Rainmeter measure API**
   - `Initialize` — create measure, read config, init WS
   - `Reload` — re-read skin settings (supports DynamicVariables)
   - `Update` — return connection status (1.0 / 0.0)
   - `GetString` — return last received message or status string
   - `ExecuteBang` — handle SendMessage, Connect, Disconnect
   - `Finalize` — cleanup

4. **Build and test**
   - Compile DLL, place in `Rainmeter/Plugins/`
   - Create minimal test skin that shows connection status
   - Test sending/receiving messages via bangs

**Deliverable:** Rainmeter can connect to Hermes via the plugin DLL. Messages flow both ways.

**Reference repos:**
- https://github.com/ILikon/WebSocketPlugins — C# WebSocket client pattern
- https://github.com/tjhrulz/MessagePassingForRainmeter — Simpler WS plugin
- https://github.com/rainmeter/rainmeter-plugin-sdk — Official SDK

---

## Phase 3: Default Skins

**Goal:** Beautiful, functional default skins using native Rainmeter meters + PluginWebView.

**Tasks:**

1. **Status widget** (native Rainmeter)
   - Small connection indicator (green/red dot)
   - Agent busy/idle status
   - Last activity timestamp
   - Uses plugin DLL measure directly

2. **Chat widget** (PluginWebView)
   - HTML/CSS/JS chat interface
   - Message history with auto-scroll
   - Text input field (proper HTML input, not Rainmeter's limited input)
   - Typing indicator
   - Markdown rendering for agent responses
   - Code block syntax highlighting
   - Dark/light theme support

3. **Dashboard widget** (PluginWebView)
   - Connection status
   - Session info
   - Quick actions (new session, connect/disconnect)
   - Last message preview

4. **Configuration system**
   - `HermesConfig.inc` — user variables (server, port, theme, dimensions)
   - `HermesStyles.inc` — visual variables (colors, fonts)
   - Well-commented, documented for easy customization

**Deliverable:** A polished Rainmeter skin package that users can install and customize.

**Reference:** https://github.com/khanhas/PluginWebView — WebView2 integration examples

---

## Phase 4: Documentation & Polish

**Tasks:**

1. **Skin authoring guide** — How to create custom widgets
2. **API documentation** — WebSocket protocol, measure variables, bangs
3. **Installation guide** — Step-by-step setup for Hermes + Rainmeter
4. **Example custom skins** — 2-3 alternative designs
5. **Error handling** — Graceful failures, reconnection UX
6. **TLS support** — WSS for remote access
7. **Media support** — Image display in chat widget

---

## Project Directory

Development happens in `~/Projects/hermes-rainmeter/`:

```
~/Projects/hermes-rainmeter/
├── SPEC.md                          # This spec
├── PLAN.md                          # This plan
├── REFERENCES.md                    # Links and references
├── hermes-plugin/                   # Hermes adapter plugin
│   ├── plugin.yaml                  # Platform manifest (kind: platform)
│   ├── adapter.py                   # RainmeterAdapter + register() + helpers
│   └── ws_server.py                 # aiohttp WebSocket server
├── rainmeter-dll/                   # C# plugin DLL source
│   ├── HermesRainmeter.sln
│   ├── HermesRainmeter/
│   │   ├── HermesRainmeter.csproj
│   │   ├── Measure.cs
│   │   ├── WebSocketClient.cs
│   │   └── Plugin.cs
│   └── README.md
├── skins/                           # Rainmeter skin package
│   ├── Hermes/
│   │   ├── @Resources/
│   │   ├── Status/
│   │   ├── Chat/
│   │   ├── Dashboard/
│   │   └── QuickToggle/
│   └── README.md
└── docs/                            # Documentation
    ├── INSTALL.md
    ├── SKIN-AUTHORING.md
    ├── API.md
    └── EXAMPLES/
```
