---
name: cpp-competitive-programming
description: C++ competitive programming algorithms and patterns.
tags: [cpp, algorithms, competitive-programming, stl]
version: 1.0.0
---

# C++ Competitive Programming

Professional patterns and algorithms for competitive programming contests (Codeforces, AtCoder, TLX, etc).

## When to Use

Load when solving algorithmic problems requiring:
- Graph algorithms (BFS, DFS, Dijkstra, Floyd-Warshall)
- Dynamic programming
- Data structures (segment tree, fenwick tree, DSU)
- Number theory (GCD, prime, modular arithmetic)
- String algorithms (KMP, Z-algorithm, suffix array)

## Fast I/O Template

```cpp
#include <bits/stdc++.h>
using namespace std;

#define fast_io ios_base::sync_with_stdio(false); cin.tie(NULL); cout.tie(NULL);
#define ll long long
#define vi vector<int>
#define pii pair<int,int>
#define pb push_back
#define mp make_pair
#define F first
#define S second
#define all(v) v.begin(), v.end()

int main() {
    fast_io;
    // Your code here
    return 0;
}
```

## Common Algorithms

### 1. Binary Search
```cpp
// Find first element >= target
int lower_bound_manual(vector<int>& arr, int target) {
    int l = 0, r = arr.size();
    while (l < r) {
        int mid = l + (r - l) / 2;
        if (arr[mid] < target) l = mid + 1;
        else r = mid;
    }
    return l;
}

// STL version
auto it = lower_bound(arr.begin(), arr.end(), target);
```

### 2. Graph - BFS
```cpp
vector<int> bfs(int start, vector<vector<int>>& adj) {
    int n = adj.size();
    vector<int> dist(n, -1);
    queue<int> q;
    
    q.push(start);
    dist[start] = 0;
    
    while (!q.empty()) {
        int u = q.front(); q.pop();
        for (int v : adj[u]) {
            if (dist[v] == -1) {
                dist[v] = dist[u] + 1;
                q.push(v);
            }
        }
    }
    return dist;
}
```

### 3. Graph - DFS
```cpp
void dfs(int u, vector<vector<int>>& adj, vector<bool>& visited) {
    visited[u] = true;
    for (int v : adj[u]) {
        if (!visited[v]) {
            dfs(v, adj, visited);
        }
    }
}
```

### 4. Dynamic Programming - Knapsack
```cpp
int knapsack(vector<int>& weights, vector<int>& values, int W) {
    int n = weights.size();
    vector<vector<int>> dp(n + 1, vector<int>(W + 1, 0));
    
    for (int i = 1; i <= n; i++) {
        for (int w = 0; w <= W; w++) {
            if (weights[i-1] <= w) {
                dp[i][w] = max(dp[i-1][w], 
                              dp[i-1][w - weights[i-1]] + values[i-1]);
            } else {
                dp[i][w] = dp[i-1][w];
            }
        }
    }
    return dp[n][W];
}
```

### 5. Number Theory - GCD & LCM
```cpp
int gcd(int a, int b) {
    return b == 0 ? a : gcd(b, a % b);
}

int lcm(int a, int b) {
    return (a / gcd(a, b)) * b;  // Avoid overflow
}
```

### 6. Sorting with Custom Comparator
```cpp
// Sort by second element descending
sort(arr.begin(), arr.end(), [](pii a, pii b) {
    return a.second > b.second;
});
```

### 7. Prefix Sum
```cpp
vector<int> prefix_sum(vector<int>& arr) {
    int n = arr.size();
    vector<int> prefix(n + 1, 0);
    for (int i = 0; i < n; i++) {
        prefix[i + 1] = prefix[i] + arr[i];
    }
    return prefix;
}

// Query sum from l to r (0-indexed)
int range_sum(vector<int>& prefix, int l, int r) {
    return prefix[r + 1] - prefix[l];
}
```

### 8. Sliding Window
```cpp
int max_sum_subarray(vector<int>& arr, int k) {
    int n = arr.size();
    int max_sum = 0, window_sum = 0;
    
    for (int i = 0; i < k; i++) {
        window_sum += arr[i];
    }
    max_sum = window_sum;
    
    for (int i = k; i < n; i++) {
        window_sum += arr[i] - arr[i - k];
        max_sum = max(max_sum, window_sum);
    }
    return max_sum;
}
```

