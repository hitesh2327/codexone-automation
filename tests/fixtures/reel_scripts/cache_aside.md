## Cache-Aside Pattern
Category: System Design · Platform: instagram · Format: animated · Audience: beginner

### Voice-over
1. Cache-aside is how apps make repeat reads fast.
2. No cache? Each read waits on the database, about fifty milliseconds.
3. First, check the cache, a fast in-memory store. Not there? A miss.
4. On a miss, read the database and save the result in the cache.
5. The next read hits the cache: about one millisecond.
6. When data changes, update the database and delete the cached copy.
7. Fewer database reads. Follow @yourhandle for more system design.

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | CACHE-ASIDE | Make repeat reads *fast* | App, cache and database boxes; requests flow from the top, mid-frame | |
| 2 | NO CACHE | Each read waits on the *database* | Requests go straight to the DB; LATENCY counter shows 50 ms | |
| 3 | CHECK THE CACHE | *Miss*: the key isn't there | Request goes to the cache first; cache box flashes "MISS" | `redis-cli GET user:42` |
| 4 | MISS: READ THE DB | Load it, then *cache* it | Arrow app -> DB, then app -> cache; key appears in the cache | `redis-cli SET user:42 ada EX 300` |
| 5 | HIT: FAST PATH | Served from *memory* | Request stops at the cache, flashes "HIT"; LATENCY drops to 1 ms | `redis-cli GET user:42` |
| 6 | INVALIDATE ON WRITE | Update the DB, *delete* the key | Write arrow to DB; cache key fades out | `redis-cli DEL user:42` |
| 7 | FEWER DB READS | Cache-aside: *lazy* loading | Payoff card "Read the cache first. Load on a miss." | |

### Hook options
1. Cache-aside is how apps make repeat reads fast. (recommended)
2. Why does the second request load so much faster?
3. Your database is doing work a cache could skip.

### Cheat sheet
- Use when: Reads far outnumber writes · Slightly stale data is fine · A cache miss is safe
- Trade-offs: First read stays slow · Stale until TTL or delete · Two systems to keep in sync
- Snippet:
```python
def get_user(r, db, key):
    v = r.get(key)
    if v is None:
        v = db.load(key)       # your database call
        r.set(key, v, ex=300)  # cache it for 5 minutes
    return v
```
- Comparison:

| Pattern | Who fills the cache | Write path | Main risk |
|---|---|---|---|
| No cache | Nobody | Database only | Database load |
| Write-through | The cache layer | Cache, then database | Slower writes |
| Cache-aside | The app, on a miss | Database, then delete key | Brief staleness |

### Caption
Repeat reads don't have to wait on the database. With cache-aside, the app checks a fast in-memory cache
first; on a miss it reads the database and saves the result with an expiry, and when the data changes it
updates the database and deletes the cached copy. You get fewer database reads in exchange for data that
can be briefly stale. Where would you add a cache in your current project?

#systemdesign #redis #caching #backend #softwareengineering

### Claims checked
- `GET`, `SET key value EX seconds` and `DEL` are real Redis commands (Redis command reference).
- `r.set(key, v, ex=300)` is valid redis-py: `Redis.set` has an `ex` parameter (checked with `inspect`).
- The snippet's syntax: parsed with `ast.parse`.
- Delete-on-write is the usual cache-aside invalidation (cache-aside / lazy-loading descriptions in the
  Redis and AWS caching docs).

### Unverified
- 50 ms vs 1 ms are illustrative orders of magnitude for a disk-backed database vs an in-memory cache,
  not measurements.

### Validation
PASS
