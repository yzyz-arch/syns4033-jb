---
name: cpp-stl-deep-dive
description: C++ STL containers, algorithms, and iterators mastery.
tags: [cpp, stl, containers, algorithms, iterators]
version: 1.0.0
---

# C++ STL Deep Dive

Master C++ Standard Template Library - containers, algorithms, and iterators.

## When to Use

Load when:
- Choosing optimal containers for data storage
- Using STL algorithms effectively
- Understanding iterator categories
- Performance optimization with STL

## Containers Overview

| Container | Access | Insert/Delete | Use Case |
|-----------|--------|---------------|----------|
| `vector` | O(1) | O(n) front, O(1) back | Dynamic array, random access |
| `deque` | O(1) | O(1) front/back | Double-ended queue |
| `list` | O(n) | O(1) anywhere | Frequent insertions |
| `array` | O(1) | N/A | Fixed-size array |
| `map` | O(log n) | O(log n) | Ordered key-value |
| `unordered_map` | O(1) avg | O(1) avg | Hash table |
| `set` | O(log n) | O(log n) | Unique sorted values |
| `unordered_set` | O(1) avg | O(1) avg | Unique hash values |
| `stack` | O(1) top | O(1) push/pop | LIFO |
| `queue` | O(1) front | O(1) push/pop | FIFO |
| `priority_queue` | O(1) top | O(log n) | Heap |

## Vector

```cpp
#include <vector>

// Creation
std::vector<int> vec;
std::vector<int> vec(10);           // 10 zeros
std::vector<int> vec(10, 5);        // 10 fives
std::vector<int> vec{1, 2, 3};      // Initializer list

// Capacity
vec.size();
vec.capacity();
vec.empty();
vec.reserve(100);       // Pre-allocate
vec.shrink_to_fit();    // Free unused memory

// Access
vec[i];                 // No bounds check
vec.at(i);              // Bounds checked
vec.front();
vec.back();
vec.data();             // Raw pointer

// Modification
vec.push_back(10);
vec.pop_back();
vec.insert(vec.begin() + 2, 42);
vec.erase(vec.begin() + 2);
vec.clear();

// Performance tip
vec.reserve(n);         // Avoid reallocations
vec.emplace_back(args); // Construct in-place
```

## Map vs Unordered Map

### Map (Red-Black Tree)
```cpp
#include <map>

std::map<std::string, int> map;
map["key"] = 100;
map.insert({"key2", 200});
map.emplace("key3", 300);

// Iteration (sorted order)
for (const auto& [key, val] : map) {
    std::cout << key << ": " << val << "\n";
}

// Search
if (map.find("key") != map.end()) { /* found */ }
if (map.count("key")) { /* found */ }

// Lower/Upper bound
auto it = map.lower_bound("b");  // First >= "b"
auto it = map.upper_bound("b");  // First > "b"
```

### Unordered Map (Hash Table)
```cpp
#include <unordered_map>

std::unordered_map<std::string, int> umap;
umap["key"] = 100;

// Custom hash
struct MyHash {
    size_t operator()(const MyKey& k) const {
        return std::hash<int>{}(k.id);
    }
};

std::unordered_map<MyKey, int, MyHash> custom_map;
```

## Set vs Unordered Set

```cpp
#include <set>
#include <unordered_set>

// Set (ordered)
std::set<int> s{3, 1, 2};  // Stored as 1, 2, 3
s.insert(4);
s.erase(2);
bool exists = s.count(3);

// Unordered set (hash-based)
std::unordered_set<int> us{3, 1, 2};
us.insert(4);

// Multiset (allows duplicates)
std::multiset<int> ms{1, 1, 2, 3};
```

## Deque

```cpp
#include <deque>

std::deque<int> dq;
dq.push_back(1);
dq.push_front(0);   // Efficient O(1)
dq.pop_back();
dq.pop_front();     // Efficient O(1)

// Random access like vector
dq[2] = 10;
```

## List (Doubly-Linked List)

```cpp
#include <list>

std::list<int> lst{1, 2, 3};
lst.push_front(0);
lst.push_back(4);

// Insert anywhere O(1)
auto it = lst.begin();
++it;
lst.insert(it, 99);  // Insert before position

// Splice (move elements from another list)
std::list<int> other{10, 20};
lst.splice(lst.begin(), other);  // Move all from other
```

## Stack, Queue, Priority Queue

```cpp
#include <stack>
#include <queue>

// Stack (LIFO)
std::stack<int> stk;
stk.push(1);
int top = stk.top();
stk.pop();

// Queue (FIFO)
std::queue<int> q;
q.push(1);
int front = q.front();
q.pop();

// Priority Queue (Max Heap default)
std::priority_queue<int> pq;
pq.push(10);
pq.push(5);
int max = pq.top();  // 10
pq.pop();

// Min Heap
std::priority_queue<int, std::vector<int>, std::greater<int>> min_pq;
```

