# Future Enhancements Product Backlog (v2+ & Market Expansion)

> **Parent Epic:** `MNT-1900` (`MNT-1902`)  
> **Authors:** Vision (Business Analyst, `CDX-014`) & Nick Fury (Project Manager, `CDX-007`)  
> **Inputs:** `future_enhancements_roadmap.md`, `MNT-701..707`, and Sprint 2 Competitor & Market Whitespace Intelligence  
> **JIRA Sync Script:** `scratch/add_future_tickets.py` -> `Mintly JIRA Backlog` (`MNT-1910..1925`)

---

## 1. Purpose & Backlog Governance

While `MNT-701..707` captured high-level v2 epics, engineering cannot estimate or execute epic-sized rows without decomposed **Stories, Tasks, and Subtasks** with clear dependencies, scope gates, and readiness statuses:
- **`Ready`**: Fully scoped, dependencies clear (or sequenced cleanly behind Sprint 2 foundations), ready for Executive RICE/ARR ranking (`MNT-1903`).
- **`Need more Info`**: Requires explicit product/legal/vendor decision (e.g., Meta App Review permission scope, ElevenLabs vs Cartesia biometric SLA, agency pricing tier) before dev pickup.

---

## 2. Decomposed Ticket Registry (`MNT-1910..1925`)

