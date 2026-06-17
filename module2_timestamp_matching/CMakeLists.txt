cmake_minimum_required(VERSION 3.14)
project(event_rgb_sync_module2 CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 最適化フラグ（Release ビルド時に有効）
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

set(CMAKE_CXX_FLAGS_RELEASE "-O2 -DNDEBUG")
set(CMAKE_CXX_FLAGS_DEBUG   "-g -O0")

# nlohmann/json はヘッダオンリー → インクルードパスを追加
include_directories(${CMAKE_SOURCE_DIR}/third_party)

add_executable(sync_timestamps main.cpp)

# C++17 ファイルシステムライブラリのリンク（GCC < 9 では -lstdc++fs が必要）
if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU" AND CMAKE_CXX_COMPILER_VERSION VERSION_LESS 9)
  target_link_libraries(sync_timestamps stdc++fs)
endif()

message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")
message(STATUS "Compiler: ${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}")
