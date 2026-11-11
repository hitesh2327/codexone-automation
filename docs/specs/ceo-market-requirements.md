# CEO Market Requirements & Executive Priorities (`CDX-001`)

> **Owner:** Odin — CEO (`CDX-001`)  
> **Product:** Mintly (`codexone-automation`) by Anjanex Labs  
> **Date:** 2026-11-11  
> **Horizon:** Sprint 2 & Q1 2027 (Post-Jan 1, 2027 Launch)  
> **Handoff Targets:** Vision & Wanda Maximoff (Business Analysts), Nick Fury (PM), Reed Richards (CTO), Shuri (CFO)  
> **Active Skills:** `gstack-founder-mode`, `market-and-competitor-intelligence`, `conductor-spec-driven-dev`

---

## 1. Executive Thesis & Strategic Positioning

Mintly's current core engine automates **AI topic discovery → script/diagram generation → Telegram approval → Instagram & YouTube Shorts publishing** (`src/plans.py`, `src/reel_v2/spec.py`, `src/publish.py`, `src/publish_youtube.py`). While this solves the "blank-page to daily-post" bottleneck for tech/educational faceless creators, **three structural shifts in Q4 2026–2027** dictate our Sprint 2 and Q1 2027 roadmap:

1. **The "Death of Flat $10 Tools" & Workflow Bundling:** Solo creators face severe subscription fatigue and resist paying standalone "AI taxes" ($20/mo just for an AI writer). Willingness to pay (WTP) concentrates around **end-to-end outcome suites** ($29–$49/mo US, €20–€50/mo EU, ₹1,499–₹2,999/mo India) that combine **creation + distribution + lead monetization**.
2. **Creator + Ghostwriter + Boutique Agency Convergence:** Faceless automation is an entry wedge; the sticky, high-LTV retention wedge is **own-video AI editing** (creators uploading raw talking-head/screen clips) and **multi-client agency workspaces** where agencies replace manual video editors and social media managers.
3. **Distribution Without Attribution Churns:** Posting daily Reels/Shorts without **lead capture (Comment-to-DM)** or **performance-driven topic loops** makes ROI invisible to the buyer within 30 days.

---

## 2. Q4 2026 / 2027 Willingness-to-Pay (WTP) & Competitor Benchmarks

### 2.1 Regional Willingness-to-Pay Matrix (US, Europe, India)

| Market | Buyer Segment | WTP Sweet Spot (Monthly) | Buying Behavior & Friction Points | Mintly Pricing Fit |
|---|---|---|---|---|
| **United States** | Solo Creator / Solopreneur | **$30 – $79 / mo** | Treats tools as tax-deductible opex; expects 1-click ROI, native TikTok/IG/YT/LinkedIn/X sync, and reliable English/ASR editing. | `$19` (Starter) / `$39` (Creator) / `$79` (Pro) |
| **United States** | Ghostwriter / Boutique Agency | **$300 – $1,000+ / mo** | Buys to replace $1.5k–$3k/mo junior editors/SMMs; requires multi-brand workspaces, client approval links, white-label reports. | `$149 – $299 / mo` Agency Tier (5–15 seats/brands) |
| **Europe (EU/UK)** | Solo Creator | **€20 – €50 / mo** | More conservative recurring spend; demands GDPR clarity, EUR/localized billing, and multi-language captions/narration. | `€19` / `€39` / `€75` (PPP-parity with US) |
| **Europe (EU/UK)** | Agency | **€200 – €600 / mo** | Strict data privacy & client data isolation; requires GDPR-compliant deletion and non-US-hosted/clean processing disclosures. | `€149 – €279 / mo` Agency Tier |
| **India** | Solo Creator / Educator | **₹800 – ₹2,500 / mo** (~$10–$30) | High volume, high price sensitivity; expects UPI/e-mandate autopay (Razorpay), Hinglish narration (`en`/`hi`), and GST invoices. | `Lite ₹699`, `Starter ₹1,499`, `Creator ₹2,999` |
| **India** | Marketing / Talent Agency | **₹8,000 – ₹25,000 / mo** (~$100–$300) | Flexible client-slot pricing preferred over rigid per-seat fees; manages 5–20 regional creator/D2C accounts. | `Pro ₹5,999` + `Agency ₹14,999 / mo` |

