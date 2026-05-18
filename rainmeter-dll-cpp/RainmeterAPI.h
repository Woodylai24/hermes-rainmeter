#ifndef RAINDROP_RAINDMETER_API_H
#define RAINDROP_RAINDMETER_API_H

//
// Rainmeter Plugin API header
// Based on the official Rainmeter SDK (rainmeter.net/SDK/)
// Provides function declarations for C++ plugin development.
//

#include <Windows.h>

// Log levels
enum LOG_LEVEL
{
	LOG_ERROR   = 1,
	LOG_WARNING = 2,
	LOG_NOTICE  = 3,
	LOG_DEBUG   = 4
};

// Export/Import macro
#ifdef _MSC_VER
#define PLUGIN_EXPORT extern "C" __declspec(dllexport)
#else
#define PLUGIN_EXPORT extern "C" __attribute__((visibility("default")))
#endif

//
// Function pointer types — resolved dynamically from Rainmeter.exe
//
typedef void     (*FN_RmLog)(void* rm, int level, LPCWSTR ms);
typedef LPCWSTR  (*FN_RmReadString)(void* rm, LPCWSTR option, LPCWSTR defValue, BOOL replaceMeasures);
typedef int      (*FN_RmReadInt)(void* rm, LPCWSTR option, int defValue);
typedef double   (*FN_RmReadDouble)(void* rm, LPCWSTR option, double defValue);
typedef LPCWSTR  (*FN_RmReadPath)(void* rm, LPCWSTR option, LPCWSTR defValue);
typedef HWND     (*FN_RmGetSkin)(void* rm);
typedef void     (*FN_RmExecute)(void* rm, LPCWSTR bang);

//
// Global function pointers — set once during Initialize
//
static FN_RmLog          _RmLog = nullptr;
static FN_RmReadString   _RmReadString = nullptr;
static FN_RmReadInt      _RmReadInt = nullptr;
static FN_RmReadDouble   _RmReadDouble = nullptr;
static FN_RmReadPath     _RmReadPath = nullptr;
static FN_RmGetSkin      _RmGetSkin = nullptr;
static FN_RmExecute      _RmExecute = nullptr;

//
// Inline helper functions
//
inline void RmLog(void* rm, int level, LPCWSTR message) {
	if (_RmLog) _RmLog(rm, level, message);
}

inline LPCWSTR RmReadString(void* rm, LPCWSTR option, LPCWSTR defValue, BOOL replaceMeasures = FALSE) {
	return _RmReadString ? _RmReadString(rm, option, defValue, replaceMeasures) : defValue;
}

inline int RmReadInt(void* rm, LPCWSTR option, int defValue) {
	return _RmReadInt ? _RmReadInt(rm, option, defValue) : defValue;
}

inline double RmReadDouble(void* rm, LPCWSTR option, double defValue) {
	return _RmReadDouble ? _RmReadDouble(rm, option, defValue) : defValue;
}

inline LPCWSTR RmReadPath(void* rm, LPCWSTR option, LPCWSTR defValue) {
	return _RmReadPath ? _RmReadPath(rm, option, defValue) : defValue;
}

inline HWND RmGetSkin(void* rm) {
	return _RmGetSkin ? _RmGetSkin(rm) : nullptr;
}

inline void RmExecute(void* rm, LPCWSTR bang) {
	if (_RmExecute) _RmExecute(rm, bang);
}

//
// Resolve API function pointers from Rainmeter.exe
// Call this once in Initialize()
//
inline void RmInitializeAPI() {
	HMODULE hRainmeter = GetModuleHandle(L"Rainmeter.exe");
	if (!hRainmeter) return;

	_RmLog         = (FN_RmLog)GetProcAddress(hRainmeter, "RmLog");
	_RmReadString  = (FN_RmReadString)GetProcAddress(hRainmeter, "RmReadString");
	_RmReadInt     = (FN_RmReadInt)GetProcAddress(hRainmeter, "RmReadInt");
	_RmReadDouble  = (FN_RmReadDouble)GetProcAddress(hRainmeter, "RmReadDouble");
	_RmReadPath    = (FN_RmReadPath)GetProcAddress(hRainmeter, "RmReadPath");
	_RmGetSkin     = (FN_RmGetSkin)GetProcAddress(hRainmeter, "RmGetSkin");
	_RmExecute     = (FN_RmExecute)GetProcAddress(hRainmeter, "RmExecute");
}

#endif // RAINDROP_RAINDMETER_API_H
