# Mintly — January 1, 2027 Master Marketing & Launch Playbook

> **Document ID:** `MNT-MKT-2027-01`  
> **Launch Date:** **Friday, January 1, 2027** (T-50 Countdown starts **Thursday, November 12, 2026**)  
> **Product & Legal Entity:** **Mintly** by **Anjanex Labs** (`codexone-automation`)  
> **Pod Lead:** **Loki — CMO** (`CDX-004`)  
> **Growth & Sales Pod:** **Pepper Potts** (`CDX-020`), **Stephen Strange** (`CDX-021`), **Thor** (`CDX-022`), **Peter Quill** (`CDX-023`)  
> **Active Skills Applied:** `conversion-copywriting`, `unslop-copywriting`, `agentic-seo-geo`, `twitter-algorithm-optimizer`, `harvey-b2b-outbound-sdr`

---

## 0. Ground-Truth Product Audit & Pre-Launch Blockers

Every claim in this playbook is grounded in the current Mintly codebase (`src/plans.py`, `web/src/pages/Subscription.tsx`, `brand/config.yaml`, `README.md`, `docs/specs/hinglish-narration-plan.md`, and `web/src/lib/company.ts`).

### What Ships Live on Day 1 (Verified in Repo)
- **Automated Topic Discovery & Dedupe:** Pulls trending engineering/tech topics from Hacker News, Reddit, dev.to, GitHub Trending, and arXiv, ranking and deduplicating against `posted_topics` so accounts never repeat a post.
- **Dual-Format Output per Run:**
  - **Short-Form Reels (`1080×1920`, 18–24s):** Hook → Problem → Architecture Shift → Loop Bridge structure with automated voiceover (7 English voices + 2 Hindi/Hinglish voices: Madhur & Swara), word-highlight captions (English), optional BGM, and animated step-by-step walkthroughs (`array`, `string`, `linked_list`, `stack`).
  - **Carousels (`1080×1350`, 5–7 slides) OR 12s Image Reels:** Cheat-sheet final slide rendered with royalty-free mood tracks (`calm`, `focus`, `upbeat`).
- **Hinglish Narration Mode:** Spoken Hindi with native English technical terminology while keeping on-screen slides, code, and captions in English.
- **Zero-Risk Telegram Approval Gate:** Every reel and carousel hits Telegram first with **Approve / Reject / Regenerate** buttons (up to 3 free regenerations per post; reply with steering notes or voice requests before tapping Regenerate). Nothing publishes without an explicit tap (`src/publish.py`). Unactioned drafts expire after 36 hours.
- **Dual-Platform Auto-Publishing & Scheduling:** Publishes approved items to **Instagram** (Reels & Carousels via Instagram Login Graph API v21.0) and **YouTube Shorts** (YouTube Data API v3 with `publishAt` scheduling and per-platform retry isolation).
- **Verified Self-Serve Catalog (`src/plans.py` — Razorpay INR + 18% GST):**
  - **Lite (`₹699/mo` | `₹6,990/yr`):** 30 carousels/mo (1/day), Instagram only.
  - **Starter (`₹1,499/mo` | `₹14,990/yr`):** 30 reels + 30 carousels/mo (1/day), IG + YouTube Shorts.
  - **Creator (`₹2,999/mo` | `₹29,990/yr`, Popular):** 60 reels + 60 carousels/mo (2/day), IG + YouTube Shorts, custom niche/tone/brand style, voice selection, Regenerate & Publish Now.
  - **Pro (`₹5,999/mo` | `₹59,990/yr`):** 120 reels + 120 carousels/mo (up to 4/day), IG + YouTube Shorts, custom posting schedule.

### Explicitly Labeled Q1 2027 Roadmap (Never Sell as Live Today)
- **Dynamic Niches:** Expanding topic engines beyond AI/Dev/DSA/System Design/Interview/OS into Finance, Fitness, SaaS Founders, and custom user-defined feeds.
- **In-Dashboard Video Editor:** Browser-based timeline, caption, and voice adjustments before approval.
- **Agency Operator Console (`MNT-900`):** Multi-brand client seats and centralized approval queues.

### Critical Ops Blockers to Clear Before Public Checkout (Flagged to `Nick Fury` / `Shuri` / `Tony Stark`)
1. **`web/src/lib/company.ts` Legal Placeholders:** `entityType`, `address`, `email`, `phone`, `grievanceOfficer`, and `courtsCity` are currently `null` (rendering draft warnings on `/legal/*`). Must be populated before enabling live Razorpay payments.
2. **YouTube API Production Audit & Quota:** Unverified Google Cloud projects lock uploads to `private`, and default quota (`10,000` units/day @ `1,600` units/upload) caps global uploads at ~6 Shorts/day unless quota increase + OAuth verification are completed or tenant BYO-OAuth is enforced.
3. **7-Day Trial / Founding Coupon Mechanics:** `src/plans.py` currently only defines paid monthly/yearly tiers and `NO_PLAN` (`free` with `0` quota). Engineering must confirm Razorpay trial/coupon config or Founding Pass provisioning before Dec 20.

---

## 1. 50-Day Countdown Calendar (Nov 12, 2026 → Jan 1, 2027)

> **Owner:** **Loki — CMO** (`CDX-004`)

### Phase 1: Foundation, Proof & Waitlist Capture (Weeks 1–3)

