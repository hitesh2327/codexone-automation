## Deadlock: Two Threads, Two Locks
Category: OS · Platform: tiktok · Format: animated · Audience: intermediate

### Voice-over
1. A deadlock takes just two threads and two locks.
2. Thread one grabs lock A. Thread two grabs lock B.
3. Now thread one waits for B, which thread two holds.
4. Thread two waits for A. Neither can move: a circular wait.
5. Fix it with one global order: lock A first, then B.
6. Now thread two waits for A while holding nothing, so no cycle forms.
7. Order your locks. Follow @yourhandle for more OS deep dives.

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | DEADLOCK | Two threads, two *locks* | Two thread boxes and two lock icons, mid-frame | |
| 2 | GRAB ONE EACH | T1 holds *A*, T2 holds *B* | Each thread turns green with its lock attached | `lock_a.acquire()` |
| 3 | WAIT FOR B | T1 waits on *B* | T1 turns amber; arrow from T1 to lock B | `lock_b.acquire()  # blocks` |
| 4 | CIRCULAR WAIT | Each waits on the *other* | T2 amber; the two arrows form a red cycle | |
| 5 | ONE LOCK ORDER | Always *A*, then *B* | Both threads re-drawn; the order A -> B shown on each | `with lock_a, lock_b:` |
| 6 | NO CYCLE | T2 waits, holding *nothing* | T1 takes A and B, finishes, releases; T2 proceeds | |
| 7 | ORDER YOUR LOCKS | One order, *no* cycle | Payoff card "Same order everywhere. No circular wait." | |

### Hook options
1. A deadlock takes just two threads and two locks. (recommended)
2. Why does your program freeze with no error at all?
3. Two threads, two locks, and nothing ever finishes.

### Cheat sheet
- Use when: Several locks per operation · Threads share resources · Freezes without errors
- Trade-offs: Order must be global · Hard to retrofit · Timeouts only hide it
- Snippet:
```python
import threading
lock_a, lock_b = threading.Lock(), threading.Lock()
def transfer():
    with lock_a:      # one global order:
        with lock_b:  # A first, then B
            pass      # critical section
```
- Comparison:

| Approach | Prevents deadlock | Cost | Notes |
|---|---|---|---|
| Lock timeouts | No, breaks it after a wait | Retry logic | Can livelock |
| Single big lock | Yes | No parallelism | Simple |
| Global lock order | Yes | Discipline | Breaks circular wait |

### Caption
Two threads, two locks, opposite order: each holds one and waits for the other. Fix it with one global lock order. Where have you seen a freeze like this?

#operatingsystems #concurrency #multithreading #programming

### Claims checked
- Opposite lock order produces a circular wait: ran two Python threads with a barrier and timeouts;
  one thread could not acquire its second lock.
- A single global order completes: ran the snippet's pattern with two threads; both finished.
- `with lock_a, lock_b:` acquires `lock_a` then `lock_b` (Python `with` statement semantics).
- Circular wait is one of the four conditions for deadlock (Coffman conditions); removing it prevents
  deadlock.

### Unverified
- none

### Validation
PASS
