## Python Lists Are Slow at the Front
Category: DSA · Platform: instagram · Format: screen · Audience: beginner

### Voice-over
1. Python lists are fast at the end, but slow at the front.
2. Six tasks. Pop zero removes the first one.
3. The other five each shift one slot left.
4. Insert at zero shifts them all right again.
5. A million items? Almost a million shifts. O of n: work grows with size.
6. A deque, a double-ended queue, pops the front without shifting.
7. Same work at any size: O of one. Follow @yourhandle for more Python tips.

### Shot list
Screen recording of a Python REPL in a terminal. Zoom the font so the code sits in the middle of the
frame, clear of the bottom 20% (caption, audio) and right 15% (buttons); headings and captions are
overlays, also mid-frame.

| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | PYTHON LISTS | Fast at the end, *slow* at the front | REPL with the list typed and printed: `[1, 2, 3, 4, 5, 6]` | `tasks = [1, 2, 3, 4, 5, 6]` |
| 2 | TAKE THE FIRST | Remove the *first* task | Type `tasks.pop(0)`; the REPL prints `1` | `tasks.pop(0)` |
| 3 | FIVE SHIFTS | The other *5* move one slot left | Type `tasks`, output `[2, 3, 4, 5, 6]`; overlay arrows slide each number one slot left; counter SHIFTS: 5 | `tasks  # [2, 3, 4, 5, 6]` |
| 4 | AND BACK AGAIN | Adding at the front: *5* more shifts | Type `tasks.insert(0, 1)`, then `tasks`: `[1, 2, 3, 4, 5, 6]`; arrows slide right; SHIFTS: 5 | `tasks.insert(0, 1)` |
| 5 | A MILLION ITEMS | *999,999* shifts for one pop | Type the line, then `big.pop(0)` prints `0`; counter SHIFTS: 999,999; label "O(n)" | `big = list(range(1_000_000))` |
| 6 | USE A DEQUE | Both ends, *no* shifting | `from collections import deque` and `q = deque([1, 2, 3, 4, 5, 6])` already typed; type `q.popleft()`, prints `1`; SHIFTS: 0 | `q.popleft()` |
| 7 | SAME AT ANY SIZE | Front of a deque: *O(1)* | Payoff card "list front: O(n) · deque front: O(1)" mid-frame, then the follow prompt | |

### Hook options
1. Python lists are fast at the end, but slow at the front. (recommended)
2. Why are Python lists slow at the front?
3. Using a Python list as a queue? pop(0) shifts the rest.

### Cheat sheet
- Use when: Queues (first in, first out) · Adding or removing at the front · Keeping the last N items (`maxlen`)
- Trade-offs: Middle indexing is O(n) · No slicing · Lists stay best for random access
- Snippet:
```python
from collections import deque
tasks = deque([1, 2, 3, 4, 5, 6])
tasks.append(7)          # add to the back: O(1)
first = tasks.popleft()  # take from the front: O(1)
print(first, list(tasks))  # 1 [2, 3, 4, 5, 6, 7]
```
- Comparison:

| Structure | Front add/remove | End add/remove | Read by index |
|---|---|---|---|
| list | O(n) | O(1) amortized | O(1) |
| deque | O(1) | O(1) | O(1) ends, O(n) middle |

### Caption
Using a Python list as a queue? pop(0) is doing more work than it looks.

A list keeps its items in one row of slots. Remove or insert at the front and every other item shifts
by one slot, so the cost grows with the list: O(n). append() and pop() work at the end, where nothing
has to shift, so they stay fast. When you need the front, collections.deque adds and removes at both
ends in O(1). One catch: reading the middle of a deque is O(n), so keep lists for random access.

Where in your code are you calling pop(0) right now?

#python #pythontips #datastructures #timecomplexity #learnpython

### Claims checked
- `list.pop(0)` and `list.insert(0, x)` are O(n): timed with `timeit` on Python 3.13 (CPython); insert(0)+pop(0) took 0.9 / 7.4 / 88 / 806 µs at 1k / 10k / 100k / 1M items (grows with size).
- `append()` / `pop()` at the end stay flat (0.05-0.09 µs at every size): same run. Append is amortized O(1): own knowledge (occasional resize), stable fact.
- `deque.appendleft` / `popleft` stay flat (0.07-0.10 µs at every size): same run.
- Pop(0) on `[1, 2, 3, 4, 5, 6]` returns 1 and leaves 5 items, all shifted; insert(0, 1) restores 6 items: ran it.
- A million-item list: one pop(0) shifts 999,999 items (n - 1): computed; `big.pop(0)` prints 0 since `range` starts at 0.
- `deque.popleft()` moves no other item (deque is a list of blocks; only the left end moves): own knowledge of the CPython implementation, consistent with the flat timings; deque docstring: "A list-like sequence optimized for data accesses near its endpoints."
- Deque middle indexing is O(n): `d[n//2]` took 0.12 µs at 10k vs 34.5 µs at 1M.
- Deque has no slicing: `deque("abc")[1:2]` raises `TypeError: sequence index must be integer, not 'slice'`.
- `maxlen` keeps the last N items: `deque(range(5), maxlen=3)` -> `deque([2, 3, 4], maxlen=3)`.
- Snippet: ran it, prints `1 [2, 3, 4, 5, 6, 7]`.
- Instagram 5-hashtag limit: from the skill's platform notes (reported December 2025), not re-checked.

### Unverified
- none

### Validation
PASS: Python Lists Are Slow at the Front (7 beats, 74 words, ~27 s)
- WARN 'every' (post caption): "every other item shifts" is literally true for front insert/remove.
- WARN 'zero' (beats 2, 4): "pop zero" / "insert at zero" name index 0, not an absolute claim.

### Changes
- Cut "Hey everyone, welcome back!! Today I'll show you...": hooks open with the topic, no greeting; beat 1 is now a true counter-intuitive fact.
- "Python lists are super fast for everything" -> "fast at the end, but slow at the front": the original is a false absolute.
- "`list.insert(0, x)` is O(1), exactly like append" was wrong: inserting at the front shifts every item, O(n) (timed: 806 µs at 1M items vs 0.07 µs for append+pop). Append itself is amortized O(1), not strictly O(1).
- "`list.pop(0)` is also O(1)" was wrong: it is O(n) for the same reason; only `pop()` from the end is O(1).
- "`x in my_list` is instant because lists use hashing" was wrong: it is a left-to-right scan, O(n) (10 ms for a miss at 1M items), and lists don't hash (`[1] in [[1]]` works although a list can't be hashed). Removed from this reel: it is a second idea (scan vs hash) and makes a good separate reel on `set`.
- "Dictionaries are always O(1), 100% guaranteed" was wrong: O(1) on average, O(n) in the worst case (keys with equal hashes: lookup went from 6.6 to 67.8 µs for 100 -> 1,000 keys). Removed: a third idea, off-topic for lists.
- "Never use collections.deque, it's useless" was backwards: deque is the fix for front operations, so it is now the payoff.
- "Like, follow and subscribe!!!" -> one CTA, "Follow @yourhandle for more Python tips" (kept your wording; "subscribe" is YouTube, not Instagram).
- Length: one mechanism in 7 beats, under 75 words (the draft packed six claims into about 90 words).
- Kept your examples `insert(0, x)`, `pop(0)`, `append` and `deque`, with a six-task list so every number on screen is what the code prints.
