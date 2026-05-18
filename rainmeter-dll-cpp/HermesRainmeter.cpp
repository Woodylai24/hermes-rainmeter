//
// HermesRainmeter — Rainmeter C++ Plugin
//
// Connects to the Hermes agent WebSocket server and enables
// desktop AI chat widgets via Rainmeter skins.
//
// Build: C++ DLL targeting x64, link with winhttp.lib
// No external dependencies.
//

#include "RainmeterAPI.h"

#include <winhttp.h>
#include <string>
#include <thread>
#include <mutex>
#include <atomic>
#include <regex>
#include <sstream>

#pragma comment(lib, "winhttp.lib")

// WebSocket close status codes (RFC 6455) — not defined in winhttp.h
static const USHORT WS_CLOSE_NORMAL = 1000;

// ---------------------------------------------------------------------------
// UTF-8 <-> Wide string helpers
// ---------------------------------------------------------------------------

static std::wstring Utf8ToWide(const std::string& utf8) {
	if (utf8.empty()) return L"";
	int len = MultiByteToWideChar(CP_UTF8, 0, utf8.c_str(), (int)utf8.size(), nullptr, 0);
	if (len == 0) return L"";
	std::wstring wide(len, L'\0');
	MultiByteToWideChar(CP_UTF8, 0, utf8.c_str(), (int)utf8.size(), &wide[0], len);
	return wide;
}

static std::string WideToUtf8(const std::wstring& wide) {
	if (wide.empty()) return "";
	int len = WideCharToMultiByte(CP_UTF8, 0, wide.c_str(), (int)wide.size(), nullptr, 0, nullptr, nullptr);
	if (len == 0) return "";
	std::string utf8(len, '\0');
	WideCharToMultiByte(CP_UTF8, 0, wide.c_str(), (int)wide.size(), &utf8[0], len, nullptr, nullptr);
	return utf8;
}

// ---------------------------------------------------------------------------
// Minimal JSON helpers (our protocol is simple — no full parser needed)
// ---------------------------------------------------------------------------

// Extract a string value from JSON by key. Handles simple cases only.
// e.g. JsonGetString(R"({"type":"welcome","message":"hi"})", "type") -> "welcome"
static std::string JsonGetString(const std::string& json, const std::string& key) {
	std::string search = "\"" + key + "\"";
	size_t pos = json.find(search);
	if (pos == std::string::npos) return "";

	// Skip past the key and the colon
	pos += search.size();
	pos = json.find(':', pos);
	if (pos == std::string::npos) return "";
	pos++; // skip ':'

	// Skip whitespace
	while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) pos++;

	if (pos >= json.size() || json[pos] != '"') return "";
	pos++; // skip opening quote

	std::string result;
	while (pos < json.size() && json[pos] != '"') {
		if (json[pos] == '\\' && pos + 1 < json.size()) {
			pos++;
			switch (json[pos]) {
			case '"':  result += '"'; break;
			case '\\': result += '\\'; break;
			case '/':  result += '/'; break;
			case 'n':  result += '\n'; break;
			case 'r':  result += '\r'; break;
			case 't':  result += '\t'; break;
			default:   result += json[pos]; break;
			}
		}
		else {
			result += json[pos];
		}
		pos++;
	}
	return result;
}

// Extract an integer value from JSON by key.
static int JsonGetInt(const std::string& json, const std::string& key, int defValue = 0) {
	std::string search = "\"" + key + "\"";
	size_t pos = json.find(search);
	if (pos == std::string::npos) return defValue;

	pos += search.size();
	pos = json.find(':', pos);
	if (pos == std::string::npos) return defValue;
	pos++;

	while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) pos++;
	if (pos >= json.size()) return defValue;

	std::string numStr;
	while (pos < json.size() && json[pos] >= '0' && json[pos] <= '9') {
		numStr += json[pos];
		pos++;
	}
	return numStr.empty() ? defValue : std::atoi(numStr.c_str());
}

