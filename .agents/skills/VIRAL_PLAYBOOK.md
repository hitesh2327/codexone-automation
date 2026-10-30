# The CodeXone Viral Reel Playbook

> **The Definitive Blueprint for 10x-50x Reach on Instagram Reels**  
> Synthesizing all 13 Instagram Skills into an Automated, High-Velocity Distribution Engine.

---

## 1. The Core Algorithmic Truths (2025/2026 Distribution Engine)

Instagram does not distribute content based on production budget, complex editing, or hashtags. The recommendation algorithm (Explore & Reels Tab) optimizes for five specific behavioral metrics in exact order of priority:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. Average Percentage Viewed (APV > 100%)                                   │
│    Videos that seamlessly loop get 2x watch time credit. Single biggest     │
│    reach trigger. Achieved via tight 18–24s duration & Seamless Loop Bridge.│
├─────────────────────────────────────────────────────────────────────────────┤
│ 2. Sends / Shares per Reach (The #1 Direct Ranking Signal)                  │
│    Adam Mosseri confirmed DM sends are weighted 3x–5x higher than likes.    │
│    Every reel must contain a "Send this to your tech lead / study buddy"    │
│    relatable pain or high-utility cheat sheet.                              │
├─────────────────────────────────────────────────────────────────────────────┤
│ 3. 3-Second Scroll-Stop Rate (> 65% - 70% Hold Rate)                        │
│    70% of viewers scroll in the first 1.5 seconds. Beat 1 must combine:     │
│    a) Bold on-screen kinetic headline (<6 words)                            │
│    b) High-stakes spoken hook from outlier formula library                  │
│    c) Visual pattern interrupt (red failure state / flashing node alert)    │
├─────────────────────────────────────────────────────────────────────────────┤
│ 4. First-Hour Comment Velocity (Keyword Lead Magnet)                        │
│    Reels receiving 30+ comments in hour 1 trigger trending classification.  │
│    Replaced dead "Follow for more" CTAs with 1-word keyword DM triggers.    │
├─────────────────────────────────────────────────────────────────────────────┤
│ 5. Saves & Bookmarks (Durable Utility)                                      │
│    Dense architecture cheat sheets and comparison tables prompt saves,      │
│    telling the algorithm the video has long-term reference value.           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. The 5 Quality Gates (No Reel Ships Without Passing)

Every generated reel must pass all 5 gates before being rendered or queued:

```
[GATE 1: HOOK SCORE >= 70]
  Tool: python .agents/skills/ig-reel/scripts/hookscore.py --hook "<spoken_line>"
  Checks: Must speak in <3.0s, contain 1 concrete marker (number/tech term),
  deliver stakes at the front, and contain zero greetings ("Hey guys").

[GATE 2: SEAMLESS INFINITY LOOP]
  Tool: src/reel_v2/spec.py Review Pass
  Checks: The final beat MUST NOT say "Follow for more" or "Thanks for watching".
  The last spoken sentence must grammatically and logically connect directly
  back into Beat 1's opening hook line.

[GATE 3: 100% HUMAN / ZERO SLOP]
  Tool: python .agents/skills/ig-human/scripts/detect.py
  Checks: 0 em-dashes, 0 invisible unicode characters, 0 words from slop.json.
  Sentence variation and natural senior engineer conversational voice.

[GATE 4: SEO & KEYWORD LEAD MAGNET]
  Tool: python .agents/skills/ig-caption/scripts/caption.py
  Checks: Line 1 visible cut under 125 characters, search keywords in first
  50 characters, exactly 1 keyword CTA (e.g. 'Comment SCALE'), and 3–5 targeted
  niche hashtags.

[GATE 5: DURATION & MICRO-PACING]
  Tool: python .agents/skills/ig-reel/scripts/beats.py --target 22
  Checks: Total narration strictly between 18.0s and 24.0s (max 60 words).
  Diagram state change every 2.5–3.5 seconds.
```

---

## 3. The 5-Stage Production Workflow (13-Skill Integration)

```
STAGE 1: NICHE EVIDENCE & RESEARCH
  • ig-viral: Runs scripts/run_swipe.py monthly. Identifies 3x+ outlier reels
    among competitor accounts (10k-100k followers). Synchronizes winning
    formula names into brand/config.yaml:preferred_hook_formulas.
  • ig-repurpose: Extracts high-tension real incidents (Cloudflare outages, AWS S3
    cascades, memory leak debriefs, Google L5 interview questions).
  • ig-plan: Schedules slots for 10:00 AM IST and 7:00 PM IST (peak Indian tech
    workplace breaks).
  • ig-profile: Audits profile to 100/100 so arriving viewers convert to followers.

STAGE 2: SCRIPTING & ANIMATION
  • ig-reel: Writes 5-7 beat script enforcing 18-24s duration and the Seamless
    Infinity Loop Bridge.
  • hookscore: Scores spoken hook candidates (Gate: >= 70).
  • spec.py: Compiles scene spec with animated diagram, live counters, and terminals.

STAGE 3: HUMANIZATION & DESLOPPING
  • ig-human (humanize.py): Strips robotic cadence, em-dashes, and corporate slop.
  • detect.py: Verifies 100% human score across the 5-point detection panel.

STAGE 4: PACKAGING & ASSETS
  • ig-caption: Packages 125-char line 1 cut + 1-word keyword CTA + 5 niche hashtags.
  • ig-carousel: Generates companion 5-7 slide carousel with screenshot-worthy
    cheat sheet slide (drives massive Saves).

STAGE 5: DISTRIBUTION & FIRST-HOUR LAUNCH
  • ig-comment: Outbound authority seeding on 5 top creator accounts in hour 1.
  • ig-reply: Instant triage replies to comments in first 60 minutes.
  • ig-story: 4-frame story with interactive poll within 5 minutes of posting.
  • ig-dm: Automated keyword asset delivery (sends architecture PDF to DMs).
  • ig-audit: Post-mortem on hold-at-3s and outlier multiples; feeds back to Stage 1.
```

---

## 4. The 60-Minute Launch Checklist (Algorithmic Priming)

The first 60 minutes after publishing determine whether Instagram expands distribution to Explore:

- [ ] **T-15 mins**: Run `ig-comment`. Place 5 thoughtful, insightful comments on fresh posts of top accounts in the niche. (Pulls active profile viewers right before your post drops).
- [ ] **T+00 mins**: Publish the Reel + Carousel. Verify thumbnail crop in profile grid.
- [ ] **T+05 mins**: Run `ig-story`. Share the Reel to Stories with an interactive engagement sticker:
  - *Frame 1*: Video clip preview with a curiosity sticker: *"Would you run this in production? [Yes / No]"*.
- [ ] **T+15 mins to T+60 mins**: Run `ig-reply`. Monitor incoming comments. Reply to every comment within 5 minutes, ending replies with a relevant technical follow-up question to double the thread depth.
- [ ] **Ongoing**: `ig-dm` delivers the promised architecture cheat sheet to everyone who comments the keyword (`SCALE`, `SHARD`, etc.).

---

## 5. Weekly Flywheel Feedback Loop

Every Monday:
1. Run `python -m src.post_log export` to produce `data/post_log.md`.
2. Run `ig-audit` on the past week's posts:
   - Calculate 3-second hold rate (target: >65%).
   - Identify top 3 formulas by sends/reach.
3. Run `python scripts/run_swipe.py` to ingest new competitor outliers into `data/swipe/swipe.md`.
4. Update `brand/config.yaml:preferred_hook_formulas` with the updated top performers.