| Window | Dates | Core Objective | Key Deliverables | Owner |
| :--- | :--- | :--- | :--- | :--- |
| **Week 1** | Thu Nov 12 – Wed Nov 18 | Ground-truth lock, landing waitlist live & dogfood proof | Ship anti-slop landing page + waitlist form; publish 14 consecutive Mintly-generated Reels/Carousels on `@codexonebyhitesh` for live proof; clear `company.ts` + YouTube OAuth verification tickets with Ops. | **Loki**, **Stephen Strange** |
| **Week 2** | Thu Nov 19 – Wed Nov 25 | Founding Creator waitlist & B2B agency prospecting | Launch Founding Creator waitlist magnet; build target list of 150 boutique social/dev-content agencies (India, US, UK); inspect sites & draft first 30 Harvey 3-sentence cold emails (queued for HITL approval). | **Pepper Potts**, **Stephen Strange** |
| **Week 3** | Thu Nov 26 – Wed Dec 2 | Organic X/Reddit seeding & SEO/GEO pillars | Publish X Thread #1 & #2; run 3 non-promotional Reddit value posts (`r/SideProject`, `r/InstagramMarketing`, `r/developersIndia`); ship 3 SEO/GEO comparison/docs pages with JSON-LD schema (`SoftwareApplication`, `FAQPage`). | **Peter Quill**, **Stephen Strange** |

### Phase 2: Beta Cohort, Assets & Partner Seeding (Weeks 4–6)

| Window | Dates | Core Objective | Key Deliverables | Owner |
| :--- | :--- | :--- | :--- | :--- |
| **Week 4** | Thu Dec 3 – Wed Dec 9 | Closed Founding Beta (25 creators) & case metrics | Onboard 25 waitlist creators onto Starter/Creator beta; collect 7-day time-saved metrics, Telegram approval screenshots, and 5 crisp video/text testimonials; run 7-day trial email sequence test. | **Loki**, **Pepper Potts**, **Stephen Strange** |
| **Week 5** | Thu Dec 10 – Wed Dec 16 | Product Hunt Ship Kit & 60s Launch Reel | Record 60-second raw founder screen-capture demo (no stock footage); finalize PH gallery (5 high-contrast 1270×760 slides), Maker Comment, and Hunter alignment; outreach to 25 micro-creators (10k–100k followers) for Jan 1 affiliate cohort. | **Thor**, **Peter Quill** |
| **Week 6** | Thu Dec 17 – Wed Dec 23 | Agency pilots, PostHog tracking & pre-launch warmup | Close 3–5 paid Agency Pilot commitments; verify PostHog + UTM attribution (`utm_source`, `utm_campaign`) across signup → Telegram connect → first publish → Razorpay checkout; run X Thread #3 & #4. | **Pepper Potts**, **Peter Quill** |

### Phase 3: Launch-Week Day-by-Day Execution (Thu Dec 24 – Fri Jan 1, 2027)

| Day | Date | Milestone | Exact Actions & Owners |
| :--- | :--- | :--- | :--- |
| **T-8** | Thu Dec 24 | Code & Offer Freeze | **Loki:** Finalize Jan 1 Founding Offer pricing/codes in Razorpay. **Stephen Strange:** Lock landing page copy, pricing table, and all 5 onboarding emails in ESP. |
| **T-7** | Fri Dec 25 | PH Ship Kit Staging | **Thor:** Upload Product Hunt draft (tagline, 5 gallery images, 60s demo MP4, Maker Comment). Verify countdown/teaser page URL. |
| **T-6** | Sat Dec 26 | Affiliate Pack Dispatch | **Peter Quill:** Send affiliate links, 3 swipe tweets, and 2 demo Reels to the 25 seeded creators + 25 beta users. Confirm Jan 1 posting windows. |
| **T-5** | Sun Dec 27 | Agency Follow-up Wave | **Pepper Potts:** Send 48-hour Founding Agency bump email to open B2B conversations (HITL approved). Book Jan 2–5 onboarding slots. |
| **T-4** | Mon Dec 28 | Waitlist "72 Hours" Alert | **Stephen Strange:** Send waitlist warm-up email previewing the Founding Creator lock-in rate and 1-tap Telegram workflow GIF. |
| **T-3** | Tue Dec 29 | Dry-Run Funnel QA | **Loki + Thor:** End-to-end test: Waitlist link → Signup → Config → 1-click Telegram connect → Sample Reel/Carousel generation → Razorpay test checkout. |
| **T-2** | Wed Dec 30 | Reddit + X Pre-Launch Teaser | **Peter Quill:** Post Thread #5 ("How we built a 24/7 Reels & Carousels pipeline that never posts without Telegram approval") + `r/SaaS` build breakdown. |
| **T-1** | Thu Dec 31 | New Year's Eve Final Lock | **Thor:** Confirm PH scheduled launch for `00:01 PST` (`13:30 IST` Jan 1). **Stephen Strange:** Queue Jan 1 "Doors Open" email for `13:35 IST`. |
| **T-0** | **Fri Jan 1** | **PUBLIC LAUNCH DAY** | **All Hands War Room:** Execute 24-hour IST+PST Product Hunt, X, LinkedIn, Reddit, Email, and Affiliate blitz (see Section 5 timeline). |

---

## 2. Positioning & Messaging Matrix

> **Owner:** **Loki — CMO** (`CDX-004`) · *Filtered via `unslop-copywriting`*

### Category Positioning
**Mintly is not another generic AI video wrapper.** It is a **daily content desk with a human circuit breaker**: it finds what your audience is actually talking about today, renders studio-consistent Reels (with animated walkthroughs and English or Hinglish narration) and Carousels, drops them into your Telegram chat for a 1-tap Approve/Regenerate, and publishes straight to Instagram and YouTube Shorts.

### Target ICP Matrix

