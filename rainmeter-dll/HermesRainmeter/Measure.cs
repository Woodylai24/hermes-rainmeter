using System;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using Rainmeter;

namespace HermesRainmeter
{
    /// <summary>
    /// Per-measure state for a HermesRainmeter plugin instance.
    /// Each [HermesMeasure] section in a skin creates one Measure.
    /// </summary>
    public class Measure
    {
        // --- Configuration (read from skin .ini) ---
        public string ServerUrl = "ws://localhost:8643/ws";
        public string AuthToken = "";
        public bool AutoReconnect = true;
        public int ReconnectIntervalSec = 5;
        public int MaxReconnectAttempts = 0;

        // Callback bangs (Rainmeter bangs executed on events)
        public string OnMessageBang = "";
        public string OnConnectedBang = "";
        public string OnDisconnectedBang = "";
        public string OnErrorBang = "";
        public string OnAuthOKBang = "";

        // --- Runtime state ---
        public HermesWSClient Client;
        public IntPtr Skin = IntPtr.Zero;
        public bool Disposed = false;

        // Thread-safe last values for Rainmeter queries
        private readonly object _stateLock = new object();
        private bool _isConnected = false;
        private string _lastMessage = "";
        private string _lastMessageType = "";
        private string _lastMessageContent = "";

        /// <summary>
        /// Implicit cast from IntPtr (GCHandle) to Measure.
        /// </summary>
        public static implicit operator Measure(IntPtr data)
        {
            return (Measure)GCHandle.FromIntPtr(data).Target;
        }

        /// <summary>
        /// Initialize the measure: read config and connect.
        /// Called from the exported Initialize function.
        /// </summary>
        public void Initialize(API api)
        {
            Skin = api.GetSkin();

            // Read configuration from skin .ini
            ServerUrl = api.ReadString("Server", "ws://localhost:8643/ws");
            AuthToken = api.ReadString("AuthToken", "");
            AutoReconnect = api.ReadInt("AutoReconnect", 1) != 0;
            ReconnectIntervalSec = api.ReadInt("ReconnectInterval", 5);
            MaxReconnectAttempts = api.ReadInt("MaxReconnectAttempts", 0);

            // Read callback bangs
            OnMessageBang = api.ReadString("OnMessage", "");
            OnConnectedBang = api.ReadString("OnConnected", "");
            OnDisconnectedBang = api.ReadString("OnDisconnected", "");
            OnErrorBang = api.ReadString("OnError", "");
            OnAuthOKBang = api.ReadString("OnAuthOK", "");

            // Create and configure the WS client
            Client = new HermesWSClient
            {
                ServerUrl = ServerUrl,
                AuthToken = AuthToken,
                AutoReconnect = AutoReconnect,
                ReconnectIntervalSec = ReconnectIntervalSec,
                MaxReconnectAttempts = MaxReconnectAttempts,
            };

            // Wire up events
            Client.OnMessage += (raw) =>
            {
                lock (_stateLock)
                {
                    _lastMessage = Client.LastMessage;
                    _lastMessageType = Client.LastMessageType;
                    _lastMessageContent = Client.LastMessageContent;
                }
                ExecuteBang(OnMessageBang, raw);
            };

            Client.OnConnected += () =>
            {
                lock (_stateLock)
                {
                    _isConnected = true;
                }
                ExecuteBang(OnConnectedBang, "connected");
            };

            Client.OnDisconnected += (reason) =>
            {
                lock (_stateLock)
                {
                    _isConnected = false;
                }
                ExecuteBang(OnDisconnectedBang, reason);
            };

            Client.OnError += (error) =>
            {
                ExecuteBang(OnErrorBang, error);
            };

            Client.OnAuthOK += () =>
            {
                ExecuteBang(OnAuthOKBang, "authenticated");
            };

            // Connect asynchronously
            Client.ConnectAsync();

            api.Log(API.LogType.Notice, $"HermesRainmeter: Initialized (server={ServerUrl})");
        }

