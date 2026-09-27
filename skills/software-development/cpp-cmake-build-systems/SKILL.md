---
name: cpp-cmake-build-systems
description: CMake and C++ build systems (Make, Ninja, vcpkg).
tags: [cpp, cmake, build-systems, make, ninja]
version: 1.0.0
---

# C++ Build Systems - CMake & Make

Professional C++ build configuration with CMake, Make, and package managers.

## When to Use

Load when:
- Setting up C++ project build system
- Writing CMakeLists.txt
- Configuring multi-platform builds
- Managing C++ dependencies

## CMake Basics

### Minimal CMakeLists.txt
```cmake
cmake_minimum_required(VERSION 3.15)
project(MyProject VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_executable(myapp src/main.cpp src/utils.cpp)
```

### Build Commands
```bash
mkdir build && cd build
cmake ..
cmake --build .

# Or with generator
cmake -G Ninja ..
ninja

# Release build
cmake -DCMAKE_BUILD_TYPE=Release ..
cmake --build .
```

## CMake Project Structure

```
project/
├── CMakeLists.txt
├── include/
│   └── mylib/
│       └── mylib.h
├── src/
│   ├── main.cpp
│   └── mylib.cpp
├── tests/
│   └── test_mylib.cpp
└── build/        # Generated
```

### Library + Executable
```cmake
cmake_minimum_required(VERSION 3.15)
project(MyProject CXX)

set(CMAKE_CXX_STANDARD 20)

# Library
add_library(mylib
    src/mylib.cpp
    include/mylib/mylib.h
)

target_include_directories(mylib PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

# Executable
add_executable(myapp src/main.cpp)
target_link_libraries(myapp PRIVATE mylib)

# Tests
enable_testing()
add_executable(tests tests/test_mylib.cpp)
target_link_libraries(tests PRIVATE mylib)
add_test(NAME MyTests COMMAND tests)
```

## Compiler Flags

```cmake
# Set C++ standard
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Warning flags
if(MSVC)
    add_compile_options(/W4 /WX)
else()
    add_compile_options(-Wall -Wextra -Wpedantic -Werror)
endif()

# Debug/Release flags
set(CMAKE_CXX_FLAGS_DEBUG "-g -O0")
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG")

# Sanitizers (Debug)
if(CMAKE_BUILD_TYPE STREQUAL "Debug")
    add_compile_options(-fsanitize=address -fsanitize=undefined)
    add_link_options(-fsanitize=address -fsanitize=undefined)
endif()
```

## External Dependencies

### Find Package
```cmake
# Find system library
find_package(Boost 1.70 REQUIRED COMPONENTS system filesystem)

target_link_libraries(myapp PRIVATE
    Boost::system
    Boost::filesystem
)
```

### FetchContent (Download deps)
```cmake
include(FetchContent)

FetchContent_Declare(
    googletest
    GIT_REPOSITORY https://github.com/google/googletest.git
    GIT_TAG release-1.12.1
)

FetchContent_MakeAvailable(googletest)

target_link_libraries(tests PRIVATE gtest_main)
```

### vcpkg (Package Manager)
```bash
# Install vcpkg
git clone https://github.com/microsoft/vcpkg.git
./vcpkg/bootstrap-vcpkg.sh

# Install packages
./vcpkg/vcpkg install fmt spdlog nlohmann-json

# Use with CMake
cmake -DCMAKE_TOOLCHAIN_FILE=./vcpkg/scripts/buildsystems/vcpkg.cmake ..
```

```cmake
# In CMakeLists.txt
find_package(fmt CONFIG REQUIRED)
find_package(spdlog CONFIG REQUIRED)
find_package(nlohmann_json CONFIG REQUIRED)

target_link_libraries(myapp PRIVATE
    fmt::fmt
    spdlog::spdlog
    nlohmann_json::nlohmann_json
)
```

## Makefile Basics

