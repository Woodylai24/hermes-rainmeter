cmake_minimum_required(VERSION 3.15)
project(HermesRainmeter LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Build as a shared library (DLL)
add_library(HermesRainmeter SHARED HermesRainmeter.cpp)

# Link WinHTTP for WebSocket support
target_link_libraries(HermesRainmeter PRIVATE winhttp)

# Export all symbols (for Rainmeter plugin entry points)
# On MSVC, we use __declspec(dllexport) in the code instead
if(MSVC)
    # Statically link the C/C++ runtime — no dependency on vcruntime DLLs
    # This is standard practice for Rainmeter plugins
    target_compile_options(HermesRainmeter PRIVATE /W4 /Zi /MT)
    target_link_options(HermesRainmeter PRIVATE /DEBUG)

    # Ensure /MT is used for all configs (CMake defaults to /MD)
    set_property(TARGET HermesRainmeter PROPERTY
        MSVC_RUNTIME_LIBRARY "MultiThreaded")
endif()

# Output to bin/ directory
set_target_properties(HermesRainmeter PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
    ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib"
)
