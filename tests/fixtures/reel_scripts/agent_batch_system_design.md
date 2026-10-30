# System design reels: week of 2 November 2026

Plan (one mechanism, example and hook pattern per reel, no overlap):

1. Consistent Hashing (Mon 2 Nov): each key goes to the next server clockwise on a ring, so a new server takes keys only from its own arc. Example: 12 cached keys, 3 -> 4 servers. Hook: counter-intuitive fact.
2. Idempotency Keys (Wed 4 Nov): the server stores each result under the client's key, so a retry returns the stored result instead of charging again. Example: one $20 payment, a timeout, a retry. Hook: common mistake.
3. Token Bucket (Fri 6 Nov): requests spend tokens that refill at a fixed rate, so bursts are capped by the bucket size. Example: limit 10 a minute, 10 requests just before a minute boundary, 10 just after. Hook: question.

---

## Consistent Hashing
Category: System Design · Platform: instagram · Format: animated · Audience: intermediate

### Voice-over
1. Consistent hashing: add a server, move three keys, not nine.
2. Hash mod three spreads twelve keys over three cache servers.
3. Add server D: nine keys remap, so nine misses hit the database.
4. Instead, hash servers and keys onto one ring.
5. Each key walks clockwise to the next server.
6. Add server D: it takes three keys, all from its neighbor C.
7. Only the new server's arc moves. Follow @yourhandle for more system design.

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | CONSISTENT HASHING | Add a server, move *3* keys, not *9* | App box on top, cache servers A, B, C in a row, DB below; a ghost server D pulses beside them; title block mid-frame | |
| 2 | HASH MOD N | 12 keys, 3 servers: *h % 3* | Key chips 0-11 drop into A (0, 3, 6, 9), B (1, 4, 7, 10), C (2, 5, 8, 11) | `node = servers[h % 3]` |
| 3 | ADD SERVER D | *9* of 12 keys remap | D slides in; chips 3-11 jump to new servers and flash red, 0-2 stay; MOVED counter (mid-left, clear of the right 15%) 0 -> 9; DB bar spikes | `node = servers[h % 4]` |
| 4 | ONE RING | Servers and keys on *one* ring | D leaves; the same A, B, C and DB fold into a clock-like ring 0-11 with A at 3, B at 7, C at 11; the mod N result shrinks to a grey tag "mod N: 9 moved"; a new RING MOVED counter appears at 0 | `pos = [3, 7, 11]` |
| 5 | WALK CLOCKWISE | Next server *clockwise* owns it | Each key dot slides clockwise to its owner: A gets 0-3, B gets 4-7, C gets 8-11 | `bisect_left(pos, h) % len(pos)` |
| 6 | ADD D TO THE RING | D takes *3* keys, all from C | D lands at 10; keys 8, 9, 10 slide from C to D; the other 9 stay still; RING MOVED 0 -> 3; DB bar bumps slightly | `pos = [3, 7, 10, 11]` |
| 7 | ONLY ONE ARC MOVES | Only the *new arc* moves | D's arc glows; payoff card mid-frame: "mod N: 9 moved, ring: 3 moved"; follow prompt above the bottom 20% | |

### Hook options
1. Consistent hashing: add a server, move three keys, not nine. (recommended)
2. Why does consistent hashing barely move keys when servers join?
3. Hash mod N sharding? Consistent hashing avoids remapping most keys.

### Cheat sheet
- Use when: Sharding a cache across nodes · Partitioning keys in a distributed database · Sticky routing in a load balancer
- Trade-offs: Uneven arcs without virtual nodes · Lookup is O(log n), not O(1) · Clients must agree on the ring
- Snippet:
```python
import bisect, hashlib
def h(s): return hashlib.md5(s.encode()).digest()
ring = sorted((h(s), s) for s in ["A", "B", "C", "D"])
def owner(key):
    i = bisect.bisect(ring, (h(key),))
    return ring[i % len(ring)][1]
```
- Comparison:

| Approach | Keys moved, N to N+1 | Lookup | Load balance |
|---|---|---|---|
| Hash mod N | About N/(N+1) | O(1) | Even |
| Rendezvous hashing | About 1/(N+1) | O(N) | Even |
| Consistent hashing | About 1/(N+1) | O(log n) | Even with virtual nodes |

### Caption
Adding one cache server shouldn't flood your database.