### 2.2 Competitive Landscape Audit

| Competitor | Core Wedge | Pricing Structure (2026) | Observed Gaps / User Complaints (Our Exploit Wedge) |
|---|---|---|---|
| **OpusClip** | Long-to-short AI video clipping | Free (60 min, watermark) · Starter $15/mo · Pro $29/mo ($14.50 annual) | Purely reactive clipper; no daily autonomous topic discovery, no carousel generator, no Telegram/auto-publish loop. |
| **Submagic** | Viral captions, B-roll, Magic Clips | Starter $19/mo · Pro $39/mo · Business $69/mo | Video-only; lacks multi-platform text/carousel repurposing, DM automation, and Indian PPP/Hinglish pricing. |
| **Captions / Mirage** | Talking-head mobile studio + avatars | Lite $4.99 · Basic $9.99 · Max $24.99 · Scale $69.99–$279.99 | Mobile-first credit burn; weak B2B/agency multi-account workflows and zero RSS/niche trend-to-post automation. |
| **Predis.ai** | AI social posts, carousels & ad creatives | Core ~$24–$32/mo · Rise ~$55/mo · Enterprise+ ~$212/mo | Generic "AI-slop" templates; lacks Mintly's deterministic animated diagram engine (`reel_v2`), Hinglish voice, and DM funnels. |
| **ManyChat** | Comment-to-DM conversational funnels | Free (25 contacts) · Essential ~$14/mo · Pro ~$29+/mo (scales with contacts) | Zero content creation or video rendering; creators must pay for *both* a creation suite and ManyChat ($29 + $29 = $58/mo). |

**Strategic Takeaway:** Mintly's unfair moat is **bundling Automated Creation + Own-Video AI Editing + Multi-Platform Repurposing + Comment-to-DM Capture** at a unified price that undercuts the fragmented 3-tool stack ($90–$120/mo combined).

---

## 3. Top Market Requirements by ICP

### ICP 1: Solo Creators & Tech/Niche Educators
- **MKT-REQ-01 — Own-Video AI Editing ("Upload & Polish"):** Creators already film 30–90s talking-head or screen-recorded clips on Loom/iPhone. They need direct upload → automatic silence/filler removal → word-level dynamic captions (EN + Hinglish) → smart zoom/B-roll/diagram cutaways → 9:16 export & auto-schedule.
- **MKT-REQ-02 — Dynamic Non-Tech Niches & Custom RSS/Substack Feeds:** Moving beyond hardcoded Tech/DSA/SystemDesign (`src/fetch_topics.py` `CATEGORY_KEYWORDS`) to any creator niche (Finance, Fitness, Real Estate, D2C, AI News) via user-supplied RSS/Substack/YouTube feeds and custom visual styles.
- **MKT-REQ-03 — ManyChat-Style Comment-to-DM Lead Capture:** Triggering an automated Instagram DM (delivering a Notion link, PDF, or booking URL) when a viewer comments a keyword (e.g., `"GUIDE"`, `"LINK"`) on a Mintly-published Reel or Carousel. Ties views directly to leads/sales.

### ICP 2: Ghostwriters & LinkedIn/X Thought-Leadership Consultants
- **MKT-REQ-04 — Multi-Platform Auto-Repurposing (1 → 5 Formats):** Converting a single validated topic, Substack post, or uploaded video into platform-native artifacts simultaneously:
  - Instagram Carousel (1080×1350) + Reel (9:16)
  - YouTube Shorts (9:16)
  - **LinkedIn** (PDF document carousel + long-form hook post)
  - **X / Twitter** (5–7 tweet thread + native short video)
  - **TikTok** (US/EU expansion — non-India markets)

