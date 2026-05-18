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
    # Reduce DLL size, enable PDB for debugging
    target_compile_options(HermesRainmeter PRIVATE /W4 /Zi)
    target_link_options(HermesRainmeter PRIVATE /DEBUG)
endif()

# Output to bin/ directory
set_target_properties(HermesRainmeter PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
    ARCHIVE_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib"
)