// Build a simple JSON string for sending.
// Escapes double quotes and backslashes in string values.
static std::string JsonEscape(const std::string& s) {
	std::string result;
	for (char c : s) {
		switch (c) {
		case '"':  result += "\\\""; break;
		case '\\': result += "\\\\"; break;
		case '\n': result += "\\n"; break;
		case '\r': result += "\\r"; break;
		case '\t': result += "\\t"; break;
		default:   result += c; break;
		}
	}
	return result;
}

static std::string MakeJsonMessage(const std::string& type, const std::string& content) {
	return "{\"type\":\"" + type + "\",\"content\":\"" + JsonEscape(content) + "\",\"session_key\":\"rainmeter:desktop:default\"}";
}

static std::string MakeJsonCommand(const std::string& command) {
	return "{\"type\":\"command\",\"command\":\"" + JsonEscape(command) + "\"}";
}

static std::string MakeJsonAuth(const std::string& token) {
	return "{\"type\":\"auth\",\"token\":\"" + JsonEscape(token) + "\"}";
}

static const char* PING_JSON = "{\"type\":\"ping\"}";

// ---------------------------------------------------------------------------
// Parse WebSocket URL into host, port, path
// ---------------------------------------------------------------------------

struct WsUrl {
	std::wstring host;
	int port;
	std::wstring path;
	bool valid;
};

static WsUrl ParseWsUrl(const std::wstring& url) {
	WsUrl result = { L"", 0, L"/", false };

	// Expected format: ws://host:port/path
	std::wstring remaining = url;

	// Remove "ws://"
	const std::wstring wsPrefix = L"ws://";
	if (remaining.find(wsPrefix) != 0) return result;
	remaining = remaining.substr(wsPrefix.length());

	// Split at first '/' for path
	size_t slashPos = remaining.find(L'/');
	std::wstring authority = (slashPos != std::wstring::npos) ? remaining.substr(0, slashPos) : remaining;
	result.path = (slashPos != std::wstring::npos) ? remaining.substr(slashPos) : L"/";

	// Split host:port
	size_t colonPos = authority.rfind(L':');
	if (colonPos != std::wstring::npos) {
		result.host = authority.substr(0, colonPos);
		result.port = _wtoi(authority.substr(colonPos + 1).c_str());
	}
	else {
		result.host = authority;
		result.port = 80; // default ws port
	}

	result.valid = !result.host.empty() && result.port > 0;
	return result;
}

// ---------------------------------------------------------------------------
// URL decode for bang template substitution
// ---------------------------------------------------------------------------

static std::wstring UrlDecode(const std::wstring& s) {
	std::wstring result;
	for (size_t i = 0; i < s.size(); i++) {
		if (s[i] == L'+' ) {
			result += L' ';
		}
		else if (s[i] == L'%' && i + 2 < s.size()) {
			wchar_t hex[3] = { s[i+1], s[i+2], 0 };
			wchar_t* end;
			long val = wcstol(hex, &end, 16);
			if (*end == 0) {
				result += (wchar_t)val;
				i += 2;
			}
			else {
				result += s[i];
			}
		}
		else {
			result += s[i];
		}
	}
	return result;
}

// ---------------------------------------------------------------------------
// Measure structure — one per skin measure instance
// ---------------------------------------------------------------------------

struct Measure {
	// Configuration
	std::wstring serverUrl = L"ws://localhost:8643/ws";
	std::wstring authToken;
	bool autoReconnect = true;
	int reconnectIntervalSec = 5;

	// Callback bangs
	std::wstring onMessageBang;
	std::wstring onConnectedBang;
	std::wstring onDisconnectedBang;
	std::wstring onErrorBang;
	std::wstring onAuthOKBang;

	// Runtime
	void* rmHandle = nullptr;  // Rainmeter measure handle for RmExecute
	HWND skinHwnd = nullptr;

