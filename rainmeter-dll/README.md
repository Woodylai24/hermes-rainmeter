# Hermes Rainmeter C# Plugin DLL

## Prerequisites

- **Visual Studio 2019+** with ".NET Framework 4.7.1 targeting pack" workload
  - In VS Installer: check "Individual Components" → ".NET Framework 4.7.1 targeting pack"

## Building

### Visual Studio

1. Open `HermesRainmeter.sln`
2. Right-click the solution → **Restore NuGet Packages** (first time only)
3. Set build config to **Release x64** (or x86 for 32-bit Rainmeter)
4. Build the solution

The DllExport NuGet package handles unmanaged export creation automatically — no external tools needed.

Output: `HermesRainmeter\bin\x64\Release\HermesRainmeter.dll`

### Command Line (MSBuild)

```cmd
:: Restore packages (first time)
msbuild HermesRainmeter.sln /t:Restore /p:Configuration=Release /p:Platform=x64

:: Build
msbuild HermesRainmeter.sln /p:Configuration=Release /p:Platform=x64
```

## Installation

1. Copy `HermesRainmeter.dll` to `%APPDATA%\Rainmeter\Plugins\`
2. Copy `skins/Hermes/` to `%USERPROFILE%\Documents\Rainmeter\Skins\`
3. Refresh Rainmeter

## Project Structure

```
HermesRainmeter/
├── Plugin.cs            — DllExport entry points (Initialize, Update, etc.)
├── Measure.cs           — Per-measure state, config reading, event handling
├── WebSocketClient.cs   — System.Net.WebSockets client with reconnect
├── RainmeterAPI.cs      — Rainmeter SDK shim (API, StringBuffer, NativeMethods)
└── HermesRainmeter.csproj
```

## How DllExport Works

Rainmeter is a C++ app that loads plugins via flat C function exports (`Initialize`, `Update`, etc.).
C# DLLs are managed .NET assemblies and don't export C functions natively.

The `DllExport` NuGet package (by 3F) solves this:
1. Compiles the C# DLL normally
2. Post-processes the IL to add unmanaged export directives
3. Reassembles into a DLL with real C entry points

No manual tools or external SDK needed.

## Architecture

```
Rainmeter skin (.ini)
  │
  ├── [Measure=Plugin] → HermesRainmeter.dll
  │     │
  │     ├── Initialize() → creates Measure + HermesWSClient
  │     ├── Update() → returns 1.0 (connected) or 0.0 (disconnected)
  │     ├── GetString() → returns last message content
  │     ├── ExecuteBang() → SendMessage, Connect, Disconnect, Ping, etc.
  │     └── Finalize() → cleanup
  │
  └── Callback bangs fire Rainmeter actions:
        OnMessage, OnConnected, OnDisconnected, OnError, OnAuthOK
```

## WebSocket Protocol

Matches the Hermes Rainmeter WS server (`hermes-plugin/ws_server.py`):

| Direction | Message |
|-----------|---------|
| Client → Server | `{"type": "message", "content": "...", "session_key": "..."}` |
| Client → Server | `{"type": "command", "command": "..."}` |
| Client → Server | `{"type": "ping"}` |
| Client → Server | `{"type": "auth", "token": "..."}` |
| Server → Client | `{"type": "message", "content": "...", "timestamp": "..."}` |
| Server → Client | `{"type": "typing", "status": true}` |
| Server → Client | `{"type": "status", "connected_clients": N}` |
| Server → Client | `{"type": "welcome", "message": "..."}` |
| Server → Client | `{"type": "auth_ok", "message": "..."}` |
| Server → Client | `{"type": "error", "message": "..."}` |
| Server → Client | `{"type": "pong"}` |

## Dependencies

- **Newtonsoft.Json 13.0.3** — JSON serialization (NuGet, auto-restored)
- **DllExport 1.7.4** — Unmanaged export creation (NuGet, auto-restored)
- **System.Net.WebSockets** — Built into .NET Framework 4.7.1 (no NuGet needed)
- **Rainmeter.dll** — Rainmeter host (loaded at runtime via P/Invoke, not a build dependency)

No ILMerge needed since we use `System.Net.WebSockets` instead of `websocket-sharp`.
