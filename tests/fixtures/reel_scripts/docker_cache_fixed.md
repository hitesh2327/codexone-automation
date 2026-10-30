## Docker Layer Caching
Category: Dev & tools · Platform: instagram · Format: screen · Audience: intermediate

### Voice-over
1. Docker layer caching is why your Dockerfile's order matters.
2. Copy all your code first, and any edit reinstalls your dependencies.
3. Each instruction is a layer, reused while its inputs don't change.
4. Change one layer, and the layers after it rebuild too.
5. So copy the package files and install first, then copy your code.
6. Now a code edit reuses the cached install layer.
7. Least-changed layers first. Follow @yourhandle for more Docker.

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | LAYER CACHING | Order *matters* | Dockerfile in the editor, centered | |
| 2 | THE SLOW WAY | Any edit = full *reinstall* | Dockerfile with COPY . . above RUN npm ci; build log reruns npm ci | `COPY . .` |
| 3 | ONE LAYER EACH | Reused until inputs *change* | Build log: "CACHED" next to unchanged steps | `docker build -t app .` |
| 4 | THE CHAIN | One change rebuilds what's *after* | Steps below the changed line turn red in the log | |
| 5 | REORDER | Dependencies *first* | COPY package*.json and RUN npm ci moved above COPY . . | `COPY package*.json ./` |
| 6 | CACHED INSTALL | Code edit, *no* reinstall | Rebuild after a code edit: "CACHED" on RUN npm ci | `RUN npm ci` |
| 7 | ORDER BY CHANGE | Stable layers on *top* | Payoff card "Least-changed layers first." | |

### Hook options
1. Docker layer caching is why your Dockerfile's order matters. (recommended)
2. Why does one code edit reinstall all your dependencies?
3. Move two lines in your Dockerfile and builds speed up.

### Cheat sheet
- Use when: Builds reinstall dependencies · CI builds feel slow · Dockerfiles copy code early
- Trade-offs: Lockfile changes still reinstall · Needs a .dockerignore · Cache varies across CI runners
- Snippet:
```dockerfile
FROM node:20-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
CMD ["node", "server.js"]
```
- Comparison:

| Dockerfile order | Code edit rebuilds | Dependency change rebuilds | Verdict |
|---|---|---|---|
| COPY . . then install | Install and code | Install and code | Slow |
| No cache (--no-cache) | Everything | Everything | For clean builds |
| Manifests, install, then code | Code only | Install and code | Fast |

### Caption
Docker reuses each layer of your image until something it depends on changes, and when a layer changes,
every layer after it rebuilds too. That's why copying your whole project before installing dependencies
makes every code edit reinstall them. Copy the package files, install, then copy the rest, and a code
edit reuses the cached install layer. What's the slowest step in your Docker build?

#docker #devops #dockerfile #nodejs #buildperformance

### Claims checked
- Layers are reused until their inputs change, and a changed layer rebuilds every later one: built both
  Dockerfile orders twice with Docker 29.9 (BuildKit). With `COPY . .` first, a code edit re-ran the
  install step; with the package file first, the install step stayed `CACHED`; a dependency change
  re-ran the install step and the `COPY . .` after it.
- The `COPY` cache follows file contents, not timestamps: touching the files without editing them left
  every step `CACHED`.
- `docker build` has no `--cache=true` flag: `docker build --cache=true .` fails with "unknown flag:
  --cache"; `docker build --help` lists `--no-cache` (caching is on by default).

### Unverified
- `npm ci` itself wasn't run: the `node:20-slim` image couldn't be pulled (Docker Hub answered 429), so
  the build test used a shell step in place of the install. The caching rules don't depend on the command.

### Validation
PASS

### Changes
- Cut from 90 words (about 33 s) to 70 (about 26 s), so it fits under 30 seconds.
- Removed the greeting ("Hey guys! Today I'm going to show you"): the hook now names the topic in the first
  words.
- Removed `docker build --cache=true`: it isn't a docker build flag. Caching is on by default;
  `--no-cache` disables it.
- Replaced "always rebuilds everything ... 100% of the time" with what actually rebuilds (the changed
  layer and the ones after it).
- Turned the advice around: `COPY . .` before `npm install` is the cause of the slow builds, not the fix.
- Replaced "builds become instant" and "save you hours every day" (absolute, unmeasured) with the
  mechanism (the install layer is reused).
- Moved the CTA to the last beat only and dropped "like and subscribe" (a YouTube phrase; on Instagram,
  people follow).
- Added a worked example and a shot list for a screen recording.