	// WebSocket state
	HINTERNET hSession = nullptr;
	HINTERNET hWebSocket = nullptr;
	std::thread* recvThread = nullptr;
	std::atomic<bool> running{ false };
	std::atomic<bool> connected{ false };
	std::atomic<bool> authenticated{ false };

	// Thread-safe received data
	std::mutex stateMutex;
	std::wstring lastMessage;
	std::wstring lastMessageType;
	std::wstring lastMessageContent;
	std::wstring lastError;
	int connectedClients = 0;

	// Reconnect tracking
	std::atomic<int> reconnectAttempts{ 0 };
};

// ---------------------------------------------------------------------------
// WebSocket send helper (call from any thread)
// ---------------------------------------------------------------------------

static bool WsSend(Measure* m, const std::string& data) {
	if (!m->hWebSocket || !m->connected) return false;

	DWORD bytesSent = 0;
	HRESULT hr = WinHttpWebSocketSend(
		m->hWebSocket,
		WINHTTP_WEB_SOCKET_UTF8_MESSAGE_BUFFER_TYPE,
		(PVOID)data.c_str(),
		(DWORD)data.size()
	);
	return SUCCEEDED(hr);
}

// ---------------------------------------------------------------------------
// Execute a Rainmeter bang with $message$ substitution
// ---------------------------------------------------------------------------

static void ExecuteCallbackBang(Measure* m, const std::wstring& bangTemplate, const std::wstring& message) {
	if (bangTemplate.empty() || !m->skinHwnd) return;

	// Replace $message$ placeholder (case-insensitive)
	std::wstring bang = bangTemplate;
	const std::wstring placeholder = L"$message$";
	size_t pos = 0;
	while ((pos = bang.find(placeholder)) != std::wstring::npos) {
		// Escape double quotes in the message for Rainmeter bang syntax
		std::wstring escaped = message;
		for (size_t i = 0; i < escaped.size(); i++) {
			if (escaped[i] == L'"') {
				escaped.insert(i, 1, L'"');
				i++;
			}
		}
		bang.replace(pos, placeholder.size(), escaped);
	}

	RmExecute(m->rmHandle, bang.c_str());
}

// ---------------------------------------------------------------------------
// Process a received JSON message
// ---------------------------------------------------------------------------

static void ProcessMessage(Measure* m, const std::string& raw) {
	std::string type = JsonGetString(raw, "type");

	{
		std::lock_guard<std::mutex> lock(m->stateMutex);
		m->lastMessage = Utf8ToWide(raw);
		m->lastMessageType = Utf8ToWide(type);
	}

	if (type == "welcome") {
		// Send auth if token is configured
		std::string token = WideToUtf8(m->authToken);
		if (!token.empty()) {
			WsSend(m, MakeJsonAuth(token));
		}
	}
	else if (type == "auth_ok") {
		m->authenticated = true;
		ExecuteCallbackBang(m, m->onAuthOKBang, L"authenticated");
	}
	else if (type == "message") {
		std::string content = JsonGetString(raw, "content");
		{
			std::lock_guard<std::mutex> lock(m->stateMutex);
			m->lastMessageContent = Utf8ToWide(content);
		}
	}
	else if (type == "image") {
		std::string url = JsonGetString(raw, "url");
		{
			std::lock_guard<std::mutex> lock(m->stateMutex);
			m->lastMessageContent = Utf8ToWide(url);
		}
	}
	else if (type == "status") {
		int clients = JsonGetInt(raw, "connected_clients", 0);
		{
			std::lock_guard<std::mutex> lock(m->stateMutex);
			m->connectedClients = clients;
		}
	}
	else if (type == "error") {
		std::string errorMsg = JsonGetString(raw, "message");
		{
			std::lock_guard<std::mutex> lock(m->stateMutex);
			m->lastError = Utf8ToWide(errorMsg);
		}
		ExecuteCallbackBang(m, m->onErrorBang, Utf8ToWide(errorMsg));
	}
	// "typing" and "pong" — no action needed

	// Always fire OnMessage for full flexibility
	ExecuteCallbackBang(m, m->onMessageBang, Utf8ToWide(raw));
}

