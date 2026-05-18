# HermesRainmeter — Rainmeter C# Plugin

A Rainmeter plugin DLL that connects to the Hermes WebSocket server, enabling desktop AI chat widgets.

## Architecture

```
Rainmeter (C++) ←→ HermesRainmeter.dll (C#, unmanaged exports) ←→ ws_server.py (Python/aiohttp)
```

- **Plugin.cs** — 6 exported C functions Rainmeter calls (`Initialize`, `Finalize`, `Reload`, `Update`, `GetString`, `ExecuteBang`)
- **Measure.cs** — Per-measure state: skin config, WebSocket client, message buffer, bang callbacks
- **WebSocketClient.cs** — `System.Net.WebSockets.ClientWebSocket` with auto-reconnect
- **RainmeterAPI.cs** — P/Invoke shim to `Rainmeter.dll` (reading options, executing bangs, logging)

## Build Instructions (Visual Studio 2019+)

### Prerequisites
- **Visual Studio** with ".NET desktop development" workload
- **.NET Framework 4.7.1 Developer Pack** (usually included with VS)

### Steps

1. **Open** `HermesRainmeter.sln` in Visual Studio
2. **Restore NuGet packages**: Right-click solution → "Restore NuGet Packages"
   - This downloads `RGiesecke.DllExport` and `Newtonsoft.Json` to a `packages/` folder
3. **Build** the solution (Debug or Release, x64 or x86)
   - DllExport automatically IL-rewrites the output DLL to add unmanaged exports
4. **Copy** the output DLL from `bin/x64/Debug/` (or `Release/`) to your Rainmeter plugins folder:
   ```
   %APPDATA%\Rainmeter\Plugins\   (for 64-bit Rainmeter)
   ```

### How DllExport Works
The `RGiesecke.DllExport` NuGet package uses MSBuild targets to post-process the compiled DLL:
1. C# compiles normally → `HermesRainmeter.dll`
2. `ildasm` disassembles to IL
3. `.export` directives are injected for each `[DllExport]`-marked method
4. `ilasm` reassembles → final DLL with real unmanaged C exports

This is required because Rainmeter (C++) can only call flat C exports, not .NET managed methods.

## Testing

See `../../skins/Hermes/TestSkin.ini` for a minimal Rainmeter skin to test the plugin.

Configure the `HermesServer` variable to point at your WebSocket server:
```ini
[Variables]
HermesServer=ws://127.0.0.1:8643/ws
```
