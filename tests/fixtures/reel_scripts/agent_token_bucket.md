## Token Bucket Rate Limiting
Category: System Design · Platform: youtube · Format: animated · Audience: intermediate

### Voice-over
1. How does a token bucket allow bursts but cap the rate?
2. A fixed window counter resets each minute: five before, five after. Ten in two seconds.
3. A token bucket holds five tokens. Each request spends one: five pass.
4. Nothing resets on the minute, so the next five get rejected.
5. Tokens drip back in, one every twelve seconds.
6. Bucket size caps bursts; refill rate caps the average. Follow @yourhandle for more system design.

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | TOKEN BUCKET | Limit: *5* requests per minute | Diagram mid-frame, clear of the bottom 20% and right 15%: CLIENT → LIMITER → API, with a timeline strip below (0:59, 1:00, 1:11) | |
| 2 | FIXED WINDOW | *10* requests in *2* seconds | LIMITER shows COUNT; five requests at 0:59 pass (COUNT 5/5), COUNT flips to 0/5 at 1:00, five more pass; PASSED: 10 turns red | |
| 3 | SPEND A TOKEN | Each request *spends* one token | Same picture: the counter morphs into a full bucket (TOKENS: 5); the 0:59 burst takes one token each: TOKENS 5 → 0, PASSED: 5 | `b.tokens -= 1` |
| 4 | NO RESET | Empty bucket: *429* Too Many Requests | Clock hits 1:00, bucket stays empty; five requests bounce back red with 429; REJECTED: 5 | `if b.tokens < 1: return False` |
| 5 | STEADY REFILL | *1* token per *12* seconds | Clock runs to 1:11; one token drips into the bucket: TOKENS 0 → 1 | `refill = (now - b.last) * b.rate` |
| 6 | BURST, THEN STEADY | Burst of *5*, then *5* per minute | Payoff card mid-frame: "Bucket size caps bursts. Refill rate caps the average." then the follow prompt | |

### Hook options
1. How does a token bucket allow bursts but cap the rate? (recommended)
2. A token bucket lets bursts through on purpose.
3. Rate limiting with a per-minute counter can let double through.

### Cheat sheet
- Use when: Bursty clients, capped average · Per-user or per-API-key limits · Throttling your own outbound calls
- Trade-offs: Backend must absorb a full burst · Two knobs: size and refill rate · Multi-server limits need shared state
- Snippet:
```python
def allow(b, now):  # b: cap, rate (tokens/s), tokens, last
    refill = (now - b.last) * b.rate
    b.tokens, b.last = min(b.cap, b.tokens + refill), now
    if b.tokens < 1: return False  # caller sends a 429
    b.tokens -= 1
    return True
```
- Comparison:

| Approach | Max burst | State per key | Quota comes back |
|---|---|---|---|
| Fixed window | 2× limit at edges | 1 counter | All at once, each window |
| Sliding log | The limit | 1 timestamp per request | As old requests age out |
| Token bucket | Bucket size | Tokens + last time | Steadily, at the refill rate |

### Caption
Title: Token bucket rate limiting: allow bursts, cap the average #Shorts

A fixed window counter can let 10 requests through a 5-per-minute limit in two seconds.
A token bucket holds 5 tokens; each request spends one, and one drips back each 12 seconds.
Bursts stop at 5, and the long-run average stays at or below 5 per minute.

#systemdesign #ratelimiting

### Claims checked
- Fixed window, 5 per minute: 5 requests at 0:59 and 5 at 1:00 all pass (10 within two seconds): simulated it.
- Token bucket (5 tokens, 5 per minute) on the same traffic: 5 pass at 0:59, all 5 rejected at 1:00 (0.083 tokens), first whole token back at 1:11: simulated it with exact fractions.
- 5 per minute = one token per 12 seconds: 60 / 5 = 12. "One every twelve seconds" (beat 5, checker WARN on 'every') is a refill rate, literally true: simulation gives the first whole token at exactly 12 s.
- "Bucket size caps bursts; refill rate caps the average": random-traffic simulation (300 runs) confirmed admitted requests in any span t never exceeded 5 + t/12. Note: over a 60 s span a full bucket can still admit 10, so the script claims the average, not a per-minute count.
- 2× limit at fixed-window edges, sliding log capped at the limit in any 60 s window: simulated both.
- 429 is "Too Many Requests": Python `http.HTTPStatus(429).phrase`.
- Snippet: ran it with cap=5, rate=5/60: True ×5 at t=59, False ×5 at t=60, True at t=71 (floats and exact fractions both). On-screen code lines are copied from it.
- State per key (counter / timestamps / token count + last time) and how quota comes back: by construction of each algorithm (own knowledge, stable).
- Use-when and trade-off bullets (bursty clients, per-key limits, outbound throttling, shared state across servers): own knowledge of how the algorithm is deployed; no numbers claimed.
- YouTube title under 100 characters, 3 hashtags including #Shorts: skill's platform notes.

### Unverified
- none

### Validation
PASS: Token Bucket Rate Limiting (6 beats, 72 words, ~27 s)
  WARN  absolute word 'every' (beat 5): make sure it is literally true (it is: a refill rate, see Claims checked)

(`python3 scripts/check.py reel-scripts/2026-10-30-token-bucket-rate-limiting.md`)