        /// <summary>
        /// Reload config when skin is refreshed.
        /// </summary>
        public void Reload(API api)
        {
            // Re-read all settings
            ServerUrl = api.ReadString("Server", "ws://localhost:8643/ws");
            AuthToken = api.ReadString("AuthToken", "");
            AutoReconnect = api.ReadInt("AutoReconnect", 1) != 0;
            ReconnectIntervalSec = api.ReadInt("ReconnectInterval", 5);
            MaxReconnectAttempts = api.ReadInt("MaxReconnectAttempts", 0);

            OnMessageBang = api.ReadString("OnMessage", "");
            OnConnectedBang = api.ReadString("OnConnected", "");
            OnDisconnectedBang = api.ReadString("OnDisconnected", "");
            OnErrorBang = api.ReadString("OnError", "");
            OnAuthOKBang = api.ReadString("OnAuthOK", "");

            // Update client config (will take effect on next connect)
            if (Client != null)
            {
                Client.ServerUrl = ServerUrl;
                Client.AuthToken = AuthToken;
                Client.AutoReconnect = AutoReconnect;
                Client.ReconnectIntervalSec = ReconnectIntervalSec;
                Client.MaxReconnectAttempts = MaxReconnectAttempts;
            }

            api.Log(API.LogType.Debug, "HermesRainmeter: Reloaded config");
        }

        /// <summary>
        /// Return numeric value for the measure (Update cycle).
        /// 1.0 = connected, 0.0 = disconnected.
        /// Also serves as keepalive check point.
        /// </summary>
        public double Update()
        {
            if (Client == null) return 0.0;

            lock (_stateLock)
            {
                _isConnected = Client.IsConnected;
            }

            return _isConnected ? 1.0 : 0.0;
        }

        /// <summary>
        /// Return string value for the measure.
        /// Returns the last received message content.
        /// </summary>
        public string GetString()
        {
            lock (_stateLock)
            {
                return _lastMessageContent ?? "";
            }
        }

        /// <summary>
        /// Handle !CommandMeasure bangs.
        /// </summary>
        public void ExecuteBang(string args)
        {
            if (Client == null) return;

            // Parse command: "SendMessage Hello world" or "Connect" etc.
            args = args.Trim();

            if (args.StartsWith("SendMessage ", StringComparison.OrdinalIgnoreCase))
            {
                string text = args.Substring("SendMessage ".Length);
                Client.SendMessage(text);
            }
            else if (args.StartsWith("SendCommand ", StringComparison.OrdinalIgnoreCase))
            {
                string cmd = args.Substring("SendCommand ".Length);
                Client.SendCommand(cmd);
            }
            else if (args.Equals("Connect", StringComparison.OrdinalIgnoreCase))
            {
                Client.ConnectAsync();
            }
            else if (args.Equals("Disconnect", StringComparison.OrdinalIgnoreCase))
            {
                Client.DisconnectAsync();
            }
            else if (args.Equals("Ping", StringComparison.OrdinalIgnoreCase))
            {
                Client.SendPing();
            }
            else if (args.StartsWith("SendRaw ", StringComparison.OrdinalIgnoreCase))
            {
                string raw = args.Substring("SendRaw ".Length);
                Client.SendRaw(raw);
            }
            else
            {
                // Default: treat as a chat message
                Client.SendMessage(args);
            }
        }

        /// <summary>
        /// Clean up the measure. Called from exported Finalize function.
        /// </summary>
        public void Finalize()
        {
            Disposed = true;
            if (Client != null)
            {
                Client.DisconnectAsync().Wait();
                Client.Dispose();
                Client = null;
            }
        }

        /// <summary>
        /// Execute a Rainmeter bang with $message$ substitution.
        /// Thread-safe — can be called from WS event handlers.
        /// </summary>
        private void ExecuteBang(string bangTemplate, string message)
        {
            if (string.IsNullOrEmpty(bangTemplate) || Skin == IntPtr.Zero)
                return;

            try
            {
                // Replace $message$ placeholder with the actual message
                string bang = Regex.Replace(
                    bangTemplate,
                    @"\$message\$",
                    message?.Replace("\"", "\"\"") ?? "",
                    RegexOptions.IgnoreCase
                );

                // Execute on the Rainmeter thread via native API
                Rainmeter.NativeMethods.RmExecute(Skin, bang);
            }
            catch { }
        }
    }
}
