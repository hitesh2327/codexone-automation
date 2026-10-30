# Worked examples

Two complete scripts in the skill's output format. Both passed the review in `SKILL.md`.

---

## Binary Search - halve the search space with every comparison
Category: DSA · Spoken words: 54 (~20 s) · Beats: 6

### Hook options
1. Why does binary search find anything so fast?  <- recommended
2. Six checks or two? Same array, same target.
3. Still scanning sorted arrays one by one?

### Script
| # | Heading (on screen) | Narration (spoken) | Caption (on screen) | Visual change | Code / terminal |
|---|---|---|---|---|---|
| 1 | BINARY SEARCH | Why does binary search find anything so fast? Let's find 25. | Find *25* in a sorted array | Array `[3, 8, 12, 17, 21, 25]` appears; a pointer sweeps in | |
| 2 | THE NAIVE WAY | Checking one by one takes six comparisons here. | Linear scan touches *every* cell | Each cell lights up in turn; COMPARES counter ticks to 6 | `for x in arr: ...` |
| 3 | CHECK THE MIDDLE | Instead, check the middle element first. | mid is *17*, too small | Pointer jumps to index 3 (17); COMPARES resets to 1 | `mid = (lo + hi + 1) // 2` |
| 4 | DROP HALF | Seventeen is smaller, so drop the left half. | Left half is *discarded* | Cells 3, 8, 12, 17 fade out | `lo = mid + 1` |
| 5 | FOUND | The next middle is twenty-five. Found it in two. | Two compares, not *six* | Pointer lands on index 5 (25), cell turns green; COMPARES = 2 | `return mid  # 5` |
| 6 | HALVE IT | Halve every step: O of log n. Follow @yourhandle for more DSA. | Sorted input, *log n* steps | Payoff card: "Halve each step. O(log n) time." | |

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
Binary search finds an item in a sorted array by checking the middle and throwing away half of
what's left on every step. That's why a million items need only about twenty comparisons. Save this
for your next interview, then try writing it from memory without an off-by-one bug. Which edge case
trips you up most?

#binarysearch #dsa #algorithms #codinginterview #python

### Review
- Fixed: the first draft showed `mid = (lo + hi) // 2` in beat 3, which picks index 2 (12), not 17.
  The upper middle `(lo + hi + 1) // 2` gives 17, then 25: exactly the 2 comparisons on screen.
- Fixed: hook alternative "1000x faster" removed (invented number).
- Checks: words 54/75 ✓, beats 6 ✓, on-screen limits ✓, CTA in last beat ✓

---

## Tell Me About Yourself - present, past, future
Category: Interview & careers · Spoken words: 49 (~18 s) · Beats: 6

### Hook options
1. "Tell me about yourself." Why do most answers fall flat?  <- recommended
2. Your first interview answer is probably a life story.
3. The 90-second answer that opens every interview.

### Script
| # | Heading (on screen) | Narration (spoken) | Caption (on screen) | Visual change | Code / terminal |
|---|---|---|---|---|---|
| 1 | TELL ME ABOUT YOU | "Tell me about yourself." Why do most answers fall flat? | The *first* question in most rounds | Interviewer -> question bubble appears | |
| 2 | THE LIFE STORY | Reciting your whole life story loses them fast. | Chronology hides *what matters* | A long timeline scrolls; it turns red | |
| 3 | START WITH NOW | Start with now: your role and one win. | Current role plus *one* result | "PRESENT" box lights up | |
| 4 | LINK THE PAST | Then link back: what led you here. | Only the past that *explains* now | Arrow to "PAST" box | |
| 5 | POINT FORWARD | Finish forward: why this role fits next. | Tie it to *this* job | Arrow to "FUTURE" box -> "NEXT ROUND" | |
| 6 | PRESENT PAST FUTURE | Present, past, future. Follow @yourhandle for more interview tips. | A story with a *direction* | Payoff card: "Present. Past. Future." | |

### Cheat sheet
- Use when: Opening question of any round · Recruiter screens · Networking intros
- Trade-offs: Needs rehearsal, not memorising · Trim the past ruthlessly · Tailor the future to each job
- Template (an answer outline, not code):
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
"Tell me about yourself" opens most interviews, and a life story is the most common way to waste it.
Use present, past, future: what you do now with one result, the experience that led you here, and why
this role is your next step. Keep it short and rehearse it out loud a few times. What's the hardest
part of this question for you?

#interviewtips #techinterview #softwareengineer #careeradvice #jobsearch

### Review
- Fixed: hook alternative "80% of candidates fail this question" removed (invented statistic).
- Fixed: "90 seconds" kept only as a hook option phrased as advice, not as data.
- Checks: words 49/75 ✓, beats 6 ✓, on-screen limits ✓, CTA in last beat ✓
