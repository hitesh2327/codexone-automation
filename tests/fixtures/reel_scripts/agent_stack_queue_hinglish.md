## Stack vs Queue
Category: DSA · Platform: instagram · Format: animated · Audience: beginner

### Voice-over
1. स्टैक और क्यू में एक, दो, तीन डालो। पहले कौन सा निकलेगा?
2. दोनों से पहले एक निकलेगा? आधा गलत।
3. स्टैक: ऊपर डालो, ऊपर से निकालो।
4. तीन आखिर में आया, पर पहले निकला।
5. क्यू: पीछे डालो, आगे से निकालो।
6. एक पहले आया, तो पहले निकला।
7. सबसे नया पहले? स्टैक। सबसे पुराना पहले? क्यू। और डीएसए के लिए फॉलो करो योरहैंडल।

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | STACK VS QUEUE | Put in *1, 2, 3*. What comes out first? | Split screen, mid-frame: vertical STACK tube (left), horizontal QUEUE lane (right, kept clear of the right 15% button area). Tiles 1, 2, 3 drop into both in order; a "?" pulses at each exit | |
| 2 | HALF WRONG | *1* first from both? Half wrong | A "1?" bubble pops up at both exits; the queue's turns green, the stack's turns red with a cross | |
| 3 | STACK: ONE END | Add on *top*, take from the *top* | Zoom on the stack: 1 at the bottom, 2, then 3 on top; one TOP arrow marks both "in" and "out" | `stack = [1, 2, 3]  # top: 3` |
| 4 | LAST IN, FIRST OUT | *3* came in last, leaves *first* | Tile 3 lifts out of the top into the stack's OUT slot; the TOP arrow moves down to 2 | `stack.pop()  # 3` |
| 5 | QUEUE: TWO ENDS | Join at the *back*, leave from the *front* | Zoom on the queue: 1 at the FRONT (left), 3 at the BACK (right); "in" arrow at the back, "out" arrow at the front | `queue = deque([1, 2, 3])` |
| 6 | FIRST IN, FIRST OUT | *1* came in first, leaves *first* | Tile 1 slides out of the front into the queue's OUT slot; the FRONT arrow moves to 2 | `queue.popleft()  # 1` |
| 7 | NEWEST OR OLDEST? | Newest first? *Stack*. Oldest? *Queue*. | Both OUT slots side by side (stack: 3, queue: 1); payoff card "Newest first: STACK · Oldest first: QUEUE" and @yourhandle, mid-frame | |

### Hook options
1. स्टैक और क्यू में एक, दो, तीन डालो। पहले कौन सा निकलेगा? (recommended)
2. स्टैक उल्टा लौटाता है, क्यू सीधा। एक, दो, तीन से देखो।
3. स्टैक और क्यू, दोनों से पहले एक? यहीं गलती होती है।

### Cheat sheet
- Use when: Newest first (undo, matching brackets): stack · Oldest first (print jobs, tasks in arrival order): queue · Graph search: DFS uses a stack, BFS a queue
- Trade-offs: Only the top (stack) or front (queue) is reachable · In a stack the oldest item waits longest · Python `list.pop(0)` shifts all remaining items (O(n)): use `deque`
- Snippet:
```python
from collections import deque
stack, queue = [], deque()
for x in (1, 2, 3):
    stack.append(x)   # add on top
    queue.append(x)   # join at the back
print(stack.pop(), queue.popleft())  # 3 1
```
- Comparison:

| Python approach | Out first (in: 1, 2, 3) | Add | Remove |
|---|---|---|---|
| List as queue: `pop(0)` | 1 | O(1) | O(n) |
| Stack: list `append`, `pop()` | 3 | O(1) | O(1) |
| Queue: `deque` `append`, `popleft()` | 1 | O(1) | O(1) |

### Caption
Same three numbers, two different answers.

Put 1, 2, 3 into a stack and take one out: you get 3. A stack adds and removes at the top, so the last one in is the first one out. Do the same with a queue and you get 1. A queue adds at the back and removes from the front, so the first one in is the first one out.

Rule of thumb: need the newest item first, like undo? Stack. Need the oldest first, like print jobs waiting in line? Queue.

Python tip: a list works fine as a stack, but use collections.deque for a queue, because list.pop(0) shifts all the remaining items.

Which one did you guess would come out first? Tell me in the comments.

#stackvsqueue #datastructures #dsa #dsainhindi #python

### Claims checked
- Push 1, 2, 3 then take one: stack gives 3, queue gives 1; draining gives 3, 2, 1 vs 1, 2, 3 (beats 1-6, hook 2, caption): ran it in Python 3.13.
- "1 first from both? Half wrong" (beat 2): follows from the run above (right for the queue, wrong for the stack).
- Stack adds and removes at the same end; queue adds at the back, removes at the front (beats 3, 5, headings): standard definitions (own knowledge, stable); the Python mapping checked with the shipped docstrings (`list.pop`: "default last"; `deque.append`: "right side"; `deque.popleft`: "leftmost").
- On-screen code lines (beats 3-6) give the narrated values (top 3, pop 3, front 1, popleft 1): ran them in order.
- Snippet prints `3 1`: ran it.
- `list.pop(0)` is O(n), `list.pop()` and `deque.popleft()` O(1), appends O(1) (list append amortized): timed 1000 removals at n = 10k / 100k / 1M: `pop(0)` 1.6 / 14.9 / 361 ms, `popleft()` 0.03-0.05 ms, `pop()` 0.03-0.05 ms; matches the Python docs on `deque` (own knowledge of the docs, not fetched).
- Undo removes the newest change first, brackets are matched with a stack, DFS uses a stack and BFS a queue, print jobs wait in arrival order by default: own knowledge (stable CS facts).
- Length: 59 spoken words, under the 60-word cap for non-English TTS: counted by the checker.

### Unverified
- Real spoken length with the user's Hindi TTS voice (the checker's ~26 s assumes 2.3 words per second; not measured with an actual voice).

### Validation
`python3 scripts/check.py reel-scripts/2026-10-30-stack-vs-queue.md --max-words 60 --wps 2.3`

```text
PASS: Stack vs Queue (7 beats, 59 words, ~26 s)
  WARN  beat 1: the topic name isn't in the first 6 words
  WARN  last beat has no CTA (follow / subscribe / save)
```

Both WARNs were read and are false positives from the Devanagari narration: "स्टैक और क्यू" (stack and queue) are words 1-3 of beat 1, and "फॉलो करो" (follow) is the CTA, but the checker matches only Latin "stack"/"queue" and English CTA verbs. The checker can't see Hindi absolutes either; checked by hand: no हमेशा / कभी नहीं / सब in the narration.

TTS note: the handle is spoken as "योरहैंडल" so the Hindi voice reads it as a word; it is shown on screen as @yourhandle. Replace both with the real handle.
