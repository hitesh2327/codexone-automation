# Worked examples

Two complete scripts in the skill's output format. Both pass `scripts/check.py`.

---

## Binary Search
Category: DSA · Platform: instagram · Format: animated · Audience: beginner

### Voice-over
1. Binary search finds 25 in three checks, not six. Here's how.
2. A linear scan checks each number in turn: six comparisons here.
3. Start in the middle: index two holds twelve.
4. Twelve is too small, so drop the whole left half.
5. Next middle: twenty-one. Too small, drop again.
6. Only twenty-five is left. Found it in three checks.
7. Halve the range each step: O of log n. Follow @yourhandle for more DSA.

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | BINARY SEARCH | Find *25* in a sorted array | Array [3, 8, 12, 17, 21, 25] slides in; a pointer bounces above it | |
| 2 | THE NAIVE WAY | A scan touches *each* cell | Cells light up one by one; COMPARES counter ticks to 6 | `arr.index(25)  # O(n) scan` |
| 3 | START IN THE MIDDLE | Middle holds *12* | COMPARES resets to 1; pointer jumps to index 2 (12) | `mid = (lo + hi) // 2` |
| 4 | DROP HALF | 12 < 25: left half *gone* | Cells 3, 8, 12 fade out; COMPARES = 1 | `lo = mid + 1` |
| 5 | AGAIN | Middle is *21*, drop again | Pointer to index 4 (21); 17 and 21 fade; COMPARES = 2 | `lo = mid + 1` |
| 6 | FOUND | *3* checks instead of *6* | Pointer lands on 25, cell turns green; COMPARES = 3 | `arr[mid] == 25  # True` |
| 7 | HALVE IT | Sorted input, *log n* steps | Payoff card "Halve each step. O(log n) time." in the middle of the frame | |

### Hook options
1. Binary search finds 25 in three checks, not six. (recommended)
2. Still scanning sorted arrays one number at a time?
3. Why binary search needs only twenty checks for a million items

### Cheat sheet
- Use when: Input is already sorted · Many lookups, few inserts · Searching a monotonic answer
- Trade-offs: Needs sorted data · Off-by-one bugs are common · Linked lists don't fit
- Snippet:
```python
from bisect import bisect_left
i = bisect_left(arr, x)
found = i < len(arr) and arr[i] == x
```
- Comparison:

| Approach | Time | Space | Needs |
|---|---|---|---|
| Linear scan | O(n) | O(1) | Nothing |
| Hash set | O(1) avg | O(n) | Extra memory |
| Binary search | O(log n) | O(1) | Sorted input |

### Caption
Binary search finds an item in a sorted array by checking the middle and throwing away half of what's
left on each step. That's why a million sorted items need only about twenty comparisons. Save this for
your next interview, then try writing it from memory without an off-by-one bug. Which edge case trips
you up most? Drop it in the comments.

#binarysearch #dsa #algorithms #codinginterview #python

### Claims checked
- 3 comparisons with `(lo + hi) // 2` (12, 21, 25) and 6 with a linear scan: re-computed step by step.
- `arr.index(25)` scans left to right (O(n)): Python documentation for `list.index`.
- The `bisect_left` snippet finds 25 at index 5: ran it.
- About 20 comparisons for a million items: log2(1,000,000) ≈ 19.9, so at most 20.

### Unverified
- none

### Validation
PASS (`python3 scripts/check.py examples.md`)

---

## Tell Me About Yourself
Category: Interview & careers · Platform: youtube · Format: talking · Audience: beginner

### Voice-over
1. "Tell me about yourself." Why do most answers fall flat?
2. Reciting your whole life story loses them fast.
3. Start with now: your role and one win.
4. Then link back: what led you here.
5. Finish forward: why this role fits next.
6. Present, past, future. Follow @yourhandle for more interview tips.

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | TELL ME ABOUT YOU | The *first* question in most rounds | Speaker to camera; text card with the question, mid-frame | |
| 2 | THE LIFE STORY | Chronology hides *what matters* | Cut to a long scrolling timeline overlay that turns red | |
| 3 | START WITH NOW | Current role plus *one* result | Overlay card "PRESENT" appears beside the speaker | |
| 4 | LINK THE PAST | Only the past that *explains* now | Arrow from "PRESENT" to a new "PAST" card | |
| 5 | POINT FORWARD | Tie it to *this* job | Arrow to a "FUTURE" card; speaker points to it | |
| 6 | PRESENT PAST FUTURE | A story with a *direction* | All three cards in a row; follow prompt mid-frame | |

### Hook options
1. "Tell me about yourself." Why do most answers fall flat? (recommended)
2. Your answer to tell me about yourself is probably a life story.
3. A three-part answer for tell me about yourself

### Cheat sheet
- Use when: Opening question of most rounds · Recruiter screens · Networking intros
- Trade-offs: Needs rehearsal, not memorising · Trim the past ruthlessly · Tailor the future to each job
- Snippet (an answer template, not code):
```text
Now:    I'm a ___ who ___ (one result).
Before: I learned ___ at ___.
Next:   I want ___, which is why this role.
```
- Comparison:

| Style | Focus | Length | Impression |
|---|---|---|---|
| Life story | Chronology | Long | Unfocused |
| Resume recap | Job titles | Medium | Forgettable |
| Present-past-future | Relevance | Short | Clear |

### Caption
Title: Tell me about yourself: the present, past, future answer #Shorts

Swap the life story for three parts: what you do now with one result, the experience that led you
here, and why this role is your next step. Keep it short and rehearse it out loud.

#interviewtips #careeradvice

### Claims checked
- Present-past-future is presented as a common structure, not as data: no statistics used.
- "The first question in most rounds" is hedged ("most"), not an absolute.

### Unverified
- none

### Validation
PASS (`python3 scripts/check.py examples.md`)