## STL Algorithms

### Sorting
```cpp
#include <algorithm>

std::vector<int> vec{3, 1, 4, 1, 5};

// Sort
std::sort(vec.begin(), vec.end());

// Custom comparator
std::sort(vec.begin(), vec.end(), std::greater<int>());
std::sort(vec.begin(), vec.end(), [](int a, int b) {
    return a > b;
});

// Partial sort
std::partial_sort(vec.begin(), vec.begin() + 3, vec.end());

// Stable sort
std::stable_sort(vec.begin(), vec.end());
```

### Searching
```cpp
// Binary search (sorted container required)
bool found = std::binary_search(vec.begin(), vec.end(), 5);

// Lower/Upper bound
auto it = std::lower_bound(vec.begin(), vec.end(), 3);  // First >= 3
auto it = std::upper_bound(vec.begin(), vec.end(), 3);  // First > 3

// Find
auto it = std::find(vec.begin(), vec.end(), 5);
if (it != vec.end()) { /* found */ }

// Find if
auto it = std::find_if(vec.begin(), vec.end(), [](int x) {
    return x > 10;
});
```

### Modification
```cpp
// Fill
std::fill(vec.begin(), vec.end(), 0);

// Replace
std::replace(vec.begin(), vec.end(), 5, 10);  // 5 -> 10

// Remove (does NOT resize!)
vec.erase(std::remove(vec.begin(), vec.end(), 5), vec.end());

// Transform
std::vector<int> result(vec.size());
std::transform(vec.begin(), vec.end(), result.begin(), [](int x) {
    return x * 2;
});

// Reverse
std::reverse(vec.begin(), vec.end());

// Rotate
std::rotate(vec.begin(), vec.begin() + 2, vec.end());
```

### Accumulation & Reduction
```cpp
#include <numeric>

// Sum
int sum = std::accumulate(vec.begin(), vec.end(), 0);

// Product
int prod = std::accumulate(vec.begin(), vec.end(), 1, std::multiplies<int>());

// Inner product
std::vector<int> v1{1, 2, 3};
std::vector<int> v2{4, 5, 6};
int dot = std::inner_product(v1.begin(), v1.end(), v2.begin(), 0);

// Partial sum
std::vector<int> prefix(vec.size());
std::partial_sum(vec.begin(), vec.end(), prefix.begin());
```

### Permutations
```cpp
std::vector<int> vec{1, 2, 3};

// Next permutation
do {
    // Process permutation
} while (std::next_permutation(vec.begin(), vec.end()));

// Previous permutation
while (std::prev_permutation(vec.begin(), vec.end())) {
    // Process
}
```

## Iterator Categories

| Category | Operations | Examples |
|----------|-----------|----------|
| Input | Read, single-pass | `istream_iterator` |
| Output | Write, single-pass | `ostream_iterator` |
| Forward | Read/Write, multi-pass | `forward_list::iterator` |
| Bidirectional | Forward + backward | `list::iterator`, `map::iterator` |
| Random Access | + arbitrary jumps | `vector::iterator`, `deque::iterator` |

### Iterator Usage
```cpp
// Distance
auto dist = std::distance(vec.begin(), vec.end());

// Advance
auto it = vec.begin();
std::advance(it, 5);  // Move 5 positions

// Next/Prev
auto next_it = std::next(it);
auto prev_it = std::prev(it);
```

## Performance Guidelines

1. **Vector** - Default choice, best cache locality
2. **Deque** - When needing push_front/pop_front
3. **List** - Frequent insertions/deletions in middle
4. **Map** - Need sorted order or range queries
5. **Unordered Map** - Pure lookups, no order needed
6. **Reserve capacity** - For vectors with known size
7. **Erase-remove idiom** - For removing elements
8. **Emplace over insert** - Construct in-place

## Common Patterns

### Erase-Remove Idiom
```cpp
vec.erase(std::remove(vec.begin(), vec.end(), value), vec.end());
```

### Count Unique Elements
```cpp
std::set<int> unique(vec.begin(), vec.end());
int count = unique.size();
```

### Check if Sorted
```cpp
bool sorted = std::is_sorted(vec.begin(), vec.end());
```

### Min/Max Element
```cpp
auto min_it = std::min_element(vec.begin(), vec.end());
auto max_it = std::max_element(vec.begin(), vec.end());
```

### Partition
```cpp
// Move even numbers to front
auto it = std::partition(vec.begin(), vec.end(), [](int x) {
    return x % 2 == 0;
});
```
