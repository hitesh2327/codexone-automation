## BFS vs DFS
Category: DSA · Platform: youtube · Format: animated · Audience: intermediate

### Voice-over
1. BFS or DFS: which finds the shortest path to D?
2. DFS dives: A, C, F, E, B, then D. Five hops.
3. Its stack pops the newest node, so it goes deep first.
4. BFS pops the oldest node from a queue: level by level.
5. Level one: B and C, one hop each.
6. Level two: D, just two hops from A.
7. Nearest first, so BFS finds the fewest hops. Follow @yourhandle for more DSA.

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | BFS VS DFS | Shortest path from *A* to *D*? | Six nodes draw in mid-frame: A on top; B, C below; D, E, F at the bottom; edges A-B, A-C, B-D, B-E, C-F, E-F. A glows (START), D gets a target ring (GOAL) | |
| 2 | DFS DIVES | A→C→F→E→B→D: *5* hops | Orange trail runs A→C→F→E→B→D; HOPS counter ticks 1 to 5; D flashes orange | |
| 3 | STACK: NEWEST FIRST | Last in, first out: *C* pops first | Rewind to A: STACK column (mid-left, clear of the right-side buttons) gets B, then C on top; C pops off and lights up | `v = stack.pop()` |
| 4 | QUEUE: OLDEST FIRST | First in, first out: *B* goes first | Trail fades; QUEUE row (mid-frame, above the bottom 20%) holds B, C; B leaves the front; D, E join the back | `v = queue.popleft()` |
| 5 | LEVEL ONE | B and C: *1* hop each | C leaves the front, F joins; B and C turn blue with a "1" badge; QUEUE now shows D, E, F | `dist[w] = dist[v] + 1` |
| 6 | LEVEL TWO | Level 2: *D* in *2* hops | D leaves the front, turns green with a "2" badge; path A→B→D glows; HOPS = 2 | `dist["D"]  # 2` |
| 7 | NEAREST FIRST | Queue order = *distance* order | Payoff card mid-frame: "DFS: 5 hops" (orange) above "BFS: 2 hops" (green); handle under it | |

### Hook options
1. BFS or DFS: which finds the shortest path to D? (recommended)
2. DFS took five hops to reach D. BFS took two.
3. Using DFS to find shortest paths? It can take the long way.

### Cheat sheet
- Use when: Fewest hops in an unweighted graph (BFS) · Nearest first, like friends of friends (BFS) · Cycle checks, topological sort, backtracking (DFS)
- Trade-offs: BFS's queue can hold a whole level · DFS's path depends on neighbour order · Weighted edges need Dijkstra, not BFS
- Snippet:
```python
from collections import deque
dist, q = {"A": 0}, deque(["A"])
while q:
    v = q.popleft()
    for w in g[v]:
        if w not in dist: dist[w] = dist[v] + 1; q.append(w)
```
- Comparison:

| Approach | Time | Extra space | Fewest hops? |
|---|---|---|---|
| DFS (stack) | O(V + E) | O(V) | Not guaranteed |
| BFS (queue) | O(V + E) | O(V) | Yes |

### Caption
Title: BFS vs DFS: which finds the shortest path? #Shorts

DFS follows its stack down one path and reaches D after five hops; BFS takes nodes from a queue level by level
and reaches it in two. In an unweighted graph, BFS gives the fewest hops; DFS fits cycle checks and backtracking.

#dsa #algorithms

### Claims checked
- Graph = edges A-B, A-C, B-D, B-E, C-F, E-F, neighbours in alphabetical order; every order, path and counter below comes from running BFS/DFS on exactly this adjacency list.
- DFS visits A, C, F, E, B, D and its path to D is A-C-F-E-B-D, 5 hops (beats 2-3, hook 2, payoff card): ran an iterative DFS (push neighbours in list order, pop the newest, skip visited on pop) with parent tracking; a recursive DFS with reversed neighbour order gives the same order and parents.
- Stack after A holds B, C and `stack.pop()` returns C; `queue.popleft()` on B, C returns B (beats 3-4): ran both.
- BFS pops A, B, C, D, E, F; queue goes B, C -> C, D, E -> D, E, F (beats 4-6): ran a traced BFS.
- B and C are 1 hop, D is 2 hops via A-B-D; level two is D, E, F (beats 5-6, `dist["D"]  # 2`): ran the cheat-sheet snippet as written, which prints dist A0 B1 C1 D2 E2 F2.
- Only two simple paths A->D exist (2 and 5 hops), so 2 is the minimum: enumerated all simple paths.
- "BFS finds the fewest hops" / "Queue order = distance order": standard BFS theorem (own knowledge, stable fact), plus 3,000 random graphs where BFS distances matched a brute-force level expansion with 0 mismatches.
- The stack loop is a real DFS (not just "BFS with a stack"): on the same 3,000 random graphs its order matched a recursive DFS with reversed neighbours, 0 mismatches.
- "DFS's path depends on neighbour order" (trade-off, hook 3 "can"): ran a recursive DFS in list order, which goes A, B, D, E, F, C and reaches D in 2 hops.
- "BFS's queue can hold a whole level": the traced queue holds D, E, F, all of level two.
- "Weighted edges need Dijkstra, not BFS": ran a 4-node weighted counterexample where BFS's 1-hop path costs 10 and Dijkstra finds cost 3 over 3 hops.
- O(V + E) time and O(V) extra space for both, with adjacency lists; DFS fits cycle checks, topological sort and backtracking; BFS fits nearest-first search: own knowledge (stable textbook facts).
- Snippet: 6 lines, longest 60 characters, ran it; shot-list code lines are lines of these real programs.

### Unverified
- none

### Validation
PASS: BFS vs DFS (7 beats, 72 words, ~27 s) (`python3 scripts/check.py reel-scripts/2026-10-30-bfs-vs-dfs.md`)

Not done: an independent review by a fresh session (sub-agents not available here).