// ---------------------------------------------------------------------------
// WebSocket receive loop (runs on background thread)
// ---------------------------------------------------------------------------

static void ReceiveLoop(Measure* m) {
	char buffer[8192];

	while (m->running && m->connected) {
		DWORD bytesRead = 0;
		WINHTTP_WEB_SOCKET_BUFFER_TYPE bufType = WINHTTP_WEB_SOCKET_BINARY_MESSAGE_BUFFER_TYPE;

		HRESULT hr = WinHttpWebSocketReceive(
			m->hWebSocket,
			buffer,
			sizeof(buffer) - 1,
			&bytesRead,
			&bufType
		);

		if (!m->running) break;

		if (FAILED(hr)) {
			// Connection lost
			m->connected = false;
			m->authenticated = false;
			ExecuteCallbackBang(m, m->onDisconnectedBang, L"Connection lost");
			break;
		}

		if (bufType == WINHTTP_WEB_SOCKET_CLOSE_BUFFER_TYPE) {
			// Server initiated close
			m->connected = false;
			m->authenticated = false;

			// Query close status
			USHORT status = 0;
			DWORD statusLen = sizeof(status);
			WinHttpWebSocketQueryCloseStatus(m->hWebSocket, &status, buffer, sizeof(buffer), &statusLen);

			wchar_t reason[64];
			swprintf_s(reason, L"Server closed (status %d)", status);
			ExecuteCallbackBang(m, m->onDisconnectedBang, reason);
			break;
		}

		// We got data — null-terminate and process
		if (bytesRead > 0) {
			buffer[bytesRead] = '\0';
			std::string raw(buffer, bytesRead);
			ProcessMessage(m, raw);
		}
	}
}

// ---------------------------------------------------------------------------
// Connect to WebSocket server
// ---------------------------------------------------------------------------

static bool ConnectWebSocket(Measure* m) {
	WsUrl url = ParseWsUrl(m->serverUrl);
	if (!url.valid) return false;

	// Close previous handles
	if (m->hWebSocket) {
		WinHttpWebSocketClose(m->hWebSocket, WS_CLOSE_NORMAL, nullptr, 0);
		WinHttpWebSocketShutdown(m->hWebSocket, WS_CLOSE_NORMAL, nullptr, 0);
		m->hWebSocket = nullptr;
	}

	// 1. Open session
	m->hSession = WinHttpOpen(
		L"HermesRainmeter/1.0",
		WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
		WINHTTP_NO_PROXY_NAME,
		WINHTTP_NO_PROXY_BYPASS,
		0
	);
	if (!m->hSession) return false;

	// 2. Connect to host
	HINTERNET hConnect = WinHttpConnect(m->hSession, url.host.c_str(), (INTERNET_PORT)url.port, 0);
	if (!hConnect) {
		WinHttpCloseHandle(m->hSession);
		m->hSession = nullptr;
		return false;
	}

	// 3. Open HTTP request with WebSocket upgrade
	HINTERNET hRequest = WinHttpOpenRequest(
		hConnect,
		L"GET",
		url.path.c_str(),
		NULL,
		WINHTTP_NO_REFERER,
		WINHTTP_DEFAULT_ACCEPT_TYPES,
		0
	);
	if (!hRequest) {
		WinHttpCloseHandle(hConnect);
		WinHttpCloseHandle(m->hSession);
		m->hSession = nullptr;
		return false;
	}

	// 4. Set WebSocket upgrade option
	BOOL optVal = TRUE;
	WinHttpSetOption(hRequest, WINHTTP_OPTION_UPGRADE_TO_WEB_SOCKET, &optVal, sizeof(optVal));

	// 5. Send request
	BOOL sent = WinHttpSendRequest(
		hRequest,
		WINHTTP_NO_ADDITIONAL_HEADERS, 0,
		WINHTTP_NO_REQUEST_DATA, 0,
		0, 0
	);
	if (!sent) {
		WinHttpCloseHandle(hRequest);
		WinHttpCloseHandle(hConnect);
		WinHttpCloseHandle(m->hSession);
		m->hSession = nullptr;
		return false;
	}

	// 6. Receive response
	BOOL received = WinHttpReceiveResponse(hRequest, nullptr);
	if (!received) {
		WinHttpCloseHandle(hRequest);
		WinHttpCloseHandle(hConnect);
		WinHttpCloseHandle(m->hSession);
		m->hSession = nullptr;
		return false;
	}

	// 7. Complete WebSocket upgrade
	m->hWebSocket = WinHttpWebSocketCompleteUpgrade(hRequest, 0);

	// The request handle is no longer needed after upgrade
	WinHttpCloseHandle(hRequest);
	WinHttpCloseHandle(hConnect);

	if (!m->hWebSocket) {
		WinHttpCloseHandle(m->hSession);
		m->hSession = nullptr;
		return false;
	}

	m->connected = true;
	m->reconnectAttempts = 0;
	return true;
}

