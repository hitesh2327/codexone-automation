## Sliding Window: Max Sum of K Elements
Category: DSA · Platform: youtube · Format: animated · Audience: senior

### Voice-over
1. Sliding window turns O of n times k into O of n.
2. Naive max sum of three: re-add each window from scratch.
3. First window: two plus one plus five is eight.
4. Slide right: minus the two leaving, plus the one entering. Seven.
5. Slide again: minus one, plus three. Nine, the new max.
6. Last window: six. Each slide cost one subtraction, one addition.
7. It needs a fixed window size. Follow @yourhandle for more DSA.

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | SLIDING WINDOW | O(n·k) becomes *O(n)* | Array [2, 1, 5, 1, 3, 2] with a 3-cell frame, mid-frame | |
| 2 | THE NAIVE WAY | Each window *re-added* | Frame jumps; all 3 cells re-sum each time; OPS counter grows | `sum(a[i:i + k])` |
| 3 | FIRST WINDOW | 2 + 1 + 5 = *8* | Frame on cells 0-2; SUM = 8, BEST = 8 | `s = best = sum(a[:k])` |
| 4 | SLIDE RIGHT | -2, +1: *7* | Cell 0 fades out, cell 3 fades in; SUM = 7 | `s += a[i] - a[i - k]` |
| 5 | SLIDE AGAIN | -1, +3: *9* | Frame on cells 2-4; SUM = 9, BEST = 9 | `best = max(best, s)` |
| 6 | LAST WINDOW | -5, +2: *6* | Frame on cells 3-5; SUM = 6, BEST stays 9 | |
| 7 | FIXED K ONLY | One subtract, one *add* | Payoff card "Max = 9. O(n) time, O(1) space." | |

### Hook options
1. Sliding window turns O of n times k into O of n. (recommended)
2. Stop re-adding the same numbers in each window.
3. One subtraction and one addition per step: sliding window

### Cheat sheet
- Use when: Fixed-size subarray sums · Moving averages · Window counts over streams
- Trade-offs: Fixed k only · Guard 1 ≤ k ≤ n · Window maximum needs a deque
- Snippet:
```python
def max_window(a, k):
    if not 0 < k <= len(a): raise ValueError("bad k")
    s = best = sum(a[:k])
    for i in range(k, len(a)):
        s += a[i] - a[i - k]; best = max(best, s)
    return best
```
- Comparison:

| Approach | Time | Space | Works for |
|---|---|---|---|
| Recompute each window | O(n·k) | O(1) | Any window |
| Prefix sums | O(n) | O(n) | Many window queries |
| Sliding window | O(n) | O(1) | One fixed k |

### Caption
Title: Sliding window: max sum of k elements in O(n) #Shorts

Subtract the element leaving, add the one entering: each slide costs O(1), so the whole scan is O(n).
Works for a fixed window size.

#dsa #algorithms

### Claims checked
- Window sums of [2, 1, 5, 1, 3, 2] with k = 3 are 8, 7, 9, 6 and the max is 9: ran the snippet. It
  raises ValueError for k = 0 and k = 7, and returns the whole sum (14) for k = 6.
- Recomputing each window costs k additions per window, so O(n·k); the slide is one subtraction and one
  addition per step, so O(n) time and O(1) extra space.
- Prefix sums answer any window sum in O(1) after an O(n) pass with O(n) space.
- "Window maximum needs a deque" refers to the sliding window *maximum* (largest element per window),
  solved with a monotonic deque.

### Unverified
- none

### Validation
PASS
