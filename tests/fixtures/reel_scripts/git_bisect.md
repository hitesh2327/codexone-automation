## Git Bisect
Category: Dev & tools · Platform: tiktok · Format: screen · Audience: intermediate

### Voice-over
1. Git bisect finds the bad commit among sixty-four in six test runs.
2. Checking sixty-four commits one by one could take sixty-four test runs.
3. Mark one good commit and one bad commit.
4. Git checks out the middle commit. Run your test.
5. Tell git good or bad, and half the range disappears.
6. Six halvings later, git prints the first bad commit.
7. Bisect your next bug. Follow @yourhandle for more git tips.

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | GIT BISECT | Find the commit that *broke* it | Terminal: red failing test output, centered | |
| 2 | THE SLOW WAY | 64 commits, *64* test runs | Scrolling git log, counter of commits | `git log --oneline \| wc -l` |
| 3 | MARK GOOD AND BAD | One *good*, one *bad* | Typing the start command; tag v1.2.0 highlighted | `git bisect start HEAD v1.2.0` |
| 4 | TEST THE MIDDLE | Git picks the *middle* commit | "Bisecting: 31 revisions left" message zoomed | `npm test` |
| 5 | HALF IS GONE | Each answer *halves* the range | Typing good; the revisions-left number halves | `git bisect good` |
| 6 | FOUND IT | 6 steps, not *64* | "is the first bad commit" line highlighted | `git bisect reset` |
| 7 | BISECT IT | log2(64) = *6* steps | Command summary card, mid-frame | |

### Hook options
1. Git bisect finds the bad commit among sixty-four in six test runs. (recommended)
2. Still checking commits one by one to find a bug?
3. Sixty-four commits, one bug, six test runs with bisect

### Cheat sheet
- Use when: A test broke at some commit · Long history since it worked · The test is scriptable
- Trade-offs: Needs a reliable test · Flaky tests mislead it · Builds per step take time
- Snippet:
```bash
git bisect start HEAD v1.2.0
git bisect run npm test
git bisect reset
```
- Comparison:

| Approach | Test runs | Effort | Needs |
|---|---|---|---|
| Check each commit | Up to N | High | Patience |
| Guess from the log | Unknown | Medium | Luck |
| Git bisect | About log2(N) | Low | A good test |

### Caption
Git bisect binary-searches your history: mark a good and a bad commit, and it finds the first bad one in about log2(N) test runs. What's the worst bug you've hunted?

#git #debugging #programming #devtips

### Claims checked
- `git bisect start <bad> <good>` syntax: `git bisect -h` ("start ... [<bad> [<good>...]]").
- `git bisect run <cmd>`: exit 0 means good, 1-127 except 125 means bad (git-bisect documentation).
- 64 commits need 6 test runs: built a repo with 64 commits after the good tag and ran `git bisect run`
  once for each possible first bad commit (all 64): each run took 6 tests and named the right commit.
- "Bisecting: 31 revisions left": git's first message on that repo ("... left to test after this
  (roughly 5 steps)").

### Unverified
- none

### Validation
PASS
