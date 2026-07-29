cmake_minimum_required(VERSION 3.16)
project(weight_stream_core VERSION 1.0.0 LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# ── Platform detection ──────────────────────────────────────────
if(WIN32)
    set(WS_PLATFORM "windows")
elseif(APPLE)
    set(WS_PLATFORM "macos")
else()
    set(WS_PLATFORM "linux")
endif()

message(STATUS "Building weight-stream-core for: ${WS_PLATFORM}")

# ── Compiler flags ──────────────────────────────────────────────
if(MSVC)
    add_compile_options(/O2 /W3 /arch:AVX2)
    add_compile_definitions(WEIGHT_STREAM_EXPORTS)
else()
    add_compile_options(-O2 -Wall -Wextra -fvisibility=hidden)

    # Auto-detect SIMD support
    include(CheckCXXCompilerFlag)
    check_cxx_compiler_flag("-mavx512f" HAS_AVX512)
    check_cxx_compiler_flag("-mavx2" HAS_AVX2)
    check_cxx_compiler_flag("-mfpu=neon" HAS_NEON)

    if(HAS_AVX512)
        message(STATUS "AVX-512 support detected — enabling")
        add_compile_options(-mavx512f -mavx512bw)
        add_compile_definitions(WS_HAS_AVX512=1)
    elseif(HAS_AVX2)
        message(STATUS "AVX2 support detected — enabling")
        add_compile_options(-mavx2 -mfma)
        add_compile_definitions(WS_HAS_AVX2=1)
    endif()

    if(HAS_NEON)
        message(STATUS "ARM NEON support detected — enabling")
        add_compile_definitions(WS_HAS_NEON=1)
    endif()
endif()

# ── Core shared library ────────────────────────────────────────
set(CORE_SOURCES
    weight_stream_core.cpp
    simd_kernels.cpp
)

# Platform-specific async I/O backends
if(WS_PLATFORM STREQUAL "windows")
    list(APPEND CORE_SOURCES win_iocp_stream.cpp)
elseif(WS_PLATFORM STREQUAL "linux")
    list(APPEND CORE_SOURCES linux_iouring_stream.c)
    # Check for liburing
    find_library(IOURING_LIB uring)
    if(IOURING_LIB)
        message(STATUS "liburing found: ${IOURING_LIB}")
    else()
        message(STATUS "liburing not found — io_uring disabled, using pread fallback")
    endif()
endif()

add_library(weight_stream_core SHARED ${CORE_SOURCES})
target_include_directories(weight_stream_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

if(WS_PLATFORM STREQUAL "linux" AND IOURING_LIB)
    target_link_libraries(weight_stream_core PRIVATE ${IOURING_LIB})
endif()

# ── Install targets ────────────────────────────────────────────
install(TARGETS weight_stream_core
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION bin
    ARCHIVE DESTINATION lib
)
install(FILES weight_stream_core.h DESTINATION include)

# ── Summary ─────────────────────────────────────────────────────
message(STATUS "")
message(STATUS "╔═══════════════════════════════════════════════╗")
message(STATUS "║  weight-stream-core build configuration      ║")
message(STATUS "╠═══════════════════════════════════════════════╣")
message(STATUS "║  Platform:   ${WS_PLATFORM}")
message(STATUS "║  AVX-512:    ${HAS_AVX512}")
message(STATUS "║  AVX2:       ${HAS_AVX2}")
message(STATUS "║  ARM NEON:   ${HAS_NEON}")
if(WS_PLATFORM STREQUAL "linux")
    message(STATUS "║  io_uring:   ${IOURING_LIB}")
endif()
message(STATUS "╚═══════════════════════════════════════════════╝")