With hash mod N, growing from 3 to 4 servers remaps about 3 in 4 keys, and each remapped key misses the cache on its next read and falls through to the database. Consistent hashing puts servers and keys on one ring and gives each key to the next server clockwise, so a new server only takes the keys in its own arc: about 1/(N+1) of them on average. Real systems add virtual nodes (many ring points per server) to even out the arcs.

Where have you used it: cache sharding, a Cassandra-style ring or a load balancer? Tell me below.

#consistenthashing #systemdesign #distributedsystems #caching #sharding

### Claims checked
- Hash mod 3 puts keys 0-11 on A (0, 3, 6, 9), B (1, 4, 7, 10), C (2, 5, 8, 11), and mod 4 moves 9 of 12 (keys 3-11): computed in Python.
- Ring with A=3, B=7, C=11: A owns 0-3, B 4-7, C 8-11; adding D=10 moves exactly keys 8, 9, 10, all from C: computed with `bisect_left` in Python.
- `bisect_left(pos, h)` returns the first position >= h, so `% len(pos)` wraps past the top of the ring: ran it against the example and against a brute-force "first server clockwise" check.
- Snippet: ran it; it matched the brute-force owner for 2,000 keys. With 4 servers and no virtual nodes it spread keys unevenly, which supports the "uneven arcs" trade-off.
- "About 3 in 4 keys" for mod N (3 to 4 servers), "about 1/(N+1)" for consistent hashing and rendezvous hashing: mod N computed exactly over 0-1199 (0.75); ring and rendezvous simulated with random positions (0.248 and 0.249 for N=3).
- Each remapped key misses the cache on its next read: follows from the cache-aside setup shown (the new owner has no copy).
- Lookup O(log n) (binary search over sorted ring points), rendezvous O(N) per key (score every server), mod N O(1): own knowledge, stable facts.
- Virtual nodes even out arcs; Cassandra places data on a token ring; consistent hashing is used for sticky routing in load balancers: own knowledge, stable facts (docs sites were blocked from this environment).

### Unverified
- none

### Validation
```text
PASS: Consistent Hashing (7 beats, 72 words, ~27 s)
PASS: Idempotency Keys (7 beats, 70 words, ~26 s)
PASS: Token Bucket (7 beats, 72 words, ~27 s)
  WARN  absolute word 'every' (beat 4, beat 4 caption, post caption): make sure it is literally true
3 scripts: 3 passed, 0 failed
```
(`python3 scripts/check.py reel-scripts/2026-10-30-batch.md`; the WARN is the Token Bucket refill rate, checked and kept.)

---

## Idempotency Keys
Category: System Design · Platform: instagram · Format: animated · Audience: intermediate

### Voice-over
1. Retrying payments without idempotency keys? That's how double charges happen.
2. A twenty dollar payment succeeds, but the client times out.
3. The client retries. The server charges again: forty dollars.
4. Replay with a unique key, reused on each retry.
5. First try: charge once, save the receipt under that key.
6. The retry finds the key: same receipt back, no second charge.
7. Retries become lookups, not charges. Follow @yourhandle for more system design.

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | IDEMPOTENCY KEYS | Retries without keys can charge *twice* | Phone (client) -> API -> payments DB in one row mid-frame; CHARGES counter shows 0 ($0) | |
| 2 | THE TIMEOUT | Charged, but the client *times out* | Request arrow reaches the API; card charged, CHARGES 0 -> 1 ($20); the reply arrow snaps at a red clock icon | `POST /payments HTTP/1.1` |
| 3 | THE RETRY | Same request, *second* charge | Client resends the same request; CHARGES 1 -> 2 ($40), flashing red | `POST /payments HTTP/1.1` |
| 4 | REPLAY WITH A KEY | One key per payment, *reused* | The no-key result shrinks to a grey tag "No key: $40"; a fresh run starts with a new CHARGES counter at 0; the request now carries a tag 5f2b9c1e | `Idempotency-Key: 5f2b9c1e` |
| 5 | STORE THE RESULT | Charge once, save under the key | CHARGES 0 -> 1 ($20); a KEY STORE box next to the API gets the row "5f2b9c1e: receipt"; the reply arrow snaps again | `receipts[key] = charge(amount)` |
| 6 | RETRY HITS THE KEY | Same key: *same* receipt back | The retry carries the same tag; the KEY STORE row lights up; the receipt flies back to the phone; CHARGES stays 1 | `return receipts[key]` |
| 7 | ONE KEY, ONE CHARGE | Retries become *lookups* | Payoff card mid-frame: "No key: $40" beside "Key: $20"; follow prompt above the bottom 20% | |