// ---------------------------------------------------------------------------
// Background thread: connect + receive loop + reconnect
// ---------------------------------------------------------------------------

static void BackgroundThread(Measure* m) {
	while (m->running) {
		// Try to connect
		bool ok = ConnectWebSocket(m);

		if (ok) {
			ExecuteCallbackBang(m, m->onConnectedBang, L"connected");

			// Enter receive loop
			ReceiveLoop(m);

			// Clean up WebSocket handles
			if (m->hWebSocket) {
				WinHttpWebSocketClose(m->hWebSocket, WS_CLOSE_NORMAL, nullptr, 0);
				WinHttpCloseHandle(m->hWebSocket);
				m->hWebSocket = nullptr;
			}
			if (m->hSession) {
				WinHttpCloseHandle(m->hSession);
				m->hSession = nullptr;
			}
		}
		else {
			wchar_t errMsg[256];
			swprintf_s(errMsg, L"Connect failed to %ls (attempt %d)",
				m->serverUrl.c_str(), m->reconnectAttempts.load() + 1);
			ExecuteCallbackBang(m, m->onErrorBang, errMsg);
			ExecuteCallbackBang(m, m->onDisconnectedBang, L"Connect failed");
		}

		if (!m->running) break;
		if (!m->autoReconnect) break;

		// Wait before reconnect
		m->reconnectAttempts++;
		int intervalMs = m->reconnectIntervalSec * 1000;
		for (int i = 0; i < intervalMs && m->running; i += 100) {
			Sleep(100);
		}
	}
}

// ---------------------------------------------------------------------------
// Start the background connection thread
// ---------------------------------------------------------------------------

static void StartConnection(Measure* m) {
	if (m->recvThread && m->recvThread->joinable()) return; // already running

	m->running = true;
	m->recvThread = new std::thread(BackgroundThread, m);
}

// ---------------------------------------------------------------------------
// Stop the background connection thread
// ---------------------------------------------------------------------------

static void StopConnection(Measure* m) {
	m->running = false;
	m->autoReconnect = false;

	// Close WebSocket to unblock receive loop
	if (m->hWebSocket) {
		WinHttpWebSocketShutdown(m->hWebSocket, WS_CLOSE_NORMAL, nullptr, 0);
	}

	if (m->recvThread && m->recvThread->joinable()) {
		m->recvThread->join();
	}
	delete m->recvThread;
	m->recvThread = nullptr;

	// Clean up handles
	if (m->hWebSocket) {
		WinHttpCloseHandle(m->hWebSocket);
		m->hWebSocket = nullptr;
	}
	if (m->hSession) {
		WinHttpCloseHandle(m->hSession);
		m->hSession = nullptr;
	}

	m->connected = false;
	m->authenticated = false;
}

// ---------------------------------------------------------------------------
// Read skin configuration into the Measure
// ---------------------------------------------------------------------------