| Segment | Who They Are | Expensive Bleed (Pain) | Mintly Winning Wedge | Target Plan |
| :--- | :--- | :--- | :--- | :--- |
| **ICP 1: Solo Creators (Tech today; Finance/Fitness via Dynamic Niches Q1)** | Developers, educators, and niche creators with 1k–100k followers trying to post daily. | Spend 6–10 hrs/week researching, scripting, recording, and formatting carousels—then burn out after week 3. | **Consistency without burnout:** 1–2 polished Reels + Carousels ready in Telegram every morning before coffee. Hinglish or English voiceover built in. | **Starter** (`₹1,499/mo`) or **Creator** (`₹2,999/mo`) |
| **ICP 2: Busy Founders & Indie Hackers** | Technical founders building SaaS/dev tools who know short-form drives signups but hate being on camera. | Paying a freelancer `₹25k–₹50k/mo` (`$500–$1,500/mo`) or ghosting Instagram/Shorts for months. | **Zero-camera authority:** Faceless animated walkthroughs + cheat-sheet carousels derived from real GitHub/HN/arXiv trends. | **Creator** (`₹2,999/mo`) or **Lite** (`₹699/mo`) |
| **ICP 3: Boutique Social & Ghostwriting Agencies** | 2–15 person content agencies managing 5–20 founder/creator accounts on retainer. | Junior editors spend 4 hrs per client post on research, static carousels, and manual IG/YT uploads—crushing margins. | **Margin multiplier:** Generate client-ready Reels + Carousels on schedule and route drafts to client Telegrams for 1-tap sign-off. | **Pro** (`₹5,999/mo` per high-volume brand) or **Agency Multi-Seat** |

### Anti-Slop Headline & Hook Variants

| Angle | Headline (Zero Clichés) | Sub-Hook |
| :--- | :--- | :--- |
| **Speed + Control** | **Daily Reels and Carousels. Nothing posts until you tap Approve.** | Mintly finds trending topics, writes the script, renders the video and slides, and waits for your thumbs-up on Telegram. |
| **Anti-Agency Cost** | **30 Reels and 30 Carousels a month for less than one freelance edit.** | Built for solo creators and founders who want daily Instagram and YouTube Shorts reach without living in Premiere. |
| **Hinglish Edge** | **Speak to India's tech crowd in Hinglish—with clean English slides.** | Natural Hindi voiceover with accurate English code terms, paired with crisp carousels and animated walkthroughs. |
| **Creator Burnout** | **Stop spending Sunday night batching content for the week.** | Wake up to ready-to-publish Reels and Carousels in Telegram. Tap Approve, or reply with one note to regenerate. |

---

## 3. Founding Creator Promo & Agency Outbound (`Pepper Potts`, `CDX-020`)

### 3A. Jan 1 Founding Creator Offer (Limited: First 100 Paid Seats or Jan 1–7, 2027)
Grounded directly in `src/plans.py` annual & monthly pricing:
- **Founding Rate Lock (40% Off First 3 Months OR 3 Months Free on Annual):**
  - **Founding Starter:** `₹899/mo` for 3 months (reg. `₹1,499/mo`) — or **Annual Founding Pass at `₹11,990/yr`** (effective `₹999/mo`, saving `₹5,998` vs monthly).
  - **Founding Creator (Recommended):** `₹1,799/mo` for 3 months (reg. `₹2,999/mo`) — or **Annual Founding Pass at `₹23,990/yr`** (effective `₹1,999/mo`, saving `₹11,998` vs monthly).
- **Founding Perks Included:**
  1. **Lifetime Founding Price Lock** on annual renewals while subscription stays active.
  2. **Priority Onboarding Slot** for **Dynamic Niches** (Finance, Fitness, SaaS Founders) & the **Browser Video Editor** as they roll out in Q1 2027.
  3. **Direct Founder Telegram Concierge** for custom voice & brand palette calibration in Week 1.

### 3B. 3-Tier B2B Agency Partner Packages (Manual B2B Invoicing / Dedicated Workspaces)

*Note: Self-serve plans in `src/plans.py` cover 1 brand per workspace (`Lite ₹699` to `Pro ₹5,999`). Agency tiers bundle multiple isolated workspaces + white-glove onboarding before the MNT-900 Admin Console ships.*

| Tier | Target Agency Size | Monthly Price (INR / USD Est.) | Monthly Output Cap | Included Deliverables |
| :--- | :--- | :--- | :--- | :--- |
| **Agency Pod (5 Brands)** | Solo ghostwriters & micro-agencies | **₹19,999/mo** (`$249/mo`) | 150 Reels + 150 Carousels across 5 workspaces | 5 isolated brand configs (palette, fonts, voices), 5 client Telegram approval bots, IG + YouTube Shorts auto-publishing, monthly onboarding call. |
| **Agency Studio (15 Brands)** | Boutique 3–10 person social agencies | **₹49,999/mo** (`$599/mo`) | 600 Reels + 600 Carousels across 15 workspaces | Everything in Pod + Hinglish & English voice mixes per client, priority Dynamic Niche early access, custom posting slots, Slack/Telegram support channel. |
| **Agency Scale (30+ Brands)** | High-volume personal branding firms | **₹89,999/mo** (`$1,099/mo`) | 1,500+ Reels + 1,500+ Carousels | Everything in Studio + custom HTML/CSS slide template matching client brand books, dedicated generation queue priority, quarterly strategy review. |

### 3C. Harvey 3-Sentence Anti-Slop Cold Email Templates (`harvey-b2b-outbound-sdr`)

> **HITL Security Gate (`mcp_permission_gate.md`):** Pepper Potts drafts these only after inspecting the prospect's real site/Instagram/LinkedIn. **Never send autonomously**—present exact recipient, subject, and body for explicit founder approval first.

