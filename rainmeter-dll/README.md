# Hermes Rainmeter C# Plugin DLL

## Prerequisites

- **Visual Studio 2019+** or **Build Tools for Visual Studio** with .NET Framework 4.7.1 targeting pack
- **Rainmeter Plugin SDK** — [Download](https://github.com/rainmeter/rainmeter-plugin-sdk)
  - You need `DllExporter.exe` from the SDK

## Building

### Option 1: Visual Studio

1. Open `HermesRainmeter.sln` in Visual Studio
2. Set build configuration to **Release** and platform to **x64** (or **x86** for 32-bit Rainmeter)
3. Place `DllExporter.exe` in `rainmeter-dll/tools/` directory
4. Build the solution
5. Output DLL is in `HermesRainmeter/bin/Release/x64/HermesRainmeter.dll`

### Option 2: Command Line (MSBuild)

```cmd
:: Build for x64
msbuild HermesRainmeter.sln /p:Configuration=Release /p:Platform=x64

:: Build for x86
msbuild HermesRainmeter.sln /p:Configuration=Release /p:Platform=x86
```

### Option 3: Build without DllExporter (for testing compilation)

```cmd
msbuild HermesRainmeter.sln /p:Configuration=Debug /p:Platform=x64 /p:SkipDllExport=true
```

> ⚠️ The DLL won't work with Rainmeter without the DllExport step.

## Installation

1. Copy `HermesRainmeter.dll` to your Rainmeter plugins directory:
   - Per-user: `%APPDATA%\Rainmeter\Plugins\`
   - System-wide: `C:\Program Files\Rainmeter\Plugins\`
2. Copy the `skins/Hermes/` folder to your Rainmeter skins directory:
   - `%USERPROFILE%\Documents\Rainmeter\Skins\`
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

- **Newtonsoft.Json 13.0.3** — JSON serialization (NuGet)
- **System.Net.WebSockets** — Built into .NET Framework 4.7.1 (no NuGet needed)
- **Rainmeter.dll** — Rainmeter host (loaded at runtime, not a build dependency)

No ILMerge needed since we use `System.Net.WebSockets` instead of `websocket-sharp`.