### ICP 3: Small Marketing & Social Media Agencies
- **MKT-REQ-05 — White-Label Multi-Account Client Workspaces:** A single agency login managing 5–25 client workspaces (`workspace_id` / sub-accounts), each with isolated IG/YT/LI/X OAuth tokens, brand kits, approval channels (branded Web Approval Link instead of Mintly-branded Telegram bot), and white-label PDF/portal performance reports.
- **MKT-REQ-06 — Analytics-Driven Topic Loops:** Automatically ingesting IG Insights & YT Analytics (reach, 3-sec hook retention, saves, shares, comments) per `posted_topics` row to score what worked and weight future `rank_topics.py` & `hookscore.py` selections toward high-converting angles.

---

## 4. Future Enhancement Requirements Handoff (BA Team: Vision & Wanda Maximoff)

> **Scope Guardrail (`spec_driven_development_enforcement`):** None of these items enter active Sprint 2 coding without an approved `SPEC.md` and `PROGRESS.md` slice. Vision & Wanda Maximoff must convert prioritized items below into formal PRDs + BA acceptance criteria before assigning `PRJ-XXX` / `MNT-XXX` tickets to engineering.

| Handoff ID | Initiative | Target ICP | Core User Journey & Acceptance Boundaries | Primary Dependencies |
|---|---|---|---|---|
| **BA-HANDOFF-01** | **Multi-Platform Publisher & DB Replan** (LinkedIn, X, TikTok alongside IG/YT) | Ghostwriters, Solo Creators, Agencies | User links LI/X/TikTok OAuth in Integrations; `posts.targets` supports `["ig","yt","li","x","tt"]`; platform-specific caption/aspect adaptation (`src/publish_*.py`). | `feat/multiplatform-db-replan` schema migration; Meta/LI/X app review approvals. |
| **BA-HANDOFF-02** | **Dynamic Categories & Custom RSS/Substack Engine** | Non-Tech Creators, Newsletter Writers | User defines custom categories + pastes RSS/Substack URLs; single-call LLM semantic tagger scores top candidates; visual renderer decouples tech icons for general niches. | `feat/dynamic-categories-engine`; SSRF-safe fetcher (CTO ADR-003). |
| **BA-HANDOFF-03** | **Own-Video AI Editor (Upload → ASR → `EditSpec`)** | Solo Creators, Educators | User uploads raw MP4/MOV (<= 150MB / 3 min); AI removes dead air, generates word-synced captions + cutaways; previews & approves before publishing. | Presigned upload, Deepgram/Whisper ASR, FFmpeg/Remotion worker (CTO ADR-004); CFO upload caps. |
| **BA-HANDOFF-04** | **Comment-to-DM Lead Capture Engine** | Solo Creators, Coaches, D2C Brands | User configures per-post keyword trigger (`"SYSTEM"`) + DM reply payload (text + URL) + optional email/follow gate; Meta webhook triggers IG Messaging API DM within 5s. | Meta `instagram_manage_comments` & `instagram_manage_messages` permissions; rate-limit queue. |
| **BA-HANDOFF-05** | **Agency White-Label & Multi-Client Workspaces** | Small Agencies (5–25 clients) | Agency owner creates isolated Client Workspaces, invites client reviewers via brandless Web Approval Portal, assigns custom domain/logo on reports. | RBAC (`workspace_members`), tenant-scoped billing add-on seats, isolated OAuth vault. |
| **BA-HANDOFF-06** | **Analytics-Driven Topic & Hook Feedback Loop** | All Paid Tiers | Nightly cron pulls 48h/7d IG Insights & YT Analytics per `post_id`; surfaces top-performing categories/hooks in Dashboard and biases `rank_topics.py` weights. | IG Insights (`instagram_basic`, `instagram_manage_insights`) + YT Analytics API scopes. |

### BA Handoff Instructions for Vision & Wanda Maximoff
1. **Do NOT bundle everything into one monolith:** Produce separate `docs/specs/<feature>-prd.md` specs with explicit **Banned Features (v1)** lists.
2. **Enforce Anti-Slop Copy:** Every user-facing label must use creator terms (*"Clip Studio"*, *"Lead Triggers"*, *"Client Workspaces"*), never internal jargon (*"ASR pipeline"*, *"SSRFs"*, *"EditSpec JSON"*).
3. **Require Gate Sign-Off:** Every BA PRD must include CFO Unit Economics sign-off (Shuri) and CTO Security/Schema sign-off (Reed Richards) before moving to Sprint execution.

