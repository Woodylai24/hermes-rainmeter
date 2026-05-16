# Hermes Rainmeter Plugin — References & Resources

## Rainmeter Plugin Development

### Official Documentation
- **C# Plugin API:** https://docs.rainmeter.net/developers/plugin/csharp/
- **Plugin SDK (GitHub):** https://github.com/rainmeter/rainmeter-plugin-sdk
- **Plugin measure docs:** https://docs.rainmeter.net/manual/measures/plugin/
- **Rainmeter developer docs:** https://docs.rainmeter.net/developers/

### Existing WebSocket Plugins (Study These)
| Plugin | Repo | Language | Notes |
|--------|------|----------|-------|
| WebSocketPlugins | https://github.com/ILikon/WebSocketPlugins | C# + C++ | Full WS client, reconnect, ping, command parsing. Best reference. |
| MessagePassingForRainmeter | https://github.com/tjhrulz/MessagePassingForRainmeter | C# + C | WS server for inter-app messaging. Simpler but server-only. |

### PluginWebView (Critical for Chat UI)
| Resource | URL |
|----------|-----|
| Repo | https://github.com/khanhas/PluginWebView |
| Forum thread | https://forum.rainmeter.net/viewtopic.php?t=39233 |
| WebView2 fork (newer) | https://forum.rainmeter.net/viewtopic.php?t=45787 |
| RainmeterAPI JS docs | In PluginWebView README |

**Key PluginWebView features:**
- Embeds Edge WebView2 in Rainmeter skins
- `RainmeterAPI` JavaScript object to read measures, get variables, execute bangs
- Supports CSS, SVG, Canvas, WebGL/3D
- Respects skin position, Z-index, transparency
- First load auto-prompts WebView2 runtime installation

**Known issue:** `RainmeterAPI.GetMeasure()` returns null for non-WebView measures. Workaround: export measure values to Rainmeter variables, then read via `RainmeterAPI.GetVariable()`.

**Known issue:** Resizing WebView measure recreates it (resets JS state). Workaround: set full-size dimensions, use CSS containers for visual sizing.

### Rainmeter C# Plugin API Summary

Required exports:
```csharp
[DllExport] public static void Initialize(ref IntPtr data, IntPtr rm)
[DllExport] public static void Reload(IntPtr data, IntPtr rm, ref double maxValue)
[DllExport] public static double Update(IntPtr data)
[DllExport] public static void Finalize(IntPtr data)
```

Optional exports:
```csharp
[DllExport] public static IntPtr GetString(IntPtr data)
[DllExport] public static void ExecuteBang(IntPtr data, [MarshalAs(UnmanagedType.LPWStr)] string args)
```

Custom section variable functions (any name not in the reserved set):
```csharp
[DllExport] public static IntPtr CustomFunc(IntPtr data, int argc, string[] argv)
```

---

## Hermes Agent Plugin Development

### Official Documentation
- **Plugin build guide:** https://hermes-agent.nousresearch.com/docs/guides/build-a-hermes-plugin
- **Architecture:** https://hermes-agent.nousresearch.com/docs/developer-guide/architecture.md
- **Adding platform adapters:** In-repo at `gateway/platforms/ADDING_A_PLATFORM.md`
- **Developer guide:** https://hermes-agent.nousresearch.com/docs/developer-guide/

### Source Code (Local: ~/.hermes/hermes-agent/)

| What | Path | Key Line |
|------|------|----------|
| Base platform adapter | `gateway/platforms/base.py` | Line 1259: `class BasePlatformAdapter(ABC)` |
| Platform enum (dynamic plugins) | `gateway/config.py` | Line 82: `class Platform(Enum)` |
| Platform registry | `gateway/platform_registry.py` | `PlatformEntry`, `PlatformRegistry` |
| Adding a platform guide | `gateway/platforms/ADDING_A_PLATFORM.md` | Full file |
| API server adapter (best reference) | `gateway/platforms/api_server.py` | 3,468 lines, uses aiohttp |
| Plugin platform examples | `plugins/platforms/irc/`, `plugins/platforms/teams/`, `plugins/platforms/google_chat/` | Working examples |
| Plugin manager | `hermes_cli/plugins.py` | PluginManager, PluginContext |
| Gateway runner | `gateway/run.py` | GatewayRunner — loads adapters |
| Session/message types | `gateway/platforms/base.py` | MessageEvent, MessageType, SendResult, SessionSource |

### Plugin Platform Pattern

```python
# adapter.py — everything in one file (canonical pattern from plugins/platforms/irc/)

def register(ctx):
    """Plugin entry point: called by the Hermes plugin system."""
    ctx.register_platform(
        name="rainmeter",
        label="Rainmeter",
        adapter_factory=lambda cfg: RainmeterAdapter(cfg),  # NOT adapter_class=
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

def _env_enablement() -> dict | None:
    """Seed config from env vars before adapter is created.
    Returns flat dict or None. Special 'home_channel' key
    becomes a HomeChannel dataclass on PlatformConfig.
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

### BasePlatformAdapter Key Methods

```python
class BasePlatformAdapter(ABC):
    def __init__(self, config: PlatformConfig, platform: Platform): ...
    
    # Abstract (MUST implement):
    async def connect(self) -> bool: ...
    async def disconnect(self) -> None: ...
    async def send(self, chat_id, content, reply_to=None, metadata=None) -> SendResult: ...
    async def get_chat_info(self, chat_id) -> Dict[str, Any]: ...
    
    # Concrete stubs (optional to override):
    async def send_typing(self, chat_id): ...      # no-op by default
    async def send_image(self, chat_id, image_url, caption=None): ...
    
    # Provided by base:
    def build_source(self, ...): ...         # Build SessionSource
    async def handle_message(self, event):   # Dispatch to gateway
```

---

## Libraries & Dependencies

### Hermes Side (Python)
- **aiohttp** — Already in Hermes gateway. WebSocket server + HTTP.
- **websockets** — Alternative WS library (check if available)

### Rainmeter Side (C#)
- **websocket-sharp** — https://github.com/sta/websocket-sharp — WS client library (used by WebSocketPlugins)
- **RainmeterPluginSDK** — https://github.com/rainmeter/rainmeter-plugin-sdk
- **DllExport** — NuGet package for exporting managed functions to unmanaged code
- **Newtonsoft.Json** — JSON parsing (standard, likely already needed)

### WebView2 Widgets (HTML/JS/CSS)
- **marked.js** or **markdown-it** — Markdown rendering for agent responses
- **highlight.js** or **Prism.js** — Code syntax highlighting
- No build step needed — plain HTML/CSS/JS loaded by WebView2

---

## Design Inspiration

- Discord-like chat bubbles for message history
- Telegram-style typing indicator
- Clean minimal status widget (small footprint on desktop)
- Dark theme default (matches most Rainmeter setups)
- Responsive layout for resizable widgets