#### Template 1: Boutique Social / Ghostwriting Agency
**Subject:** `[Agency Name] client reels`
```text
Noticed on [Agency Name]'s portfolio that you run daily carousel and short-form retainers for [Niche, e.g., B2B SaaS] founders.

Most 5-person agencies we talk to burn 12–15 editor hours a week just formatting repeat carousels and chasing client sign-offs over WhatsApp.

Worth sending a 90-second clip showing how teams generate daily Reels + Carousels and get 1-tap client approval inside Telegram?
```

#### Template 2: Tech / DevTool Brand with Stale Instagram or Shorts
**Subject:** `Quick question on [Company]'s Shorts`
```text
Saw [Company] shipped [Specific Feature/Changelog from site] last week, though your Instagram Reels and Shorts haven't had a post since [Month].

Engineering teams usually skip short-form because turning docs and changelogs into 20-second animated walkthroughs takes half a day per video.

Want me to run one of your recent blog posts through Mintly and send the finished Reel + Carousel to your Telegram to test?
```

#### Template 3: Solo Educator / Course Creator Selling Cohort Programs
**Subject:** `Your [Course/Cohort Name] carousels`
```text
Been reading your [Specific Topic] threads on X—your breakdown on [Specific Post Topic] got strong saves, but it isn't on YouTube Shorts yet.

Turning text threads into narrated Reels and 6-slide cheat sheets manually eats 6+ hours a week that most solo creators don't have mid-cohort.

Mind if I send over a 60-second walkthrough of how Mintly converts daily topics into ready-to-approve Reels in English or Hinglish?
```

---

## 4. Landing Page Hero, Waitlist & 7-Day Email Funnel (`Stephen Strange`, `CDX-021`)

### 4A. Landing Page Hero & Conversion Architecture (`conversion-copywriting` + `unslop-copywriting`)

- **Eyebrow Pill:** `Launching Jan 1, 2027 · Now accepting Founding Creators`
- **Hero Headline (H1):**  
  **Daily Reels and Carousels—approved in one tap on Telegram.**
- **Hero Subheadline:**  
  Mintly discovers trending topics in your niche, scripts and renders animated 1080×1920 Reels and 5–7 slide Carousels in English or Hinglish, and waits in Telegram for your **Approve** tap before posting to Instagram and YouTube Shorts.
- **Primary CTA Button:** `Claim Founding Creator Spot` *(Sub-trigger: `Takes 2 minutes · No card needed for waitlist · Founding 40% lock opens Jan 1`)*
- **Secondary CTA:** `Watch 60s Live Pipeline Demo`

#### Proof & Feature-to-Benefit Grid (Zero Technical Leakage)
| What Mintly Does | What That Means for You (Human Payoff) |
| :--- | :--- |
| **Finds fresh topics daily & never repeats** | Never stare at a blank Notion page or accidentally post the same topic twice. |
| **Animated walkthroughs + 9 natural voices (EN & Hinglish)** | Stand out from static text-on-video reels with crisp step-by-step visuals and voiceovers your audience actually finishes. |
| **1-tap Approve / Reject / Regenerate in Telegram** | Keep 100% editorial control from your phone. Reply with one tweak ("use Madhur" or "make hook punchier") and regenerate free. |
| **Dual-publishes to Instagram & YouTube Shorts** | Hit two algorithms from one approval tap—scheduled cleanly at your peak time slots. |
| **Cheat-sheet Carousels or 12s Image Reels** | Give followers save-worthy reference slides alongside every video so saves and shares compound. |

#### Risk Reversal & FAQ Strip
- **Nothing ever auto-posts behind your back.** If you don't tap Approve in Telegram within 36 hours, the draft quietly expires.
- **Cancel anytime in one click.** Keep your active plan through the end of your paid cycle. Fair prorated upgrades via Razorpay (UPI, cards, netbanking).

### 4B. Waitlist Capture Block (Live Nov 12 – Dec 31)
- **Headline:** `Lock 40% off your first 3 months before Jan 1.`
- **Copy:** We're onboarding 100 Founding Creators for our January 1 release. Drop your email and niche—we'll send your private invite link and Founding rate code 24 hours before public launch.
- **Fields:** `Email`, `Primary Niche` (`Tech / AI / Dev`, `Finance / Business` *(Q1)*, `Fitness / Lifestyle` *(Q1)*, `Agency / Multiple Brands`), `Language` (`English`, `Hinglish`, `Both`).
- **Button:** `Reserve My Founding Rate`

### 4C. 7-Day Trial / Onboarding Email Funnel (Exact Ready-to-Ship Copy)

#### Email 1 — Day 0 (Immediately on Signup / Waitlist Confirmation)
- **Subject:** `Your Mintly workspace is ready (2 steps to your first Reel)`
- **Body:**
  ```text
  Hey {{first_name}},

  You're in. Welcome to Mintly.

  Most automation tools fail because they either take 3 hours to configure or post embarrassing AI slop straight to your feed. Mintly does neither—nothing ever leaves your account until you tap Approve on Telegram.

  Here is your 2-minute setup to get your first Reel + Carousel tonight:
  1. Connect your Telegram bot in /config (1 click—no terminal commands).
  2. Connect Instagram (and optionally YouTube Shorts) and set your posting slot.

  Once connected, hit "Generate" on your dashboard to test your first topic in English or Hinglish.

  [Button: Connect Telegram & Run First Post ->]

  See you in your Telegram chat,
  Hitesh & the Mintly team
  ```

