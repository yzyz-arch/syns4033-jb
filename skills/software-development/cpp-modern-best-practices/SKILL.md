---
name: cpp-modern-best-practices
description: Modern C++ best practices (C++11/14/17/20/23).
tags: [cpp, modern-cpp, best-practices, c++20]
version: 1.0.0
---

# Modern C++ Best Practices

Professional C++ development patterns using C++11/14/17/20/23 features.

## When to Use

Load when:
- Writing production C++ code
- Refactoring legacy code to modern standards
- Need smart pointers, lambdas, ranges, or concepts
- Building performant, maintainable C++ applications

## Smart Pointers (C++11)

### Unique Pointer
```cpp
#include <memory>

// Prefer make_unique
auto ptr = std::make_unique<MyClass>(arg1, arg2);

// Transfer ownership
std::unique_ptr<MyClass> ptr2 = std::move(ptr);

// Raw pointer access (non-owning)
MyClass* raw = ptr2.get();
```

### Shared Pointer
```cpp
// Multiple owners
auto shared1 = std::make_shared<MyClass>();
auto shared2 = shared1;  // Reference count++

// Weak pointer (non-owning reference)
std::weak_ptr<MyClass> weak = shared1;
if (auto locked = weak.lock()) {
    // Object still alive
}
```

**Rule:** Prefer `unique_ptr` by default. Use `shared_ptr` only when multiple ownership is truly needed.

## Move Semantics (C++11)

```cpp
class MyClass {
    std::vector<int> data;
public:
    // Move constructor
    MyClass(MyClass&& other) noexcept 
        : data(std::move(other.data)) {}
    
    // Move assignment
    MyClass& operator=(MyClass&& other) noexcept {
        data = std::move(other.data);
        return *this;
    }
};

// Usage
MyClass obj1;
MyClass obj2 = std::move(obj1);  // Efficient, no copy
```

## Lambdas (C++11/14)

```cpp
// Basic lambda
auto add = [](int a, int b) { return a + b; };

// Capture by value
int x = 10;
auto f1 = [x]() { return x * 2; };

// Capture by reference
auto f2 = [&x]() { x++; };

// Capture all by value
auto f3 = [=]() { return x + y; };

// Capture all by reference
auto f4 = [&]() { x++; y++; };

// Generic lambda (C++14)
auto print = [](auto x) { std::cout << x << "\n"; };

// Init capture (C++14)
auto ptr = std::make_unique<int>(42);
auto f5 = [p = std::move(ptr)]() { return *p; };
```

## Range-based For Loop (C++11)

```cpp
std::vector<int> vec = {1, 2, 3};

// Read-only
for (const auto& val : vec) {
    std::cout << val << "\n";
}

// Modify elements
for (auto& val : vec) {
    val *= 2;
}

// Copy (avoid unless needed)
for (auto val : vec) {  // Copies each element
    // ...
}
```

## Auto Type Deduction (C++11)

```cpp
// Prefer auto for complex types
auto it = myMap.find("key");
auto ptr = std::make_unique<Widget>();

// Use explicit types for clarity
int count = 0;          // Clear intent
double ratio = 0.5;     // Clear intent

// Auto with const&
const auto& ref = getLargeObject();
```

## Structured Bindings (C++17)

```cpp
std::pair<int, std::string> getPair() {
    return {42, "hello"};
}

auto [num, str] = getPair();
std::cout << num << " " << str << "\n";

// Map iteration
std::map<int, std::string> myMap;
for (const auto& [key, value] : myMap) {
    std::cout << key << ": " << value << "\n";
}
```

## Optional (C++17)

```cpp
#include <optional>

std::optional<int> findValue(const std::vector<int>& vec, int target) {
    auto it = std::find(vec.begin(), vec.end(), target);
    if (it != vec.end()) {
        return *it;
    }
    return std::nullopt;
}

// Usage
if (auto val = findValue(vec, 42)) {
    std::cout << "Found: " << *val << "\n";
} else {
    std::cout << "Not found\n";
}
```

## String View (C++17)

```cpp
#include <string_view>

// Efficient non-owning string reference
void processString(std::string_view sv) {
    std::cout << sv << "\n";
}

std::string str = "hello";
processString(str);      // No copy
processString("world");  // No copy
```

## Concepts (C++20)

```cpp
#include <concepts>

// Define concept
template<typename T>
concept Addable = requires(T a, T b) {
    { a + b } -> std::convertible_to<T>;
};

// Use concept
template<Addable T>
T add(T a, T b) {
    return a + b;
}
```

## Ranges (C++20)

```cpp
#include <ranges>
namespace rng = std::ranges;
namespace views = std::views;

std::vector<int> vec = {1, 2, 3, 4, 5};

// Filter and transform
auto result = vec 
    | views::filter([](int x) { return x % 2 == 0; })
    | views::transform([](int x) { return x * 2; });

for (int x : result) {
    std::cout << x << " ";  // 4 8
}
```

## Initialization (C++11/17)

```cpp
// Uniform initialization
std::vector<int> vec{1, 2, 3};
std::string str{"hello"};

// Direct list initialization (C++17)
std::vector vec{1, 2, 3};  // Type deduced

// If-init statement (C++17)
if (auto it = myMap.find(key); it != myMap.end()) {
    // Use it here
}
```

## Constexpr (C++11/14/17/20)

```cpp
// Compile-time constant
constexpr int factorial(int n) {
    return n <= 1 ? 1 : n * factorial(n - 1);
}

constexpr int val = factorial(5);  // Computed at compile time

// constexpr if (C++17)
template<typename T>
auto process(T value) {
    if constexpr (std::is_integral_v<T>) {
        return value * 2;
    } else {
        return value;
    }
}
```

## Perfect Forwarding (C++11)

```cpp
template<typename T, typename... Args>
std::unique_ptr<T> make_unique(Args&&... args) {
    return std::unique_ptr<T>(new T(std::forward<Args>(args)...));
}
```

## Code Quality Rules

1. **RAII** - Resource Acquisition Is Initialization
   - Use smart pointers, containers, RAII wrappers
   - No manual `new`/`delete`

2. **Rule of Zero/Five**
   - Rule of Zero: Let compiler generate special members
   - Rule of Five: If you define one special member, define all five

3. **Const Correctness**
   - Mark methods `const` when they don't modify state
   - Use `const&` for read-only parameters

4. **Avoid Raw Pointers**
   - Use `unique_ptr`, `shared_ptr`, or references
   - Raw pointers only for non-owning observation

5. **Prefer Standard Library**
   - Use `std::vector` over C arrays
   - Use `std::string` over `char*`
   - Use algorithms over raw loops

## Performance Tips

1. **Pass by const reference** for large objects
2. **Return by value** - Compiler optimizes (RVO/NRVO)
3. **Use `reserve()` for vectors** when size is known
4. **Avoid unnecessary copies** - Use move semantics
5. **Profile before optimizing** - Don't guess

## Common Mistakes

1. **Dangling references** - Returning reference to local
2. **Use after move** - Accessing moved-from objects
3. **Forgetting `const`** - Missing optimization opportunities
4. **Naked `new`/`delete`** - Use smart pointers
5. **Comparing with `NULL`** - Use `nullptr`
