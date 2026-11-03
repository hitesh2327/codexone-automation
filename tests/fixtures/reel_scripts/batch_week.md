# Week plan

1. Exponential Backoff: delays that double, plus jitter
2. Process vs Thread: who shares memory

## Exponential Backoff
Category: System Design · Platform: instagram · Format: animated · Audience: intermediate

### Voice-over
1. Exponential backoff stops your retries from making an outage worse.
2. A server says 429, too many requests. Retrying immediately adds load.
3. Instead, wait one second, then two, then four, doubling each time.
4. Add random jitter so thousands of clients don't retry together.
5. If the response has a Retry-After header, wait that long.
6. Cap the delay and the retries, then fail cleanly.
7. Back off, don't pile on. Follow @yourhandle for more backend tips.

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | EXPONENTIAL BACKOFF | Retries that don't *pile on* | Clients on top, one server below, mid-frame | |
| 2 | 429 | Instant retries add *load* | Server turns red; a burst of retry arrows hits it | |
| 3 | DOUBLE THE WAIT | 1 s, 2 s, *4 s* | A timeline with gaps doubling | `delay = base * 2 ** n` |
| 4 | ADD JITTER | Spread the *retries* | Retry arrows scatter across the timeline | `random.uniform(0, delay)` |
| 5 | RETRY-AFTER | The server says *when* | Response header box appears on the arrow | `Retry-After: 120` |
| 6 | CAP IT | Max delay, max *tries* | The timeline stops after 5 attempts | `if n == tries - 1: raise` |
| 7 | BACK OFF | Wait more, *retry less* | Payoff card "Double, jitter, cap." | |

### Hook options
1. Exponential backoff stops retries from making an outage worse. (recommended)
2. Your retry loop might be the thing taking the server down.
3. Retrying instantly after a 429 is the wrong move.

### Cheat sheet
- Use when: Rate limits (429) · Flaky network calls · Overloaded services (503)
- Trade-offs: Slower recovery · Needs a retry cap · Only for safe-to-retry requests
- Snippet:
```python
def retry(call, tries=5, base=1.0, cap=30.0):
    for n in range(tries):
        try: return call()
        except RateLimited:
            if n == tries - 1: raise
        time.sleep(random.uniform(0, min(cap, base * 2**n)))
```
- Comparison:

| Strategy | Wait between tries | Load on server | Risk |
|---|---|---|---|
| Immediate retry | None | High | Makes outages worse |
| Fixed delay | Same each time | Medium | Clients retry in sync |
| Exponential + jitter | Doubling, randomised | Low | Slower to recover |

### Caption
When a server answers 429 Too Many Requests, retrying straight away only adds to the overload. Exponential
backoff waits longer after each failure, doubling the delay, and random jitter spreads clients out so they
don't all retry at the same moment. Respect a Retry-After header when the server sends one, cap the delay
and the number of attempts, and only retry requests that are safe to repeat. How does your app handle a
429 today?

#systemdesign #backend #api #reliability #softwareengineering

### Claims checked
- 429 Too Many Requests may include a Retry-After header: RFC 6585, section 4.
- The snippet retries with full jitter and gives up after `tries`: ran it with a fake call that fails
  twice, then succeeds (3 calls, 2 sleeps within 0-1 s and 0-2 s), and with one that always fails (the
  error is re-raised after 5 calls, with no sleep after the last). Needs `import random, time` and your
  client's rate-limit exception as `RateLimited`.
- "Full jitter" (a random wait between 0 and the backoff delay) is the AWS Architecture Blog's name for
  this variant.

### Unverified
- none

### Validation
PASS

## Process vs Thread
Category: OS · Platform: tiktok · Format: animated · Audience: beginner

### Voice-over
1. Process versus thread: the difference is who shares memory.
2. A process is a running program with its own memory.
3. A thread runs inside a process and shares that memory.
4. Two processes can't see each other's memory by default.
5. Two threads can, so they need locks around shared data.
6. A bad memory access, a segfault, in one thread kills the whole process.
7. Isolation or sharing: pick per job. Follow @yourhandle for more OS.

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | PROCESS VS THREAD | Who shares *memory*? | Two boxes labelled PROCESS and THREAD, mid-frame | |
| 2 | PROCESS | A program with its *own* memory | A process box with a private memory block | `os.getpid()` |
| 3 | THREAD | Lives inside, *shares* memory | Two threads inside one process, one memory block | `threading.Thread(target=f)` |
| 4 | ISOLATED | Separate *address spaces* | Two process boxes, a wall between their memory | |
| 5 | SHARED | Shared data needs *locks* | Two threads reach for one variable; a lock icon appears | `with lock:` |
| 6 | ONE CRASH | A segfault takes the *process* | One thread flashes red; the whole process box goes dark | |
| 7 | PICK PER JOB | Isolation or *speed*? | Payoff card "Processes isolate. Threads share." | |

### Hook options
1. Process versus thread: the difference is who shares memory. (recommended)
2. Why can one thread crash your entire program?
3. Processes and threads, explained with one memory box

### Cheat sheet
- Use when: Choosing parallelism · Debugging shared-state bugs · Explaining crashes
- Trade-offs: Threads need locks · Processes cost more memory · IPC is slower than sharing
- Snippet:
```python
import threading
hits = []
t = threading.Thread(target=hits.append, args=(1,))
t.start(); t.join()
print(hits)  # [1]: the thread shared hits
```
- Comparison:

| Unit | Memory | Crash impact | Communication |
|---|---|---|---|
| Process | Own address space | Usually contained | IPC (pipes, sockets) |
| Thread | Shared with its process | Can take down the process | Shared variables |

### Caption
A process is a running program with its own memory; threads live inside a process and share it. Sharing is fast but needs locks, and a segfault in one thread ends the whole process.

#operatingsystems #computerscience #programming #concurrency

### Claims checked
- Threads share their process's memory: ran the snippet; the thread's append is visible in the main
  thread (`[1]`).
- Separate processes have separate address spaces by default (shared memory must be set up explicitly).
- SIGSEGV's default action terminates the whole process, not one thread (POSIX signal semantics).

### Unverified
- none

### Validation
PASS
