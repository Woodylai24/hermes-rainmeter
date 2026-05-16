# Phase 0 Spec: WebSocket Round-Trip Prototype

## Goal

Validate the Rainmeter ↔ WebSocket ↔ Python boundary before building the full Hermes adapter.

## Deliverables

1. **`echo_server.py`** — Standalone aiohttp WebSocket echo server
2. **`test_client.html`** — Single-file HTML test page for manual browser testing

## File Locations

All files in `~/Projects/hermes-rainmeter/prototype/`:

```
prototype/
├── echo_server.py      # WebSocket echo server
└── test_client.html    # Browser-based test client
```

## Component 1: echo_server.py

### Requirements

- Use `aiohttp.web` (already available in Hermes venv)
- Listen on configurable port (default 8643), via `--port` CLI arg
- Accept WebSocket connections at path `/ws`
- Echo back any received JSON message with an added `echo: true` field
- Broadcast status events when clients connect/disconnect
- Optional token auth: if `--token <value>` is passed, require clients to send `{"type": "auth", "token": "<value>"}` as their first message within 5 seconds or be disconnected
- Log connections, disconnections, and messages to stdout
- Handle graceful shutdown on Ctrl+C

### WebSocket Protocol (for prototype)

```
Client → Server:
  {"type": "message", "content": "hello"}
  {"type": "auth", "token": "secret123"}   # only if --token is set

Server → Client:
  {"type": "echo", "content": "hello", "original": {...}}
  {"type": "status", "connected_clients": 1}
  {"type": "error", "message": "auth required"}
  {"type": "welcome", "message": "Connected to Hermes echo server"}
```

### CLI

```
python echo_server.py [--port 8643] [--token SECRET]
```

### Behavior

1. On client connect: send `{"type": "welcome", ...}`, broadcast status to all clients
2. On message: echo it back with `{"type": "echo", ...}`, log to stdout
3. On client disconnect: broadcast updated status to remaining clients
4. Auth mode: if `--token` set, disconnect clients that don't auth within 5 seconds

## Component 2: test_client.html

### Requirements

- Single self-contained HTML file (no external dependencies)
- Opens WebSocket connection to `ws://localhost:8643/ws`
- Shows connection status (green/red indicator)
- Text input + send button
- Message log showing sent and received messages with timestamps
- Auto-scroll to latest message
- Dark theme (matches typical Rainmeter aesthetic)
- Connection URL configurable via input field at top

### Layout

```
┌─────────────────────────────────┐
│ Hermes WS Test Client    ● ON   │
│ [ ws://localhost:8643/ws ] [Go] │
├─────────────────────────────────┤
│                                 │
│ [14:30:01] >> hello             │
│ [14:30:01] << {"type":"echo"...│
│ [14:30:05] >> test message      │
│ [14:30:05] << {"type":"echo"...│
│                                 │
├─────────────────────────────────┤
│ [Type a message...      ] [Send]│
└─────────────────────────────────┘
```

## Testing Plan

After implementation, verify:

1. Start server: `python prototype/echo_server.py`
2. Open `test_client.html` in browser (just double-click the file)
3. Verify "Connected" status shows
4. Type a message, click Send
5. Verify echo response appears in log
6. Open second browser tab with same page
7. Verify both clients see status updates (connected_clients: 2)
8. Kill server, verify client shows "Disconnected"
9. Restart server, verify client can reconnect
10. Test auth: restart with `--token test123`, verify unauthed client gets disconnected

## Out of Scope

- Rainmeter skin (Woody tests manually on Windows)
- Hermes gateway integration (Phase 1)
- TLS/WSS (Phase 4)
- Multi-session routing