static void ReadConfig(Measure* m, void* rm) {
	m->serverUrl = RmReadString(rm, L"Server", L"ws://localhost:8643/ws", FALSE);
	m->authToken = RmReadString(rm, L"AuthToken", L"", FALSE);
	m->autoReconnect = RmReadInt(rm, L"AutoReconnect", 1) != 0;
	m->reconnectIntervalSec = RmReadInt(rm, L"ReconnectInterval", 5);

	m->onMessageBang     = RmReadString(rm, L"OnMessage", L"", FALSE);
	m->onConnectedBang   = RmReadString(rm, L"OnConnected", L"", FALSE);
	m->onDisconnectedBang = RmReadString(rm, L"OnDisconnected", L"", FALSE);
	m->onErrorBang       = RmReadString(rm, L"OnError", L"", FALSE);
	m->onAuthOKBang      = RmReadString(rm, L"OnAuthOK", L"", FALSE);

	m->rmHandle = rm;
	m->skinHwnd = RmGetSkin(rm);
}

// ===========================================================================
// Rainmeter Plugin Exports
// ===========================================================================

PLUGIN_EXPORT void Initialize(void** data, void* rm) {
	// Resolve API function pointers (once)
	static bool apiInitialized = false;
	if (!apiInitialized) {
		RmInitializeAPI();
		apiInitialized = true;
	}

	Measure* m = new Measure();
	*data = m;

	ReadConfig(m, rm);

	RmLog(rm, LOG_NOTICE, L"HermesRainmeter: Initializing");

	StartConnection(m);

	RmLog(rm, LOG_NOTICE, L"HermesRainmeter: Started");
}

PLUGIN_EXPORT void Finalize(void* data) {
	Measure* m = (Measure*)data;
	StopConnection(m);
	delete m;
}

PLUGIN_EXPORT void Reload(void* data, void* rm, double* maxValue) {
	Measure* m = (Measure*)data;
	ReadConfig(m, rm);
	RmLog(rm, LOG_DEBUG, L"HermesRainmeter: Reloaded config");
}

PLUGIN_EXPORT double Update(void* data) {
	Measure* m = (Measure*)data;
	return m->connected ? 1.0 : 0.0;
}

// Return buffer for GetString — must persist until next call
static std::wstring g_stringBuffer;

PLUGIN_EXPORT LPCWSTR GetString(void* data) {
	Measure* m = (Measure*)data;
	std::lock_guard<std::mutex> lock(m->stateMutex);
	g_stringBuffer = m->lastMessageContent;
	return g_stringBuffer.c_str();
}

PLUGIN_EXPORT void ExecuteBang(void* data, LPCWSTR args) {
	Measure* m = (Measure*)data;
	std::wstring command(args);

	// Trim whitespace
	while (!command.empty() && (command[0] == L' ' || command[0] == L'\t'))
		command.erase(0, 1);
	while (!command.empty() && (command.back() == L' ' || command.back() == L'\t'))
		command.pop_back();

	if (command.compare(0, 12, L"SendMessage ") == 0) {
		std::wstring text = command.substr(12);
		WsSend(m, MakeJsonMessage("message", WideToUtf8(text)));
	}
	else if (command.compare(0, 12, L"SendCommand ") == 0) {
		std::wstring cmd = command.substr(12);
		WsSend(m, MakeJsonCommand(WideToUtf8(cmd)));
	}
	else if (command.compare(0, 8, L"SendRaw ") == 0) {
		std::wstring raw = command.substr(8);
		WsSend(m, WideToUtf8(raw));
	}
	else if (command == L"Connect") {
		m->autoReconnect = true;
		StartConnection(m);
	}
	else if (command == L"Disconnect") {
		StopConnection(m);
	}
	else if (command == L"Ping") {
		WsSend(m, PING_JSON);
	}
	else if (!command.empty()) {
		// Default: treat as a chat message
		WsSend(m, MakeJsonMessage("message", WideToUtf8(command)));
	}
}
