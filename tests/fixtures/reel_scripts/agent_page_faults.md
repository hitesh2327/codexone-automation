## Virtual Memory: Page Faults on First Write
Category: OS · Platform: youtube · Format: animated · Audience: senior

### Voice-over
1. Virtual memory fact: a one-gibibyte malloc barely moves your RSS.
2. That's address space. Frames arrive later, page by page.
3. First write: the MMU finds no page-table entry and traps.
4. The kernel maps a zeroed frame, then retries the write.
5. Four-K pages: one gibibyte is over a quarter million faults.
6. That lands on whatever writes first, maybe a live request.
7. MAP_POPULATE prefaults at mmap time: same work, paid early. Follow @yourhandle for OS internals.

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | VIRTUAL MEMORY | VSZ *+1 GiB*, RSS barely moves | Process box with two bars: VSZ jumps by 1 GiB, RSS stays flat (+4 KiB). Small label "Linux 6.18, x86-64, glibc". All text mid-frame, clear of the bottom 20% and right 15% | `char *p = malloc(1UL << 30);` |
| 2 | ADDRESS SPACE ONLY | 262,144 pages, frames *on demand* | Zoom into the 1 GiB range: a grid of page-table entries, all grey "not present"; the RAM panel on the left stays empty | |
| 3 | PAGE FAULT | No PTE, so the MMU *traps* | A write pointer hits page 0; its PTE cell flashes red; arrow from the CPU box to a "kernel" box | `memset(p, 1, 1UL << 30);` |
| 4 | KERNEL MAPS IT | Zeroed frame, PTE set, *retry* | Kernel takes a frame from the free list, fills it with 0s, the PTE turns green and points to it; arrow back to the CPU, the write completes | |
| 5 | 262,144 FAULTS | 1 GiB / 4 KiB = *262,144* | The grid fills page by page while a "minor faults" counter spins to 262,144; source tag "getrusage ru_minflt" | `getrusage(RUSAGE_SELF, &ru);` |
| 6 | FIRST WRITER PAYS | The *first* pass pays for the faults | A request arrow hits the service while the grid is still filling; its latency bar spikes. Second pass: counter stays at 0, bar flat | |
| 7 | PREFAULT EARLY | MAP_POPULATE: same work, *at mmap* | Rewind: the counter fills during startup's mmap; the request path stays flat. Follow card mid-frame | `flags \|= MAP_POPULATE;` |

### Hook options
1. Virtual memory fact: a 1 GiB malloc barely moves your RSS. (recommended)
2. Page faults: why is your first pass over memory slower?
3. Virtual memory mistake: assuming malloc means the RAM is yours.

### Cheat sheet
- Use when: Latency-critical buffers (prefault them) · Reading RSS vs VSZ on dashboards · Sizing memory when the kernel overcommits
- Trade-offs: Prefaulting slows startup and commits RAM up front · Huge pages cut faults but can raise memory use · Overcommit lets malloc succeed, so a later write can meet the OOM killer
- Snippet:
```python
from mmap import mmap, MAP_PRIVATE, PAGESIZE
from resource import getrusage, RUSAGE_SELF
m = mmap(-1, 1 << 30, MAP_PRIVATE)  # 1 GiB, nothing touched
f0 = getrusage(RUSAGE_SELF).ru_minflt
for i in range(0, 1 << 30, PAGESIZE): m[i] = 1
print(getrusage(RUSAGE_SELF).ru_minflt - f0)  # ~262144
```
- Comparison:

| Mapping | Faults for 1 GiB | Paid when | Catch |
|---|---|---|---|
| MAP_POPULATE | 262,144 | At mmap | Slower start, RAM committed |
| 2 MiB pages (MADV_HUGEPAGE) | 512 | First write | Can raise memory use |
| 4 KiB, lazy (demand paging) | 262,144 | First write | Lands in the hot path |

### Caption
Title: Virtual memory and page faults: where a 1 GiB malloc really pays #Shorts

malloc reserves address space; RAM arrives one 4 KiB page at a time, through a minor page fault on the first write.
Measured on Linux 6.18 x86-64 with getrusage: 262,144 faults for 1 GiB, 512 with MADV_HUGEPAGE, and MAP_POPULATE moves them to mmap time.

#linux #operatingsystems

### Claims checked
- A 1 GiB `malloc` barely moves RSS: ran a C program (glibc, Linux 6.18.44, x86-64); RSS (from /proc/self/statm) grew by 4 KiB after `malloc(1UL << 30)`, about 1 GiB after the first `memset`.
- Pages are mapped lazily, and the first write to each 4 KiB page is one minor fault: `memset` over 1 GiB added 262,146 minor faults (getrusage `ru_minflt`; 262,144 plus 2 from stdio), a second `memset` added 0. The Python snippet printed exactly 262144 on two runs.
- 4 KiB page size: `getconf PAGESIZE` printed 4096; 2^30 / 2^12 = 262,144, "over a quarter million".
- The new frame is zero-filled: reading untouched bytes of the fresh 1 GiB block returned 0. (The MMU trap, the kernel finding the VMA, installing the PTE and retrying the instruction: own knowledge of x86-64/Linux fault handling, stable.)
- The cost lands on the first writer: first `memset` took 1.3-5.3 s, the second 0.2 s on this VM (timings vary, so no number is shown on screen).
- `MAP_POPULATE` moves the faults to mmap time: mmap with `MAP_POPULATE` added 262,152 minor faults and RSS +1 GiB at the call; the following `memset` added 2.
- 512 faults with 2 MiB pages: `madvise(MADV_HUGEPAGE)` on the 1 GiB mapping, then `memset`: 514 minor faults (512 plus 2); 2^30 / 2^21 = 512. THP on this machine is `madvise`; `MADV_NOHUGEPAGE` gave 262,146.
- Overcommit: with `vm.overcommit_memory = 0`, three untouched 12 GiB mmaps (36 GiB) succeeded on a 16 GB box with no swap; a single 40 GiB mmap was refused.
- The Python snippet runs on Python 3.13 (`mmap(-1, ...)` adds MAP_ANONYMOUS itself) and prints 262144.
- `char *p = malloc(1UL << 30);`, `memset(p, 1, 1UL << 30);`, `getrusage(RUSAGE_SELF, &ru);` and `flags |= MAP_POPULATE;` are lines from the C test program (compiled with gcc and run).

### Unverified
- "Huge pages can raise memory use" and "a later write can meet the OOM killer": own knowledge of Linux THP and overcommit behaviour (not triggered here, to avoid killing processes on this machine).
- On systems with THP set to `always`, the default lazy mapping may take about 512 faults instead of 262,144; only `madvise` mode was tested here.

### Validation
PASS: Virtual Memory: Page Faults on First Write (7 beats, 73 words, ~27 s)
(`python3 scripts/check.py reel-scripts/2026-10-30-virtual-memory-page-faults.md`; the first run's only WARN, the absolute word "every" in beat 6's caption, was reworded.)