### Hook options
1. Retrying payments without idempotency keys? That's how double charges happen. (recommended)
2. Why do idempotency keys stop double charges on retries?
3. Idempotency keys exist because a timeout doesn't mean failure.

### Cheat sheet
- Use when: Payments, orders and bookings · Any POST a client may retry · Consumers of at-least-once queues or webhooks
- Trade-offs: Needs a shared store with a TTL · Concurrent duplicates need an atomic claim · Reject a reused key with a different body
- Snippet:
```python
receipts = {}  # shared store + TTL in production
def pay(key, amount, charge):
    if key not in receipts:
        receipts[key] = charge(amount)
    return receipts[key]
```
- Comparison:

| Approach | Double charge | Outcome after a timeout | Server state |
|---|---|---|---|
| Blind retry | Possible | Known after the retry | None |
| No retry | No | Unknown | None |
| Idempotency key | No, while the key is kept | Known after the retry | Key to result store |

### Caption
A timeout doesn't tell you whether the payment went through.

So a client that simply retries a POST can charge the same card twice. The fix is an idempotency key: the client creates one unique key per operation (a UUID works) and sends it in an Idempotency-Key header on the first try and on each retry. The server stores the result under that key, so a repeat gets the stored response instead of running the charge again. Keep keys for a limited time, and claim each key atomically so two simultaneous duplicates can't both run.

Which of your endpoints would double-charge, double-book or double-send if a client retried it?

#idempotency #apidesign #restapi #systemdesign #distributedsystems

### Claims checked
- A client timeout doesn't tell the client whether the server finished the charge: own knowledge, stable fact (the reply can be lost after the work is done).
- Charging $20 twice totals $40; with the key, one charge of $20: ran the snippet with a stub `charge` function; two calls with the same key charged once and returned the same receipt object.
- Snippet is real working code given any `charge` function: ran it.
- POST is not idempotent by default, so a blind retry can repeat its effect: own knowledge, stable fact (HTTP semantics).
- `Idempotency-Key` as the request header name: own knowledge; it is the name Stripe's API uses and the one in the IETF httpapi draft (no standard is claimed in the script).
- A dict is not safe for concurrent duplicates, so production needs an atomic claim (a unique row or Redis `SET ... NX`) and a TTL: own knowledge, stable facts.

### Unverified
- none

### Validation
```text
PASS: Consistent Hashing (7 beats, 72 words, ~27 s)
PASS: Idempotency Keys (7 beats, 70 words, ~26 s)
PASS: Token Bucket (7 beats, 72 words, ~27 s)
  WARN  absolute word 'every' (beat 4, beat 4 caption, post caption): make sure it is literally true
3 scripts: 3 passed, 0 failed
```
(`python3 scripts/check.py reel-scripts/2026-10-30-batch.md`; the WARN is the Token Bucket refill rate, checked and kept.)

---

## Token Bucket
Category: System Design · Platform: instagram · Format: animated · Audience: intermediate

### Voice-over
1. Why does a token bucket beat fixed window rate limits?
2. Fixed window: ten a minute. Ten arrive just before the reset.
3. The counter resets, ten more pass: twenty in two seconds.
4. Token bucket: holds ten, refills one every six seconds.
5. Same burst: ten requests spend all ten tokens.
6. A second later, no full token yet: all ten get 429s.
7. Size caps bursts; refill caps the rate. Follow @yourhandle for more system design.

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | TOKEN BUCKET | Token bucket vs *fixed window* | Clients -> rate limiter box -> API in one row mid-frame; a clock reads 0:58 | |
| 2 | FIXED WINDOW | *10* a minute, resets on the minute | Clock 0:59; 10 requests pass; the limiter's COUNT 0 -> 10; SERVED 0 -> 10 | `count[w] = count.get(w, 0) + 1` |
| 3 | THE RESET | *20* requests in 2 seconds | Clock 1:00; w goes 0 -> 1 and COUNT resets to 0; 10 more pass; SERVED 10 -> 20, flashing red; the API box shakes | `w = int(now // 60)` |
| 4 | ENTER THE BUCKET | Holds *10*, refills 1 every 6 s | The fixed-window result shrinks to a grey tag "Window: 20 in 2 s"; the limiter box becomes a bucket holding 10 tokens with a slow drip; a new SERVED counter appears at 0 | `tok = min(10, tok + dt / 6)` |
| 5 | SPEND A TOKEN | Each request spends *one* token | Clock back to 0:59; the same 10 requests each grab a token; TOKENS 10 -> 0; SERVED 0 -> 10 | `if tok >= 1: tok -= 1` |
| 6 | 429 TOO MANY | No full token yet: *429* | Clock 1:00; the bucket shows a one-sixth sliver; 10 more requests bounce off; REJECTED 0 -> 10; SERVED stays 10 | `HTTP/1.1 429 Too Many Requests` |
| 7 | SIZE AND RATE | Size caps bursts, refill caps rate | Payoff card mid-frame: "Window: 20 in 2 s" beside "Bucket: 10 in 2 s"; follow prompt above the bottom 20% | |

