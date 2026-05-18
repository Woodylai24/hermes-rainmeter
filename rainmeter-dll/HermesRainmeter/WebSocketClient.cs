using System;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace HermesRainmeter
{
    /// <summary>
    /// WebSocket client that connects to the Hermes Rainmeter WS server.
    /// Uses System.Net.WebSockets.ClientWebSocket (no external dependency).
    /// </summary>
    public class HermesWSClient : IDisposable
    {
        private ClientWebSocket _ws;
        private CancellationTokenSource _cts;
        private Task _receiveTask;
        private readonly object _lock = new object();

        // Config
        public string ServerUrl { get; set; } = "ws://localhost:8643/ws";
        public string AuthToken { get; set; } = "";
        public bool AutoReconnect { get; set; } = true;
        public int ReconnectIntervalSec { get; set; } = 5;
        public int MaxReconnectAttempts { get; set; } = 0; // 0 = unlimited

        // State
        public bool IsConnected => _ws?.State == WebSocketState.Open;
        public bool IsRunning { get; private set; }

        // Events (fired on background thread — consumers must be thread-safe)
        public event Action<string> OnMessage;          // JSON string
        public event Action OnConnected;
        public event Action<string> OnDisconnected;     // reason
        public event Action<string> OnError;
        public event Action OnAuthOK;

        // Track last received data for Rainmeter measure access
        private string _lastMessage = "";
        public string LastMessage => _lastMessage;

        private string _lastMessageType = "";
        public string LastMessageType => _lastMessageType;

        private string _lastMessageContent = "";
        public string LastMessageContent => _lastMessageContent;

        private int _connectedClients = 0;
        public int ConnectedClients => _connectedClients;

        private bool _authenticated = false;
        public bool Authenticated => _authenticated;

        private int _reconnectAttempts = 0;

        /// <summary>
        /// Connect to the WebSocket server asynchronously.
        /// </summary>
        public async Task ConnectAsync()
        {
            if (IsRunning)
                return;

            IsRunning = true;
            _cts = new CancellationTokenSource();
            await ConnectInternal();
        }

        /// <summary>
        /// Connect to the server. Called internally and for reconnection.
        /// </summary>
        private async Task ConnectInternal()
        {
            try
            {
                _ws?.Dispose();
                _ws = new ClientWebSocket();

                await _ws.ConnectAsync(new Uri(ServerUrl), _cts.Token);

                // Connected — reset reconnect counter
                _reconnectAttempts = 0;

                OnConnected?.Invoke();

                // Start receive loop
                _receiveTask = Task.Run(() => ReceiveLoop(_cts.Token), _cts.Token);
            }
            catch (Exception ex)
            {
                OnError?.Invoke($"Connect failed: {ex.Message}");
                ScheduleReconnect();
            }
        }

        /// <summary>
        /// Main receive loop. Reads messages from the WebSocket.
        /// </summary>
        private async Task ReceiveLoop(CancellationToken ct)
        {
            var buffer = new byte[8192];

            try
            {
                while (!ct.IsCancellationRequested && _ws.State == WebSocketState.Open)
                {
                    var sb = new StringBuilder();
                    WebSocketReceiveResult result;

                    do
                    {
                        result = await _ws.ReceiveAsync(new ArraySegment<byte>(buffer), ct);
                        if (result.MessageType == WebSocketMessageType.Close)
                        {
                            await _ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "", ct);
                            break;
                        }
                        sb.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));
                    } while (!result.EndOfMessage);

                    if (result.MessageType == WebSocketMessageType.Close)
                        break;

                    string raw = sb.ToString();
                    ProcessMessage(raw);
                }
            }
            catch (OperationCanceledException)
            {
                // Normal shutdown
            }
            catch (WebSocketException ex)
            {
                OnError?.Invoke($"WebSocket error: {ex.Message}");
            }
            catch (Exception ex)
            {
                OnError?.Invoke($"Receive error: {ex.Message}");
            }
            finally
            {
                bool wasRunning = IsRunning;
                IsRunning = false;
                _authenticated = false;
                OnDisconnected?.Invoke("Connection closed");

                if (wasRunning && AutoReconnect && !ct.IsCancellationRequested)
                {
                    ScheduleReconnect();
                }
            }
        }

        /// <summary>
        /// Process a received JSON message from the server.
        /// </summary>
        private void ProcessMessage(string raw)
        {
            try
            {
                var msg = JObject.Parse(raw);
                string type = msg.Value<string>("type") ?? "";

                _lastMessage = raw;
                _lastMessageType = type;

                switch (type)
                {
                    case "welcome":
                        // Server greeting — send auth if token is configured
                        if (!string.IsNullOrEmpty(AuthToken))
                        {
                            SendRaw(JsonConvert.SerializeObject(new
                            {
                                type = "auth",
                                token = AuthToken
                            }));
                        }
                        break;

                    case "auth_ok":
                        _authenticated = true;
                        OnAuthOK?.Invoke();
                        break;

                    case "message":
                        _lastMessageContent = msg.Value<string>("content") ?? "";
                        break;

                    case "image":
                        _lastMessageContent = msg.Value<string>("url") ?? "";
                        break;

                    case "typing":
                        // Agent typing indicator
                        break;

                    case "status":
                        _connectedClients = msg.Value<int?>("connected_clients") ?? 0;
                        break;

                    case "pong":
                        // Keepalive response
                        break;

                    case "error":
                        string errorMsg = msg.Value<string>("message") ?? "Unknown error";
                        OnError?.Invoke(errorMsg);
                        break;
                }

                // Always fire OnMessage for full flexibility
                OnMessage?.Invoke(raw);
            }
            catch (JsonException)
            {
                // Non-JSON message (shouldn't happen with our server, but be safe)
                _lastMessage = raw;
                OnMessage?.Invoke(raw);
            }
        }

        /// <summary>
        /// Send a chat message to Hermes.
        /// </summary>
        public void SendMessage(string text)
        {
            var msg = new
            {
                type = "message",
                content = text,
                session_key = "rainmeter:desktop:default"
            };
            SendRaw(JsonConvert.SerializeObject(msg));
        }

        /// <summary>
        /// Send a command to Hermes (e.g., /status, /new).
        /// </summary>
        public void SendCommand(string command)
        {
            var msg = new
            {
                type = "command",
                command = command
            };
            SendRaw(JsonConvert.SerializeObject(msg));
        }

        /// <summary>
        /// Send a raw string over the WebSocket.
        /// </summary>
        public void SendRaw(string text)
        {
            if (_ws?.State != WebSocketState.Open)
            {
                OnError?.Invoke("Not connected");
                return;
            }

            try
            {
                var bytes = Encoding.UTF8.GetBytes(text);
                _ws.SendAsync(new ArraySegment<byte>(bytes), WebSocketMessageType.Text, true, _cts.Token)
                    .Wait();
            }
            catch (Exception ex)
            {
                OnError?.Invoke($"Send failed: {ex.Message}");
            }
        }

        /// <summary>
        /// Send a ping keepalive.
        /// </summary>
        public void SendPing()
        {
            SendRaw("{\"type\":\"ping\"}");
        }

        /// <summary>
        /// Schedule a reconnection attempt.
        /// </summary>
        private void ScheduleReconnect()
        {
            if (!AutoReconnect || _cts?.IsCancellationRequested == true)
                return;

            _reconnectAttempts++;
            if (MaxReconnectAttempts > 0 && _reconnectAttempts > MaxReconnectAttempts)
            {
                OnError?.Invoke($"Max reconnect attempts ({MaxReconnectAttempts}) reached");
                return;
            }

            Task.Run(async () =>
            {
                await Task.Delay(ReconnectIntervalSec * 1000, _cts.Token);
                if (!_cts.IsCancellationRequested && !IsConnected)
                {
                    try
                    {
                        await ConnectInternal();
                    }
                    catch (Exception ex)
                    {
                        OnError?.Invoke($"Reconnect failed: {ex.Message}");
                        ScheduleReconnect();
                    }
                }
            }, _cts.Token);
        }

        /// <summary>
        /// Disconnect from the server.
        /// </summary>
        public async Task DisconnectAsync()
        {
            IsRunning = false;
            AutoReconnect = false;

            _cts?.Cancel();

            if (_ws?.State == WebSocketState.Open)
            {
                try
                {
                    await _ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "Client disconnecting", CancellationToken.None);
                }
                catch { }
            }

            _receiveTask?.Wait(TimeSpan.FromSeconds(3));
        }

        public void Dispose()
        {
            IsRunning = false;
            _cts?.Cancel();
            _ws?.Dispose();
            _cts?.Dispose();
        }
    }
}
