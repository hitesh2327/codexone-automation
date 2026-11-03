## Hash Map Collisions: Chaining
Category: DSA · Platform: instagram · Format: animated · Audience: beginner

### Voice-over
1. Hash map collisions: two keys, one bucket. Who wins?
2. Keys go to numbered buckets by last digit: 42 and 72 both land in 2.
3. With no plan for collisions, 72 would erase 42.
4. Chaining fixes it: each bucket keeps a list.
5. 72 joins the list after 42.
6. To find 72, jump to bucket 2.
7. Walk the list: 42, no. 72, yes. Two checks.
8. Both stay, sharing one short list. Follow @yourhandle for more DSA.

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | HASH MAP COLLISIONS | Two keys, *one* bucket | Column of 10 buckets numbered 0-9, centred (clear of the bottom 20% and right 15%); keys "42 → Ana" and "72 → Ben" slide toward bucket 2 and bump | |
| 2 | LAST DIGIT PICKS | 42 and 72 both land in *2* | The last digit of each key lights up; labels "42 % 10 = 2" and "72 % 10 = 2"; both arrows point at bucket 2 | `bucket = key % 10` |
| 3 | NO COLLISION PLAN | *42* gets wiped out | Bucket 2 holds 42; 72 drops in and replaces it; 42 turns red and fades | `slots[2] = (72, "Ben")` |
| 4 | CHAINING | Each bucket keeps a *list* | Rewind: 42 comes back; bucket 2 grows a list whose first node is "42 → Ana" | `table = [[] for _ in range(10)]` |
| 5 | JOIN THE LIST | *72* joins right after 42 | Node "72 → Ben" attaches after 42; bucket 2 now shows 42 → 72 | `table[2].append((72, "Ben"))` |
| 6 | JUMP TO BUCKET 2 | Find *72*: go straight to 2 | Query "72?" appears; "72 % 10 = 2"; bucket 2 lights up, the other 9 dim | `chain = table[72 % 10]` |
| 7 | WALK THE LIST | 42? No. 72? *Yes* | Pointer on 42 (red ✗), moves to 72 (green ✓); CHECKS counter 1 → 2; "Ben" pops out | `if k == key: return v` |
| 8 | BOTH STAY | Same bucket, *shared* list | Payoff card "Collisions share a list. Nothing lost." mid-frame; follow prompt above the bottom 20% | |

### Hook options
1. Hash map collisions: two keys, one bucket. Who wins? (recommended)
2. With chaining, one hash map bucket can hold many keys.
3. Think hash map collisions overwrite your data? They don't.

### Cheat sheet
- Use when: Writing a hash map in an interview · Deletes are frequent · Keys may outnumber buckets
- Trade-offs: Extra memory for the lists · Bad hash, one long list: O(n) · Must grow the table to keep lists short
- Snippet:
```python
table = [[] for _ in range(10)]   # 10 empty buckets
def put(key, val):
    table[key % 10].append((key, val))  # new keys only
def get(key):
    for k, v in table[key % 10]:   # walk one bucket's list
        if k == key: return v
```
- Comparison:

| Approach | On collision | Lookup avg / worst | Memory |
|---|---|---|---|
| No collision plan | Old key lost | O(1) / O(1) | Table only |
| Linear probing | Try the next slot | O(1) / O(n) | Table only |
| Chaining | Add to the list | O(1) / O(n) | Table + lists |

### Caption
Two keys can land in the same bucket, and your hash map still keeps both.

Here's the trick, called chaining: each bucket holds a small list. In this example the last digit picks the bucket, so 42 and 72 both go to bucket 2. Instead of overwriting 42, the map adds 72 to the end of bucket 2's list. To find 72, it jumps straight to bucket 2 and checks only that list: 42, then 72. Two checks, not a scan of the whole map.

Real hash maps pick the bucket from a hash of the key, not its last digit, and grow the table as it fills so the lists stay short. Java's HashMap works this way.

What would you do if one bucket's list kept growing? Tell me in the comments.

#hashmap #hashtable #datastructures #dsa #codinginterview

### Claims checked
- 42 % 10 = 2 and 72 % 10 = 2, so both keys land in bucket 2: ran it in Python.
- With no collision handling, the second write replaces the first (slot 2 ends up holding only (72, "Ben")): ran it.
- With chaining, bucket 2 holds [(42, 'Ana'), (72, 'Ben')] and finding 72 takes 2 checks (42, then 72): ran the snippet with a comparison counter.
- Every line in the Code column is valid Python and does what the beat says; `[[] for _ in range(10)]` makes 10 separate lists (no aliasing): executed each line.
- Snippet runs: get(72) = 'Ben', get(42) = 'Ana', a missing key returns None; 25 keys in 10 buckets are all found ("keys may outnumber buckets"): ran it. Its `put` doesn't update an existing key, which the `# new keys only` comment says.
- Worst case O(n): 1,000 keys all ending in 2 make one list of 1,000, so the last key takes 1,000 checks: ran it. Average O(1): 750 random keys in 1,000 buckets average 1.33 checks per lookup: ran it. Big-O labels in the table are textbook results (own knowledge, stable).
- Linear probing "tries the next slot": a toy probe table put 72 in slot 3 after 42 took slot 2: ran it. "Deletes are frequent" favours chaining: in that table, naively emptying 42's slot made 72 unfindable, while chaining just removes one list item: ran it. Linear probing storing entries in the table only: own knowledge (stable definition).
- Java's HashMap chains (caption): in Java 21, reflection shows `HashMap$Node` has a `next` field; keys 42 and 58 share bucket 10 of 16 as 42 -> 58 (new key added at the end), and both are returned by get: ran it.
- "Grow the table as it fills": Java 21's HashMap went from 16 to 32 buckets at the 13th entry (16 × 0.75 = 12): ran it.
- Hook 3, "collisions don't overwrite your data": shown for the snippet and for Java's HashMap above.
- "Extra memory for the lists": own knowledge (each entry lives in a list or node outside the table).

### Unverified
- none

### Validation
PASS: Hash Map Collisions: Chaining (8 beats, 74 words, ~27 s) (`python3 scripts/check.py reel-scripts/2026-10-30-hash-map-chaining.md`)