### Simple Makefile
```makefile
CXX = g++
CXXFLAGS = -std=c++20 -Wall -Wextra -O2
TARGET = myapp
SRCS = main.cpp utils.cpp
OBJS = $(SRCS:.cpp=.o)

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^

%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

clean:
	rm -f $(TARGET) $(OBJS)

run: $(TARGET)
	./$(TARGET)

.PHONY: all clean run
```

## Cross-Platform CMake

```cmake
# Platform-specific code
if(WIN32)
    target_sources(myapp PRIVATE src/windows.cpp)
elseif(UNIX AND NOT APPLE)
    target_sources(myapp PRIVATE src/linux.cpp)
elseif(APPLE)
    target_sources(myapp PRIVATE src/macos.cpp)
endif()

# Platform-specific libraries
if(WIN32)
    target_link_libraries(myapp PRIVATE ws2_32)
else()
    target_link_libraries(myapp PRIVATE pthread)
endif()
```

## Installation

```cmake
# Install targets
install(TARGETS myapp mylib
    RUNTIME DESTINATION bin
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib
)

# Install headers
install(DIRECTORY include/mylib
    DESTINATION include
)

# Install with
cmake --install build --prefix /usr/local
```

## CMake Variables

```cmake
# Project info
${PROJECT_NAME}
${PROJECT_VERSION}
${CMAKE_PROJECT_NAME}

# Paths
${CMAKE_SOURCE_DIR}       # Top-level source
${CMAKE_BINARY_DIR}       # Build directory
${CMAKE_CURRENT_SOURCE_DIR}
${CMAKE_CURRENT_BINARY_DIR}

# Compiler
${CMAKE_CXX_COMPILER}
${CMAKE_CXX_COMPILER_ID}  # GNU, Clang, MSVC

# Build type
${CMAKE_BUILD_TYPE}       # Debug, Release, etc

# System
${CMAKE_SYSTEM_NAME}      # Linux, Windows, Darwin
${CMAKE_SYSTEM_PROCESSOR} # x86_64, arm64
```

## Useful CMake Commands

```cmake
# Print message
message(STATUS "Building for ${CMAKE_SYSTEM_NAME}")
message(FATAL_ERROR "Error occurred")

# Check compiler features
target_compile_features(myapp PRIVATE cxx_std_20)

# Generate config header
configure_file(config.h.in config.h @ONLY)

# Add preprocessor define
target_compile_definitions(myapp PRIVATE
    VERSION="${PROJECT_VERSION}"
    $<$<CONFIG:Debug>:DEBUG_MODE>
)

# Platform-specific define
if(WIN32)
    target_compile_definitions(myapp PRIVATE PLATFORM_WINDOWS)
endif()
```

## Common Build Patterns

### Header-Only Library
```cmake
add_library(myheaderlib INTERFACE)
target_include_directories(myheaderlib INTERFACE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)
```

### Static vs Shared Library
```cmake
# Static
add_library(mylib STATIC src/lib.cpp)

# Shared
add_library(mylib SHARED src/lib.cpp)

# Let user choose
option(BUILD_SHARED_LIBS "Build shared libraries" OFF)
add_library(mylib src/lib.cpp)  # Respects BUILD_SHARED_LIBS
```

### Precompiled Headers
```cmake
target_precompile_headers(myapp PRIVATE
    <iostream>
    <vector>
    <string>
)
```

## Ninja Build System

```bash
# Generate Ninja files
cmake -G Ninja ..

# Build
ninja

# Build specific target
ninja myapp

# Clean
ninja clean

# Verbose
ninja -v
```

## Build System Comparison

| Tool | Speed | Features | Complexity |
|------|-------|----------|-----------|
| Make | Medium | Basic | Low |
| CMake | Medium | Cross-platform, rich | Medium |
| Ninja | Fast | Minimal, fast | Low |
| Bazel | Fast | Google-scale | High |

## Best Practices

1. **Out-of-source builds** - Never build in source tree
2. **Modern CMake** - Use target-based commands
3. **Version control** - `.gitignore` build directories
4. **Cache variables** - Use `cmake -L` to list options
5. **Incremental builds** - Don't clean unless necessary