#### Email 2 — Day 1 (24 Hours Later — Activation Nudge)
- **Subject:** `Did your first preview hit Telegram yet?`
- **Body:**
  ```text
  Hey {{first_name}},

  Quick check—have you seen a Mintly preview inside Telegram yet?

  If not, 90% of the time it's just one skipped step in /config (usually connecting your Telegram bot or picking your first voice).

  Once that's linked, Mintly checks trending topics, builds a 20-second animated Reel + matching 6-slide Carousel, and drops both in your Telegram chat at your chosen slot.

  Don't like the hook? Reply to the Telegram message with "make the first line shorter" or "use Swara", tap Regenerate, and get a fresh version in ~2 minutes—without burning extra post quota.

  [Button: Finish 2-Minute Setup ->]

  Reply to this email if you hit any snag. I read every reply.
  — Mintly Support
  ```

#### Email 3 — Day 3 (Value Proof + Hinglish & Carousel Angle)
- **Subject:** `The 2-format trick doubling saves on tech & creator accounts`
- **Body:**
  ```text
  Hey {{first_name}},

  Posting a Reel gets you reach. Pairing it with a 6-slide cheat-sheet Carousel gets you saves—and saves are what push your next Reel into new feeds.

  Inside Mintly, every topic automatically builds both:
  - A 18–24s vertical Reel (try toggling Hinglish narration on the Generate page if you target Indian builders—spoken Hindi, crisp English tech terms).
  - Either a 5–7 slide Carousel OR a 12-second Image Reel with mood audio.

  Same topic. Zero extra editing time. Double the surface area across Instagram and YouTube Shorts.

  [Button: Generate a Hinglish + Carousel Combo ->]

  — Mintly Team
  ```

#### Email 4 — Day 5 (Objection Handling & Time Math)
- **Subject:** `6 hours of editing vs. 4 taps on your phone`
- **Body:**
  ```text
  Hey {{first_name}},

  If you script, record, caption, and design 1 Reel + 1 Carousel yourself, it takes roughly 90 minutes to 2 hours per post. At 1 post a day, that's a part-time job.

  With Mintly Starter (₹1,499/mo), 30 Reels + 30 Carousels cost ₹25 per asset—and your total daily effort is tapping "Approve" in Telegram during your morning chai.

  Already posting twice a day? Creator (₹2,999/mo) unlocks 60 Reels + 60 Carousels a month across Instagram and YouTube Shorts, custom brand style, and voice selection.

  [Button: Compare Mintly Plans ->]

  — Mintly Team
  ```

#### Email 5 — Day 7 (Trial / Founding Window Closing Urgency)
- **Subject:** `Your Founding Creator rate expires tonight (40% off lock)`
- **Body:**
  ```text
  Hey {{first_name}},

  Quick heads up: your Founding Creator window closes tonight at 11:59 PM IST.

  If you want Mintly generating and queueing your daily Reels and Carousels for the next 30 days, lock your Founding rate before midnight:
  - Founding Starter: ₹899/mo for 3 months (30 Reels + 30 Carousels/mo)
  - Founding Creator: ₹1,799/mo for 3 months (60 Reels + 60 Carousels/mo)
  - Or go Annual and lock 2 months free + Founding priority for Dynamic Niches & Video Editor in Q1.

  Zero lock-in. Cancel in one click anytime from Billing.

  [Button: Lock My Founding Plan Now ->]

  — Hitesh & the Mintly team
  ```

---

## 5. Product Hunt Ship Kit & Launch Reel Script (`Thor`, `CDX-022`)

### 5A. Product Hunt Ship Kit
- **Product Name:** `Mintly`
- **Tagline (58 chars, limit 60):** `Daily Reels & Carousels, approved in one tap on Telegram`
- **Category Tags:** `Social Media`, `Artificial Intelligence`, `Productivity`, `Video`
- **Short Description (245 chars):**  
  `Mintly discovers trending topics in your niche, renders animated 1080×1920 Reels (English or Hinglish) and cheat-sheet Carousels, sends previews to Telegram for 1-tap approval, and auto-publishes to Instagram & YouTube Shorts.`
- **5-Slide Gallery Blueprint (`1270×760`):**
  1. **Slide 1 (Hero):** Dark `#0D1117` Mintly workspace + "Trending Topic → Reel + Carousel → Telegram Approve → IG + Shorts" visual flow.
  2. **Slide 2 (Telegram Circuit Breaker):** Real phone screenshot showing Telegram preview with `Approve / Reject / Regenerate` inline buttons + feedback reply.
  3. **Slide 3 (Animated Walkthroughs):** Side-by-side frame of an animated array/linked-list Reel (`1080×1920`) and 6-slide Carousel (`1080×1350`).
  4. **Slide 4 (Hinglish + 9 Voices):** Voice selector showing English + Hinglish (Madhur/Swara) toggle on the Generate page.
  5. **Slide 5 (Pricing & Founding Offer):** Clean comparison of Starter (`₹1,499`) and Creator (`₹2,999`) + Jan 1 Founding discount badge.

#### Product Hunt Maker Comment (Zero Fluff, Builder-to-Builder)
```markdown
Hey Product Hunt 👋 Hitesh here, founder of Anjanex Labs.

I built Mintly because I tried automating my own tech page (@codexonebyhitesh) and hated both options on the market:
1. "1-click AI auto-posters" that flood your feed with cringey, inaccurate slop while you sleep.
2. Spending 10 hours every weekend fighting video timelines and Canva grids.

So we built a strict rule into Mintly: **nothing ever publishes without your tap on Telegram.**

Every day at your scheduled slot, Mintly:
- Pulls fresh, non-repeating topics from HN, Reddit, dev.to, GitHub Trending, and arXiv.
- Generates an 18–24s animated Reel (English or Hinglish voiceover) + a 5–7 slide Carousel (or 12s Image Reel).
- Sends both previews straight to your Telegram chat with **Approve / Reject / Regenerate** buttons.
- Reply with one sentence ("swap voice to Andrew" or "sharper hook") and hit Regenerate free of quota.
- Once approved, publishes cleanly to Instagram and YouTube Shorts.

**What's next in Q1 2027:** Dynamic Niches (expanding beyond Tech/AI into Finance, Fitness, and SaaS Founders), an in-browser Video Editor, and multi-brand Agency seats.

**PH Launch Special (Jan 1–7):** 40% off your first 3 months on Starter or Creator, or Annual Founding Pass pricing—live right on the billing page.

Ask me anything about the pipeline, Telegram workflow, or Hinglish voice engine—I'm in the comments all day!
```