## STL Containers

### Priority Queue (Max Heap)
```cpp
priority_queue<int> pq;  // Max heap
priority_queue<int, vector<int>, greater<int>> min_pq;  // Min heap

pq.push(10);
int top = pq.top();
pq.pop();
```

### Set & Map
```cpp
set<int> s;
s.insert(10);
s.erase(10);
bool exists = s.count(10);  // 0 or 1

map<string, int> mp;
mp["key"] = 100;
if (mp.find("key") != mp.end()) { /* exists */ }
```

### Vector Operations
```cpp
vector<int> v = {1, 2, 3};
v.push_back(4);
v.pop_back();
reverse(v.begin(), v.end());
sort(v.begin(), v.end());
int sum = accumulate(v.begin(), v.end(), 0);
```

## Time Complexity Reference

| Operation | Complexity |
|-----------|-----------|
| Sorting (merge/quick) | O(n log n) |
| Binary search | O(log n) |
| BFS/DFS | O(V + E) |
| Dijkstra (priority queue) | O((V + E) log V) |
| Dynamic programming | O(n × m) typical |
| Sieve of Eratosthenes | O(n log log n) |

## Common Pitfalls

1. **Integer overflow** - Use `long long` for large calculations
2. **Array bounds** - Always check 0 <= i < n
3. **Uninitialized variables** - Initialize all arrays/vectors
4. **Wrong data type** - int vs long long, float vs double
5. **Off-by-one errors** - Check loop boundaries carefully

## Optimization Tips

1. Use `fast_io` for faster input/output
2. Avoid `endl` in loops - use `\\n` instead
3. Pass large objects by reference (`const vector<int>&`)
4. Reserve vector capacity if size is known (`v.reserve(n)`)
5. Use `emplace_back` instead of `push_back` for complex objects

## AI Common Mistakes & Mandatory Fixes

**CRITICAL: Before writing ANY C++ competitive programming solution, check these:**

### 1. Read Constraints FIRST
```cpp
// If problem says: 1 ≤ n ≤ 10^5
vector<int> arr(n);  // ✓ Dynamic size
int arr[100];        // ✗ WRONG - too small!

// If problem says: sum can be 10^9
long long sum = 0;   // ✓ Use long long
int sum = 0;         // ✗ WRONG - overflow!
```

### 2. Array/Vector Size Must Match Constraints
```cpp
// Constraint: n ≤ 200000
const int MAXN = 200005;  // ✓ Add buffer
int arr[MAXN];

// Or use dynamic allocation
int n; cin >> n;
vector<int> arr(n);  // ✓ Exact size needed
```

### 3. Check Time Complexity vs Constraints
| n | Max Allowed Complexity | Examples |
|---|---|---|
| n ≤ 10 | O(n!) | Permutations |
| n ≤ 20 | O(2^n) | Bitmask DP |
| n ≤ 500 | O(n³) | Floyd-Warshall |
| n ≤ 5000 | O(n²) | DP, Nested loops |
| n ≤ 10^5 | O(n log n) | Sorting, Binary search |
| n ≤ 10^6 | O(n) | Linear scan, prefix sum |

```cpp
// If n = 10^5, this will TLE:
for (int i = 0; i < n; i++) {
    for (int j = 0; j < n; j++) {  // O(n²) - TOO SLOW!
        // ...
    }
}

// Need O(n log n) or better - use sorting, binary search, or prefix sum
```

### 4. Integer Overflow - When to Use `long long`
```cpp
// Use long long if ANY of these are true:
// - Numbers can exceed 2×10^9 (int max is ~2.1×10^9)
// - Multiplication: if a*b where a,b > 50000
// - Factorial, exponentials, or cumulative sums

int a = 100000, b = 100000;
long long result = (long long)a * b;  // ✓ Cast before multiply
int result = a * b;  // ✗ Overflow before assignment!
```

### 5. Index Errors - 0-based vs 1-based
```cpp
// Most problems are 0-indexed unless explicitly stated
vector<int> arr(n);
for (int i = 0; i < n; i++) {  // ✓ 0 to n-1
    cin >> arr[i];
}

// If problem says "nodes numbered 1 to n":
vector<vector<int>> adj(n + 1);  // Size n+1, index 1 to n
for (int i = 1; i <= n; i++) {
    // Use 1-based indexing
}
```

