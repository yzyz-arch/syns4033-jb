---
name: cpp-debugging-profiling
description: Debug and profile C++ programs efficiently.
tags: [cpp, debugging, profiling, gdb, valgrind]
version: 1.0.0
---

# C++ Debugging and Profiling

Professional debugging and performance profiling techniques.

## When to Use

Load when:
- Debugging segfaults, memory leaks, or logic errors
- Profiling performance bottlenecks
- Need GDB, Valgrind, or sanitizer usage
- Analyzing runtime behavior

## Compilation Flags

### Debug Build
```bash
g++ -g -O0 -Wall -Wextra -std=c++20 main.cpp -o debug_app
clang++ -g -O0 -Wall -Wextra -std=c++20 main.cpp -o debug_app
```

- `-g` = Debug symbols
- `-O0` = No optimization (easier debugging)
- `-Wall -Wextra` = Enable warnings

### Sanitizers

#### AddressSanitizer (Memory errors)
```bash
g++ -fsanitize=address -g -O1 main.cpp -o app
./app
```

Detects:
- Buffer overflows
- Use-after-free
- Memory leaks
- Stack/heap overflow

#### UndefinedBehaviorSanitizer
```bash
g++ -fsanitize=undefined -g main.cpp -o app
```

Detects:
- Integer overflow
- Null pointer dereference
- Division by zero
- Invalid casts

#### ThreadSanitizer (Data races)
```bash
g++ -fsanitize=thread -g -O2 main.cpp -o app
```

## GDB (GNU Debugger)

### Basic Commands
```bash
gdb ./app

# Run program
(gdb) run
(gdb) run arg1 arg2

# Breakpoints
(gdb) break main
(gdb) break file.cpp:42
(gdb) break MyClass::method

# Execution control
(gdb) continue      # Resume
(gdb) step          # Step into
(gdb) next          # Step over
(gdb) finish        # Step out

# Inspect variables
(gdb) print var
(gdb) print *ptr
(gdb) print array[5]
(gdb) display var   # Auto-print after each step

# Backtrace
(gdb) backtrace     # Stack trace
(gdb) frame 2       # Switch to frame 2
(gdb) up/down       # Navigate frames

# Watchpoints
(gdb) watch var     # Break when var changes
(gdb) rwatch var    # Break when var is read

# Conditional breakpoint
(gdb) break file.cpp:42 if x == 10

# Info commands
(gdb) info breakpoints
(gdb) info locals
(gdb) info args
```

### GDB Script
```bash
# debug.gdb
break main
run
continue
backtrace
quit

# Use it
gdb -x debug.gdb ./app
```

## Valgrind (Memory Profiler)

### Memory Leak Detection
```bash
valgrind --leak-check=full --show-leak-kinds=all ./app

# With suppressions
valgrind --leak-check=full --suppressions=valgrind.supp ./app
```

### Callgrind (Performance Profiling)
```bash
valgrind --tool=callgrind ./app
kcachegrind callgrind.out.*
```

### Helgrind (Thread Errors)
```bash
valgrind --tool=helgrind ./app
```

## Print Debugging

### Macro for Debug Prints
```cpp
#ifdef DEBUG
    #define DBG(x) std::cerr << #x << " = " << (x) << std::endl
    #define DBGV(v) do { \
        std::cerr << #v << " = ["; \
        for (size_t i = 0; i < v.size(); i++) { \
            if (i) std::cerr << ", "; \
            std::cerr << v[i]; \
        } \
        std::cerr << "]" << std::endl; \
    } while(0)
#else
    #define DBG(x)
    #define DBGV(v)
#endif

// Usage
int x = 42;
DBG(x);  // Prints: x = 42

std::vector<int> vec = {1, 2, 3};
DBGV(vec);  // Prints: vec = [1, 2, 3]
```

### Compile with debug
```bash
g++ -DDEBUG -g main.cpp -o app
```

## Assertions

```cpp
#include <cassert>

void process(int* ptr) {
    assert(ptr != nullptr);  // Debug builds only
    // ...
}

// Custom assert with message
#define ASSERT(cond, msg) \
    if (!(cond)) { \
        std::cerr << "Assertion failed: " << (msg) << std::endl; \
        std::abort(); \
    }

ASSERT(x > 0, "x must be positive");
```

## Core Dumps

### Enable core dumps
```bash
ulimit -c unlimited
./app  # Crashes and generates core

# Analyze core dump
gdb ./app core
(gdb) backtrace
```

## Performance Profiling

### perf (Linux)
```bash
# Record
perf record -g ./app

# Report
perf report

# Top hotspots
perf top
```

### gprof
```bash
# Compile with profiling
g++ -pg -O2 main.cpp -o app

# Run
./app

# Generate report
gprof app gmon.out > analysis.txt
```

### Time Measurement
```cpp
#include <chrono>

auto start = std::chrono::high_resolution_clock::now();

// Code to measure

auto end = std::chrono::high_resolution_clock::now();
auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end - start);

std::cout << "Time: " << duration.count() << " µs\n";
```

## Common Bug Patterns

### 1. Uninitialized Variable
```cpp
int x;  // ❌ Uninitialized
std::cout << x;  // Undefined behavior

int x = 0;  // ✓ Initialized
```

### 2. Buffer Overflow
```cpp
int arr[10];
arr[15] = 42;  // ❌ Overflow

// Use vector for safety
std::vector<int> vec(10);
vec.at(15) = 42;  // ✓ Throws exception
```

### 3. Use After Free
```cpp
int* ptr = new int(42);
delete ptr;
*ptr = 10;  // ❌ Use after free

// Use smart pointers
auto ptr = std::make_unique<int>(42);
// Automatic cleanup
```

### 4. Dangling Reference
```cpp
std::string& getBadRef() {
    std::string local = "temp";
    return local;  // ❌ Returns reference to destroyed object
}

std::string getGoodValue() {
    std::string local = "temp";
    return local;  // ✓ Returns by value (RVO)
}
```

### 5. Iterator Invalidation
```cpp
std::vector<int> vec = {1, 2, 3};
for (auto it = vec.begin(); it != vec.end(); ++it) {
    if (*it == 2) {
        vec.erase(it);  // ❌ Invalidates iterator
        // ✓ it = vec.erase(it);
    }
}
```

## Debugging Tools Summary

| Tool | Purpose |
|------|---------|
| GDB | Interactive debugging |
| Valgrind | Memory leaks, profiling |
| AddressSanitizer | Fast memory error detection |
| UBSan | Undefined behavior |
| ThreadSanitizer | Data races |
| perf | Linux performance profiling |
| gprof | Function-level profiling |
| strace | System call tracing |
| ltrace | Library call tracing |

## Best Practices

1. **Compile with warnings** - Fix all warnings
2. **Use sanitizers** in development
3. **Test with Valgrind** before release
4. **Profile before optimizing**
5. **Write unit tests** for reproducible bugs
6. **Use version control** for bisecting regressions