### 5B. 60-Second Founder Demo / Launch Reel Script (`1080×1920` + `16:9` PH Video)

| Time | Visual on Screen | Spoken Audio (Punchy, Conversational) |
| :--- | :--- | :--- |
| **0:00 – 0:06** | Split screen: messy Premiere timeline + blank Google Doc vs. clean Telegram ping. | "Most creators quit daily Reels by week three because one 20-second video takes two hours to make. Here's how I replaced that whole workflow with one tap on Telegram." |
| **0:06 – 0:16** | Screen record of Mintly `/generate` dashboard picking a trending topic + clicking Hinglish/English toggle. | "Every morning, Mintly scans Hacker News, Reddit, GitHub, and arXiv for topics you haven't posted yet. It writes a tight 20-second script and renders an animated Reel plus a matching Carousel." |
| **0:16 – 0:28** | Phone screen: Telegram bot drops the rendered MP4 + slide preview with `Approve / Reject / Regenerate`. | "Here's the catch: nothing posts automatically. It lands in your Telegram first. Want a punchier hook or a different voice? Reply once, tap Regenerate, and get a new cut in two minutes." |
| **0:28 – 0:40** | Live tap on **Approve** → cut to Instagram Reels & YouTube Shorts showing both live posts. | "When it looks sharp, tap Approve. Mintly schedules and publishes it to both Instagram and YouTube Shorts—including Hinglish narration with clean English code slides." |
| **0:40 – 0:52** | Quick montage of `/posts` queue and `/subscription` plans. | "Starter gives you 30 Reels and 30 Carousels a month for ₹1,499—less than ₹25 a post. Creator doubles that to twice a day." |
| **0:52 – 0:60** | Mintly logo + `Launching Jan 1 · 40% Founding Offer` card. | "Our Founding Creator offer is live this week only. Link's below—try one post in Telegram today." |

### 5C. Jan 1, 2027 Launch Day War Room Timeline (IST + PST Aligned)

> **Timezone Anchor:** Product Hunt day runs `00:01 PST` – `23:59 PST` = **`13:30 IST` (Jan 1) – `13:29 IST` (Jan 2)**.

| IST Time | PST Time | War Room Action | Owner |
| :--- | :--- | :--- | :--- |
| **12:30 IST** | 23:00 PST (Dec 31) | Pre-flight smoke check: landing page, `/signup`, Razorpay Founding promo, PostHog live events, Telegram bot health. | **Loki + Ops** |
| **13:30 IST** | **00:01 PST** | **PH LIVE!** Verify listing live, post Maker Comment within 3 mins, embed PH badge on landing page. | **Thor** |
| **13:35 IST** | 00:06 PST | Blast "Doors Open" Founding Offer email to full waitlist + beta list; DM 25 seeded affiliates to go live. | **Stephen Strange + Peter Quill** |
| **14:00 IST** | 00:31 PST | Drop X Launch Thread #1 (founder build story + 60s native video) + LinkedIn launch post + `r/SideProject` Show post. | **Peter Quill + Loki** |
| **16:00 IST** | 02:31 PST | First 2.5-hour check: reply to every PH comment in < 10 mins; fix any signup friction flagged in PostHog/Sentry. | **Thor + Loki** |
| **19:00 IST** | 05:31 PST | India prime-time push: Hinglish demo Reel drops on `@codexonebyhitesh` IG + YT Shorts; Pepper sends Jan 1 Agency Launch note to warm B2B prospects. | **Pepper Potts + Peter Quill** |
| **21:30 IST** | **08:01 PST** | **US East/West Morning Wave:** Drop X Thread #2 (cost breakdown + Telegram approval GIF) & founder quote-RT early user results. | **Peter Quill** |
| **00:30 IST (Jan 2)** | 11:01 PST | Midday US push: share 12-hour milestone update ("X creators joined, Y Reels generated today") on X & PH comment update. | **Thor + Loki** |
| **06:00 IST (Jan 2)** | 16:31 PST | US afternoon final push: "Final hours of Launch Day" reminder on X + LinkedIn + Telegram community channels. | **Peter Quill** |
| **13:30 IST (Jan 2)** | **00:00 PST** | PH 24h freeze! Screenshot final rank, export Day-1 funnel metrics (visits → signups → TG connects → paid), assign Day-2 follow-ups. | **Loki** |

---

## 6. Viral Distribution, SEO/GEO & Affiliate Engine (`Peter Quill`, `CDX-023`)

### 6A. 5 Ready-to-Post X/Twitter Launch Threads (`twitter-algorithm-optimizer`)

*Rules enforced on every thread: Tweet 1 < 240 chars, zero external links in Tweet 1, 1 idea per line, native media in Tweet 1 or 2, link + RT CTA in final tweet.*

#### Thread 1 (Jan 1 Launch): The "Telegram Circuit Breaker" Story
- **Tweet 1 (Hook — 218 chars):**
  `I tried 6 "AI auto-poster" tools for Instagram. Every single one eventually posted cringe slop while I slept. So we built Mintly with one hard rule: nothing posts until you tap Approve on Telegram. Here's how it works 🧵` *(Attach 60s demo video)*