### 6. Edge Cases - ALWAYS Test These
```cpp
// Before submitting, mentally test:
// - n = 1 (single element)
// - n = 2 (minimum interaction)
// - All elements same
// - All elements different
// - Sorted array vs reverse sorted
// - Negative numbers (if allowed)
// - Maximum constraint values
```

### 7. Input/Output Format Mistakes
```cpp
// Problem: "Print each answer on a new line"
for (int i = 0; i < n; i++) {
    cout << ans[i] << "\\n";  // ✓ Newline per answer
}

// Problem: "Print space-separated"
for (int i = 0; i < n; i++) {
    cout << ans[i];
    if (i < n - 1) cout << " ";  // ✓ No trailing space
}
cout << "\\n";

// Problem: "Print YES or NO"
cout << (condition ? "YES" : "NO") << "\\n";  // ✓ Exact case
```

### 8. Modulo Operations
```cpp
const int MOD = 1e9 + 7;

// Addition with mod
int add(int a, int b) {
    return ((a % MOD) + (b % MOD)) % MOD;
}

// Multiplication with mod
long long mul(long long a, long long b) {
    return ((a % MOD) * (b % MOD)) % MOD;
}

// Modular exponentiation
long long power(long long a, long long b, long long mod) {
    long long res = 1;
    a %= mod;
    while (b > 0) {
        if (b & 1) res = (res * a) % mod;
        a = (a * a) % mod;
        b >>= 1;
    }
    return res;
}
```

### 9. String Operations
```cpp
// Reading strings with spaces
string s;
getline(cin, s);  // Read full line with spaces

cin.ignore();  // Clear buffer after cin >> before getline

// String to int
int num = stoi(s);
long long num = stoll(s);

// Int to string
string s = to_string(num);
```

### 10. Sorting Edge Cases
```cpp
// Sort pairs by first element ascending, second descending
sort(arr.begin(), arr.end(), [](pii a, pii b) {
    if (a.first != b.first) return a.first < b.first;
    return a.second > b.second;  // Descending on tie
});

// Sort indices by array values
vector<int> idx(n);
iota(idx.begin(), idx.end(), 0);  // Fill 0,1,2,...,n-1
sort(idx.begin(), idx.end(), [&](int i, int j) {
    return arr[i] < arr[j];
});
```

## Mandatory Pre-Submit Checklist

**EVERY C++ solution MUST pass this before submitting:**

```cpp
// 1. Includes
#include <bits/stdc++.h>  // Or specific headers
using namespace std;

// 2. Fast I/O (for large inputs)
#define fast_io ios_base::sync_with_stdio(false); cin.tie(NULL);

// 3. Type definitions
#define ll long long
#define vi vector<int>
#define pii pair<int,int>

int main() {
    fast_io;
    
    // 4. Read constraints from problem
    int n; cin >> n;
    
    // 5. Allocate correct size
    vector<int> arr(n);
    for (int i = 0; i < n; i++) {
        cin >> arr[i];
    }
    
    // 6. Check time complexity matches constraint
    // If n ≤ 10^5, must be O(n log n) or better
    
    // 7. Use long long if numbers can exceed 2×10^9
    long long sum = 0;
    for (int x : arr) {
        sum += x;  // Safe because sum is ll
    }
    
    // 8. Output exact format from problem
    cout << sum << "\\n";
    
    return 0;
}
```

**Before submitting, ask yourself:**
1. ✓ Did I read the constraints? (n max, value ranges)
2. ✓ Is my time complexity acceptable? (Check table above)
3. ✓ Will integers overflow? (Use `long long` if unsure)
4. ✓ Are array sizes correct? (Dynamic or large enough static)
5. ✓ Did I test edge cases? (n=1, n=2, all same, all different)
6. ✓ Is output format exact? (Spaces, newlines, case sensitivity)
7. ✓ Did I compile and test with sample input?

**Compile & Test Command:**
```bash
# Compile with warnings
g++ -std=c++17 -O2 -Wall solution.cpp -o solution

# Test with sample input
./solution < input.txt

# Or inline test
echo "5
1 2 3 4 5" | ./solution
```