---

## 5. Upper-Layer Priority Rubric (RICE + ARR Impact) — Sprint 2 & Q1 2027

**Scoring Formula:**
- **Reach (R):** Estimated active/target paying accounts impacted per quarter (1–10 scale, where 10 = 90–100% of user base).
- **Impact (I):** Conversion / retention / expansion lift (`3.0` = Massive, `2.0` = High, `1.0` = Medium, `0.5` = Low).
- **Confidence (C):** Execution & demand certainty (`0.50`–`1.00`).
- **Effort (E):** Engineering person-weeks across Backend + Frontend + QA.
- **RICE Score:** `(R × I × C) / E`
- **ARR Weighting:** Blended rank prioritizes items that unlock **Jan 1 Launch readiness, US/EU USD conversion, and churn prevention** first.

| Rank | Initiative | R | I | C | E (wks) | RICE Score | Est. Q1–Q2 2027 ARR Lift | Sprint / Quarter Assignment |
|---:|---|---:|---:|---:|---:|---:|---|---|
| **1** | **Admin Console, Telemetry & Billing/GST Invoices** *(In-flight foundation)* | 10 | 2.0 | 0.95 | 2.0 | **9.50** | Risk-mitigation + B2B GST conversion (**+$25k ARR unlocked**) | **Sprint 2 (Pre-Jan 1 Gate)** |
| **2** | **Dynamic Categories & Custom RSS Engine** (`BA-HANDOFF-02`) | 9 | 2.0 | 0.90 | 2.0 | **8.10** | Unlocks non-tech TAM (5x addressable creators; **+$48k ARR**) | **Sprint 2 (Launch Ready)** |
| **3** | **Multi-Platform Publisher: LinkedIn + X + TikTok** (`BA-HANDOFF-01`) | 9 | 2.5 | 0.85 | 3.0 | **6.38** | Unlocks US/EU Ghostwriters & Pro/Creator upgrades (**+$65k ARR**) | **Sprint 2 → Q1 Wk 2** |
| **4** | **Analytics-Driven Topic Loop** (`BA-HANDOFF-06`) | 8 | 1.5 | 0.85 | 2.0 | **5.10** | Reduces M2–M3 solo creator churn by ~25% (**+$30k retained ARR**) | **Q1 2027 (Jan–Feb)** |
| **5** | **Own-Video AI Editor (Upload → ASR → `EditSpec`)** (`BA-HANDOFF-03`) | 8 | 3.0 | 0.80 | 4.5 | **4.27** | Direct OpusClip/Submagic displacement; justifies $39–$79/mo (**+$90k ARR**) | **Q1 2027 (Feb–Mar)** |
| **6** | **Comment-to-DM Lead Capture** (`BA-HANDOFF-04`) | 7 | 2.5 | 0.75 | 3.5 | **3.75** | Replaces standalone ManyChat ($29/mo); drives Starter→Creator upgrades (**+$55k ARR**) | **Q1 2027 (Mar)** |
| **7** | **Agency White-Label & Multi-Client Workspaces** (`BA-HANDOFF-05`) | 4 | 3.0 | 0.80 | 5.0 | **1.92** | High ACV ($149–$299/mo or ₹14,999/mo), but narrower early volume (**+$72k ARR**) | **Q2 2027 (Apr–May)** |

### Executive Mandate for Sprint 2 (Pre-Jan 1, 2027)
1. **Lock & Land the Three Active Workstreams:** Linearize and merge `feat/admin-stakeholder-console`, `feat/dynamic-categories-engine`, and `feat/multiplatform-db-replan` safely into `dev` → `main` before Dec 15, 2026.
2. **Protect Launch Economics:** Enforce CFO Shuri's free-tier and regeneration guardrails before turning on public self-serve signups on Jan 1, 2027.
3. **Hold Scope on Q1 Enhancements:** Own-Video Editor, Comment-to-DM, and Agency White-Label enter BA discovery (`Vision` & `Wanda Maximoff`) immediately, with engineering kickoff sequenced strictly after Jan 1 launch telemetry is green.