- **Tweet 2:** Most tools optimize for "1-click automation" and forget your reputation. One bad AI carousel kills months of audience trust.
- **Tweet 3:** Mintly separates **production** from **publishing**: 1) Pulls fresh topics from HN, Reddit, GitHub & arXiv. 2) Renders a 20s animated Reel + 6-slide Carousel. 3) Pings your Telegram with Approve / Reject / Regenerate.
- **Tweet 4:** Don't like the hook? Reply right inside Telegram: *"make slide 1 shorter"* or *"use Andrew voice"*. Tap Regenerate. New cut arrives in ~2 minutes. Zero quota burned.
- **Tweet 5:** Tap Approve once → Mintly schedules & posts to both Instagram Reels/Carousels and YouTube Shorts.
- **Tweet 6 (CTA + Link):** Today (Jan 1) we're opening Mintly to Founding Creators at 40% off for 3 months (starts at ₹899/mo). If you found this useful, RT Tweet 1 so other builders skip the burnout. Try it here → `[mintly-link]?utm_source=x&utm_campaign=jan1_t1`

#### Thread 2: The Unit Economics of Freelance Editors vs. Mintly
- **Tweet 1 (Hook — 196 chars):**
  `Paying a freelance editor ₹30,000/mo for 15 Reels and 15 Carousels is normal. We broke down how to get 30 Reels + 30 Carousels a month for ₹1,499—without sacrificing visual quality 🧵` *(Attach pricing + reel comparison screenshot)*
- **Tweet 2:** Where agency/freelance hours actually go: 35% researching trending topics, 35% formatting slides & captions, 20% revisions over WhatsApp, 10% manual uploads.
- **Tweet 3:** Mintly automates the 90% grunt work and leaves you the only job that matters: 10 seconds of editorial taste inside Telegram.
- **Tweet 4:** Even better: every Reel pairs with a cheat-sheet Carousel (or 12s Image Reel). Reels bring cold reach; cheat sheets drive saves & follows.
- **Tweet 5 (CTA + Link):** Founding Starter is ₹899/mo for the first 3 months this week only. Bookmark this breakdown or grab a Founding spot → `[mintly-link]?utm_source=x&utm_campaign=jan1_t2`

#### Thread 3: The Hinglish Distribution Moat
- **Tweet 1 (Hook — 214 chars):**
  `English-only tech Reels leave 70% of India's developer audience on the table. Pure Hindi slides look unnatural for code. Here's the Hinglish content format that beats both 🧵` *(Attach side-by-side Hinglish Reel clip)*
- **Tweet 2:** Real Indian developers don't say *"डेटाबेस कैशिंग प्रणाली"*—they say *"Socho har request seedha database pe jaaye toh kya hoga?"*
- **Tweet 3:** So in Mintly, Hinglish mode keeps **all slides, code blocks, and captions in crisp English**, while the spoken voiceover explains the concept in natural Hinglish (Madhur or Swara voices).
- **Tweet 4:** Result: global-looking visual aesthetic + local voice retention that hooks Indian builders in the first 2 seconds.
- **Tweet 5 (CTA + Link):** You can toggle English or Hinglish per post right from the Generate screen. What niche should we add Hinglish voices to next? Reply below. Link → `[mintly-link]?utm_source=x&utm_campaign=jan1_t3`

#### Thread 4: Animated Code Walkthroughs (Why Static Text Reels Die)
- **Tweet 1 (Hook — 189 chars):**
  `Static "5 AI tools you need" reels get scrolled past in 0.8 seconds. Animated step-by-step diagrams hold viewers to the final loop. Here's the 18-second Reel structure we baked into Mintly 🧵` *(Attach GIF of Mintly array/linked-list animation)*
- **Tweet 2:** Seconds 0–3: Negative Command or Counter-Intuitive hook (*"Stop using arrays for this..."*).
- **Tweet 3:** Seconds 3–13: Visual walkthrough—pointers glide across cells, nodes highlight step by step, one narrated sentence per state change.
- **Tweet 4:** Seconds 13–18: Architecture shift + loop bridge straight into the comment CTA for the cheat sheet.
- **Tweet 5 (CTA + Link):** Mintly renders these 1080×1920 MP4s automatically for DSA, System Design, and AI topics—with more niches coming in Q1. Grab a Founding spot → `[mintly-link]?utm_source=x&utm_campaign=jan1_t4`

#### Thread 5 (Pre-Launch Dec 30): Build-in-Public Postmortem
- **Tweet 1 (Hook — 205 chars):**
  `50 days ago we had an internal script posting twice a day to @codexonebyhitesh. On Jan 1 we launch Mintly publicly. Here are the 4 hardest engineering bugs we fixed so creators never lose a post 🧵`
- **Tweet 2:** 1) Per-platform retry isolation: if Instagram succeeds and YouTube fails, retrying never double-posts to Instagram.
- **Tweet 3:** 2) 36-hour draft expiry + Telegram feedback steering: stale news never auto-publishes days late.
- **Tweet 4:** 3) Topic deduplication across HN/Reddit/arXiv/GitHub so your audience never sees the same explanation twice.
- **Tweet 5 (CTA + Link):** Doors open Jan 1 with 100 Founding Creator spots. Join the waitlist or drop a question below—I'll reply to everyone → `[mintly-link]?utm_source=x&utm_campaign=dec30_t5`