| Key | Pillar / Market Gap | Type | Status | Priority | Owner | SP | Summary & Key Acceptance Boundary |
|---|---|---|---|---|---|---:|---|
| **MNT-1910** | **F1** Auto-Subtitles | Story | `Ready` | P1 | AI/Video Eng | 5 | **Resumable Chunked Video Upload & Word-Level ASR + Silence Map (`0-Credit Preview`)** — Presigned chunked upload (`.mp4/.mov/.webm`), `<15s` word-timestamp ASR + VAD silence markers, interactive transcript typo & cut editor before credit charge. |
| **MNT-1911** | **F1** Auto-Subtitles | Subtask | `Ready` | P1 | AI/Video Eng | 5 | **Kinetic Caption Preset Renderer & Free Post-Render Typo Fast Path** — Hormozi/Minimalist/Editorial subtitle styles, IG/YT safe-zone preview overlay, and 24h pre-burn intermediate cache for 0-credit caption-only typo patches. |
| **MNT-1912** | **F2** AI Prompt Editor | Story | `Ready` | P1 | AI/Video Eng | 8 | **2-Stage AI Prompt Enhancer / Refiner & Inspectable Edit Checklist (`EditSpec`)** — Converts vague prompts (*"make it punchy"*) into timestamped, toggleable Edit Checklist items (trims, zoom keyframes, SFX/music ducking) with Pydantic bounds validation before render. |
| **MNT-1913** | **F2** AI Prompt Editor | Subtask | `Ready` | P1 | AI/Video Eng | 5 | **Deterministic FFmpeg Edit Graph Compiler, Non-Destructive Versioning (`v1/v2`) & Auto-Refund** — Compiles approved `EditSpec` into FFmpeg filter graphs, verifies output via `ffprobe`, auto-refunds reserved quota on failure, and hands off to Mintly Approval Queue. |
| **MNT-1914** | **Market Gap** (Submagic/Captions) | Task | `Ready` | P1 | AI/Video Eng | 5 | **Context-Aware AI B-Roll Auto-Matcher & Safe-Zone Framing** — Matches transcript beat phrases to licensed stock/user B-roll clips (`Pexels`/`Pixabay` or user library) with subject-aware 9:16 smart crop and opt-out toggles in the Edit Checklist. |
| **MNT-1915** | **Market Gap** (OpusClip/Vizard) | Task | `Ready` | P2 | AI/Video Eng | 5 | **Long-Form Video / YouTube Link Hook Extractor ("Clip-to-Shorts")** — Paste a 15–60 min YouTube/podcast link or upload; scores top 3–5 self-contained 30–60s hooks with logical boundary protection (no awkward mid-sentence chops) + credit cap preview before extraction. |
| **MNT-1916** | **Market Gap** (Audio/Hook Quality) | Task | `Ready` | P2 | AI/Backend Eng | 3 | **Audio Clarity Enhancer & Pre-Publish Hook Scorer (`hookscore.py` v2)** — Optional 1-click voice denoise/loudness normalization (`-14 LUFS`) + pre-publish 3-second Hook & Retention Risk Score across both AI-generated and user-uploaded reels. |
| **MNT-1917** | **Market Gap** (Repurposing) | Story | `Ready` | P1 | Full-Stack Eng | 5 | **URL / Blog / PDF-to-Carousel & Reel Repurposer** — Drop a Substack article, blog URL, PDF whitepaper, or YouTube transcript -> SSRF-safe extract -> Mintly converts into a 5–7 slide carousel + companion reel script using user's `UserTaste`. |
| **MNT-1918** | **F3** Lead Capture | Story | `Need more Info` | P2 | Full-Stack Eng | 8 | **Instagram & Threads Comment-to-DM Keyword Automation (`ManyChat` Built-In)** — Per-post `automation_rules` (`GUIDE`, `LINK`), Meta `comments` webhook signature verification, jittered queue replies, and DM delivery. *Info needed: Meta App Review timeline for `instagram_manage_messages`.* |
| **MNT-1919** | **F4** Brand Kit Studio | Story | `Ready` | P2 | Full-Stack Eng | 5 | **Brand Kit & Custom Template Studio (`content_templates`)** — Upload brand logo (SVG/PNG), custom TTF/WOFF2 fonts, color tokens, and safe-zone watermark rules with live HTML/CSS canvas preview in `/config#brand-kit`. |
| **MNT-1920** | **F5** Voice Cloning | Story | `Need more Info` | P3 | AI/Backend Eng | 8 | **Consent-Gated Creator Voice Twin (`ElevenLabs` / `Cartesia`)** — Live spoken verification phrase biometric check, explicit biometric disclosure, and 1-click upstream + local voice clone purge. *Info needed: Vendor selection & legal biometric consent wording.* |
| **MNT-1921** | **F6** Localization | Story | `Ready` | P2 | AI/Backend Eng | 8 | **Multi-Language Dubbing & Localized Caption/Hashtag Pipeline** — Expand `GenerationJob.language` from `en|hi` to ISO 639-1 (`es`, `fr`, `de`, `pt`, `ja`, `ar`), preserving technical/code terms untranslated and syncing native TTS + translated IG/YT copy. |
| **MNT-1922** | **F7** Analytics Loop | Story | `Ready` | P2 | Data/AI Eng | 5 | **Closed-Loop Analytics Ingestion & ROI Dashboard (`platform_analytics`)** — Scheduled `+24h/+72h/+7d` insights collector (reach, saves, shares, watch time) + Creator ROI Hooks view showing top-converting categories and hook formulas. |
| **MNT-1923** | **F7** Analytics Loop | Subtask | `Ready` | P2 | Data/AI Eng | 3 | **Performance-Weighted `rank_topics.py` & `suggest-schedule` Feedback** — Inject per-tenant save/watch-time multipliers into `rank_topics.py` prompt context and ground AI schedule recommendations in actual follower peak hours. |
| **MNT-1924** | **Market Gap** (Agencies/Pro) | Story | `Need more Info` | P1 | Full-Stack Eng | 8 | **Multi-Workspace & Client Brand Switcher (Agency Mode)** — One Agency login manages 3–25 client workspaces (isolated `UserTaste`, `social_accounts`, `content_templates`, approval links, and client-branded review portals). *Info needed: Agency seat/workspace pricing tier.* |
| **MNT-1925** | **Market Gap** (Viral Growth) | Task | `Need more Info` | P2 | Full-Stack Eng | 5 | **Trending Audio / Format Radar & Public Share-to-Approve Link** — Surface niche-matched trending reel formats + 1-click passwordless expiring client approval link (for agency clients without Telegram/Mintly logins). *Info needed: Licensing stance on trending IG audio metadata.* |

---

## 3. Open Questions Requiring Executive / User Input (`Need more Info` Gate)

1. **`MNT-1918` (Comment-to-DM):** Should v1 launch for Instagram Comments first (bundled with `MNT-204` Meta App Review) or wait until Phase B OAuth is approved in production?
2. **`MNT-1920` (Voice Cloning):** Confirm preferred TTS cloning vendor (`ElevenLabs` vs `Cartesia`) and whether Voice Twin is gated exclusively to `Pro` / `Agency` tiers due to COGS and biometric compliance overhead.
3. **`MNT-1924` (Agency Multi-Workspace):** Confirm Agency tier pricing (e.g., ₹9,999/mo for 5 client workspaces vs per-brand seat add-on) before `Shuri` & `Reed Richards` lock workspace billing schema.
4. **`MNT-1925` (Public Approval Link):** Confirm whether client approval links should require a 4-digit PIN/OTP or signed expiring token only.