### Hook options
1. Why does a token bucket beat fixed window rate limits? (recommended)
2. A token bucket allows bursts and still caps your average rate.
3. Token bucket fixes the fixed window mistake: double bursts at reset.

### Cheat sheet
- Use when: APIs where short bursts are fine · Per-user or per-API-key quotas · Throttling calls to a paid upstream
- Trade-offs: Bursts up to the bucket size still reach the backend · Limits across servers need shared state · Two knobs to tune: size and refill rate
- Snippet:
```python
def allow(b, now, cap=10, rate=1 / 6):  # rate: tokens/s
    tok = min(cap, b["tok"] + (now - b["t"]) * rate)
    ok = tok >= 1
    b["tok"], b["t"] = tok - 1 if ok else tok, now
    return ok  # False: reply 429
b = {"tok": 10, "t": 0.0}; allow(b, 59.0)  # True
```
- Comparison:

| Algorithm | Most in any 2 s (10/min) | State per client | Trade-off |
|---|---|---|---|
| Fixed window | 20 | 1 counter | Spikes at each reset |
| Sliding window log | 10 | Up to 10 timestamps | Exact, more memory |
| Token bucket | 10 | Tokens + last refill time | Bursts up to bucket size |

### Caption
Your limit says 10 a minute. A fixed window can still pass 20 in two seconds.

Ten requests just before the reset and ten just after each fit their own window. A token bucket holds up to 10 tokens and refills at 10 a minute (one every six seconds). Each request spends a token, and when no full token is left the request gets 429 Too Many Requests. The bucket size caps bursts, the refill rate caps the average, and each client only needs two numbers: tokens and the last refill time.

What does your API gateway use today: fixed windows, sliding windows or a bucket?

#ratelimiting #tokenbucket #systemdesign #apigateway #backendengineering

### Claims checked
- Fixed window, limit 10 per calendar minute: 10 requests at 0:59 and 10 at 1:00 all pass (20 in 2 s): simulated in Python with `w = int(now // 60)` and a per-window counter.
- Token bucket (size 10, 1/6 token per second): 10 pass at 0:59, then 0 of 10 pass at 1:00 with 0.1667 tokens left: ran the snippet.
- Most requests in any 2 s: bucket 10, measured by running the snippet against a greedy client for 300 s; fixed window 20 (above); sliding window log 10 by definition (it allows at most 10 in any 60 s).
- Over 60 s the bucket allowed up to 19 in the same simulation, so the comparison uses "any 2 s", not "any minute", to compare like with like.
- `HTTP/1.1 429 Too Many Requests`: Python's `http.HTTPStatus(429).phrase` returns "Too Many Requests".
- Snippet is real working code: ran it (state is two numbers per client).
- Sliding window log stores up to 10 timestamps per client at 10/min: own knowledge, stable fact.
- "Refills one every six seconds" (checker WARN on 'every'): literally true as a rate; the snippet adds 1/6 token per second, which is one token per six seconds.

### Unverified
- none

### Validation
```text
PASS: Consistent Hashing (7 beats, 72 words, ~27 s)
PASS: Idempotency Keys (7 beats, 70 words, ~26 s)
PASS: Token Bucket (7 beats, 72 words, ~27 s)
  WARN  absolute word 'every' (beat 4, beat 4 caption, post caption): make sure it is literally true
3 scripts: 3 passed, 0 failed
```
(`python3 scripts/check.py reel-scripts/2026-10-30-batch.md`; the WARN is the Token Bucket refill rate, checked and kept.)
