# HermesRainmeter — C++ Plugin

A Rainmeter plugin that connects to the Hermes agent WebSocket server, enabling desktop AI chat widgets.

## Why C++ (not C#)?

The original C# approach required `RGiesecke.DllExport` NuGet package for IL rewriting to create unmanaged exports — but this package's MSBuild task is incompatible with VS 2022's 64-bit MSBuild. The C++ approach has **zero external dependencies** and builds natively.

## Build Requirements

- **Visual Studio 2022** with C++ Desktop Development workload
- **CMake** (bundled with VS 2022)
- **WinHTTP** (system library, no install needed)

## Build Steps

### Option A: Visual Studio (recommended)

1. Open the `rainmeter-dll-cpp` folder in Visual Studio 2022
2. VS will detect the `CMakeLists.txt` and offer to open as a CMake project
3. Build → Build All (x64-Debug or x64-Release)
4. Output DLL at `out/build/x64-Debug/bin/HermesRainmeter.dll` (or Release)

### Option B: Command Line

```cmd
cd rainmeter-dll-cpp
cmake -B build -A x64
cmake --build build --config Release
```

Output: `build/bin/Release/HermesRainmeter.dll`

## Install

Copy `HermesRainmeter.dll` to `%APPDATA%\Rainmeter\Plugins\`

**That's it.** No Newtonsoft.Json, no NuGet, no extra DLLs.

## Usage

See `skins/Hermes/TestSkin.ini` for a complete example skin.

### Skin Configuration

```ini
[Variables]
HermesServer=ws://localhost:8643/ws
HermesAuthToken=

[HermesMeasure]
Measure=Plugin
Plugin=HermesRainmeter.dll
Server=#HermesServer#
AuthToken=#HermesAuthToken#
AutoReconnect=1
ReconnectInterval=5
OnMessage=[!SetVariable HermesLastMsg "$message$"][!UpdateMeter MessageText]
OnConnected=[!SetOption StatusIndicator SolidColor 0,200,0,255][!UpdateMeter StatusLabel]
OnDisconnected=[!SetOption StatusIndicator SolidColor 200,0,0,255][!UpdateMeter StatusLabel]
OnError=[!SetVariable HermesError "$message$"][!UpdateMeter ErrorLabel]
```

### Bangs

- `SendMessage <text>` — Send a chat message to Hermes
- `SendCommand <cmd>` — Send a command (e.g., `/status`)
- `SendRaw <json>` — Send raw JSON
- `Connect` — Connect to server
- `Disconnect` — Disconnect from server
- `Ping` — Send keepalive ping
- `<anything else>` — Treated as a chat message

### Measure Values

- **Numeric** (Update): `1.0` = connected, `0.0` = disconnected
- **String** (GetString): Last received message content

## Architecture

```
Rainmeter skin ←→ HermesRainmeter.dll (C++) ←→ WinHTTP WebSocket ←→ Hermes WS server (Python)
```

- **Rainmeter thread**: Update, GetString, ExecuteBang
- **Background thread**: WebSocket connect/receive/reconnect loop
- **Thread-safe**: mutex-protected state shared between threads