### 6B. Reddit Organic Value-Post Strategy (Zero-Ban Rules)
- **Golden Rule:** Never drop a bare promotional link or "Check out my SaaS!" title. Lead with a full breakdown, code/workflow teardown, or real numbers; mention Mintly once naturally at the bottom ("We packaged this into Mintly, launching Jan 1—happy to answer questions here").
- **Target Subreddits & Exact Angles:**
  1. `r/developersIndia` (Week 3 + Jan 1): *"How we got Hinglish TTS to pronounce English engineering terms cleanly without weird phonetic glitches (Devanagari + Latin script prompt trick)"* — genuine technical insight from `hinglish-narration-plan.md`.
  2. `r/SaaS` & `r/SideProject` (Dec 30 & Jan 1): *"Why we put a mandatory Telegram Approve button in front of our AI social pipeline (and why 1-click auto-posting hurts creator retention)"*.
  3. `r/InstagramMarketing` & `r/NewTubers` (Week 3 & Week 6): *"Data from pairing 18s vertical walkthrough Reels with 6-slide cheat-sheet Carousels on the same topic"* — share real `@codexonebyhitesh` learnings.

### 6C. Agentic SEO & Generative Engine Optimization (GEO) Blueprint (`agentic-seo-geo`)
Target 4 high-intent landing pages under `/use-cases/*` or `/compare/*` before Dec 15 so Google AI Overviews, Perplexity, and ChatGPT Search cite Mintly by Jan 1:
1. `/automate-instagram-reels-and-carousels` — *"Automated Instagram Reels & Carousel Generator with Telegram Approval"*
2. `/youtube-shorts-scheduler-for-tech-creators` — *"Auto-Publish Animated Tech Walkthroughs to Instagram & YouTube Shorts"*
3. `/hinglish-ai-reel-generator` — *"Hinglish Voiceover Reels with English Slides for Indian Creators"*
4. `/mintly-vs-freelance-video-editors` — *"Mintly vs. Hiring a Short-Form Video Editor (2027 Cost Breakdown)"*

**On-Page GEO Rules for Every Page:**
- Place a **40–60 word direct-answer summary** right under every `H2` (e.g., *"What is Mintly?"*, *"How does Telegram approval work?"*).
- Include a **Comparative Markdown/HTML Table** with exact quotas and INR prices (`Lite ₹699`, `Starter ₹1,499`, `Creator ₹2,999`, `Pro ₹5,999`) so AI answer engines lift exact numbers.
- Inject **JSON-LD Schema** on marketing pages: `Organization` (`Anjanex Labs`), `SoftwareApplication` (`Mintly`, `operatingSystem: Web`, `applicationCategory: MultimediaApplication`), `Product` + `Offer` (INR tiers), and `FAQPage`.

### 6D. "Made with Mintly" Viral Watermark & Affiliate Loop Math

#### Watermark Growth Loop (Lite & Starter / Free Trial)
- **Mechanism:** Optional subtle footer pill (`Generated with Mintly · mintly.app`) on Carousel Slide 1/Last Slide corner and optional end-card tag on Trial/Lite outputs (removable on **Creator** & **Pro** plans).
- **Loop Math (Conservative 30-Day Model):**
  - `100` active Starter/Trial creators × `30` posts/mo = `3,000` published posts/mo.
  - Avg. `1,200` views/post = `3,600,000` monthly impressions carrying subtle attribution.
  - `0.04%` profile/bio/search lookup rate (`4` lookups per `10,000` views) = `1,440` organic branded visits/mo.
  - `12%` visitor-to-signup × `20%` signup-to-paid = **`34` zero-CAC new paid customers/month** (`K-factor ≈ 0.34` compounding from product usage alone).

#### Creator Affiliate Program (`25% Recurring for 12 Months`)
- **Structure:** Any active user or seeded tech/creator affiliate gets a unique referral link (`?ref=<handle>`).
- **Payout:** **25% recurring commission** for 12 months on every referred Creator (`₹750/mo` payout on `₹2,999` plan) or Pro (`₹1,500/mo` payout on `₹5,999` plan). Minimum payout threshold `₹2,000` via UPI/bank transfer after 30-day refund window.
- **Trigger:** Surface *"Refer 4 Creator friends → your own Creator plan is effectively free"* directly inside the Billing & Dashboard footer after a user's **3rd approved post** (peak delight moment).

### 6E. PostHog Event Taxonomy, UTM Standard & 50-Day North-Star KPIs

**Standard UTM Schema:** `?utm_source={x|ph|reddit|youtube|ig|email|affiliate}&utm_medium={social|organic|cold|lifecycle}&utm_campaign={jan1_launch|founding_7d|agency_q1}&utm_content={thread1|reel_demo}`

**Core PostHog Funnel Events:**
1. `landing_viewed` (`utm_*`, `ref`)
2. `waitlist_submitted` (`niche`, `language`)
3. `signup_completed` (`auth_method: google|password`)
4. `telegram_connected` (critical Time-to-Value gate)
5. `first_generation_started` (`language: en|hi`, `post_format: carousel|image_reel`)
6. `first_post_approved` (North-Star Activation event)
7. `checkout_started` → `subscription_activated` (`plan_id`, `interval: month|year`, `promo_code`)

**Launch Targets (Nov 12, 2026 → Jan 7, 2027):**

| Metric | Pre-Launch Target (By Dec 31) | Launch Week Target (Jan 1 – Jan 7) |
| :--- | :--- | :--- |
| **Waitlist Leads** | `1,000+` verified emails | — |
| **Product Hunt Rank** | — | Top 5 Product of the Day |
| **Activated Creators (`first_post_approved`)** | `25` beta creators | `200+` activated accounts |
| **Paid Self-Serve Subscribers** | `10` early beta conversions | `75–100` Founding Creators (`~₹1.5L–₹2.2L MRR`) |
| **Agency Pilots Closed** | `3` paid pilots | `5` Agency Pod/Studio retainers (`~₹1.0L–₹1.5L MRR`) |
| **Total Launch MRR Target** | — | **`₹2.5L – ₹3.7L MRR`** (`~$3,000 – $4,400/mo`) |
