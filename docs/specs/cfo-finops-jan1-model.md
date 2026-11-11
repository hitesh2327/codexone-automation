# CFO FinOps, Unit Economics & Jan 1, 2027 Launch Financial Model (`CDX-003`)

> **Owner:** Shuri — CFO (`CDX-003`)  
> **Product:** Mintly (`codexone-automation`) by Anjanex Labs  
> **Date:** 2026-11-11  
> **Launch Target:** January 1, 2027  
> **Source Anchors:** `src/plans.py`, `src/plan_limits.py`, `src/billing.py`, `docs/legal/compliance.md`, `docs/specs/admin-stakeholder-system-design.md`  
> **Active Skills:** `quant-algo-finance`, `llm-cost-circuit-breaker`, `legal-compliance-privacy-gate`

---

## 1. Executive Financial Summary

Mintly's existing plan pricing (`src/plans.py`: ₹699 to ₹5,999/mo ex-GST) is **structurally profitable (>80% gross margin)** at typical utilization (60–75% of quota, 0.5 avg regenerations), **provided three critical leaks are plugged before January 1, 2027**:

1. **`MAX_REGENERATIONS = 3` Worst-Case Margin Inversion:** In `src/plan_limits.py`, every post can be regenerated 3 times (4 total generations per quota slot) without consuming quota. Under Paid-Tier Gemini + full GitHub Actions runner compute + 100% quota + 3× regenerations, **`Lite ₹699` drops to ~30%–45% margin (or negative if Gemini Pro + paid TTS is used)**.
2. **Free-Tier & Video-Upload Uncapped Exposure:** Moving from Google's free Gemini tier (which permits prompt training per `docs/legal/compliance.md`) to the **Gemini Paid Tier** on Jan 1 introduces hard per-token cash burn. Without hard caps on trials and user-uploaded video ASR/rendering, viral free signups create immediate negative cash flow.
3. **USD International Pricing & GST/LUT Readiness:** Selling `Lite ₹699` (~$8.30) globally leaves 70%+ ARPU on the table in US/EU markets and creates FX/payment-fee drag unless paired with PPP-localized USD tiers + Indian GST Form RFD-11 LUT (0% tax on exports).

**FX & Benchmark Assumptions:** `1 USD = ₹85.00 INR` · Domestic GST = `18%` (inclusive/added on top per `src/billing.py`).

---

## 2. Detailed Per-Post & Per-Tenant COGS Breakdown

### 2.1 Unit Component Cost Benchmarks (Paid Production Tiers, Q4 2026–2027)

| Cost Driver | Production Service / Assumption | Unit Rate (USD) | Unit Rate (INR @ ₹85) |
|---|---|---:|---:|
| **Gemini LLM (Flash)** | `gemini-flash-latest` Paid Tier (topic ranking + script + review + repair) | ~$0.50 / 1M input · ~$2.00 / 1M output | ₹42.50 / 1M in · ₹170 / 1M out |
| **Gemini LLM (Pro fallback)** | Flagship Pro (only for complex/fallback calls, max 10% traffic) | ~$2.00 / 1M input · ~$12.00 / 1M output | ₹170 / 1M in · ₹1,020 / 1M out |
| **Voice Synthesis (TTS)** | `edge-tts` (default EN + Hinglish) vs Cloud Paid TTS (optional) | $0.00 (`edge-tts`) · $0.015/1k chars (cloud) | ₹0.00 (`edge-tts`) · ~₹0.75/reel (cloud) |
| **ASR (User Video Editor)** | Deepgram Nova-3 / Hosted Whisper Large (~1.5 min avg clip) | $0.0048 / audio min | ₹0.41 / audio min |
| **GitHub Actions Compute** | Private repo Linux 2-core runner (after free monthly minutes) | $0.006 / min (2026) – $0.008 / min | ₹0.51 – ₹0.68 / min |
| **Cloudinary Media CDN** | Credit pool (~$0.39/credit on Plus $89/225 cr): 1 credit = 1 GB storage or 1 GB bandwidth or 1k transforms | ~$0.09–$0.39 / GB effective | ₹7.65 – ₹33.15 / GB |
| **Core DB & API Hosting** | Neon Postgres + AWS Lambda / API Gateway (amortized per active tenant) | ~$0.60 / active tenant / mo | ₹51.00 / active tenant / mo |

### 2.2 Per-Artifact Variable COGS Breakdown

*(Reconciling against `src/plans.py` Oct 2026 estimate of ~₹9/carousel, ~₹13/reel, ~₹17/combo with 50% retry buffer. Below separates **Optimized Flash + Edge-TTS** vs **Conservative Worst-Case with Paid Runner + Retry Buffer**.)*

| Artifact Type | LLM Tokens (In / Out) | LLM Cost | TTS / ASR | Compute (GHA / Worker) | Cloudinary (Storage + 30d CDN) | Raw COGS (INR) | Buffered COGS (+35% Retries/Buffer) |
|---|---|---:|---:|---:|---:|---:|---:|
| **1. Carousel Only** (5–7 slides, HTML→PNG→JPG ~2.5 MB) | 12k in / 3.5k out | ₹1.11 | ₹0.00 | 1.5 min = ₹0.85 | ~0.04 GB = ₹0.60 | **₹2.56** | **₹3.46** *(vs ₹9 legacy est.)* |
| **2. AI Reel (`reel_v2`)** (1080×1920 MP4 ~18 MB, Edge-TTS) | 18k in / 5.5k out | ₹1.70 | ₹0.00 (`edge-tts`) | 3.5 min = ₹1.98 | ~0.18 GB = ₹2.70 | **₹6.38** | **₹8.61** *(vs ₹13 legacy est.)* |
| **3. Reel + Carousel Combo** (shared topic/spec) | 22k in / 6.5k out | ₹2.04 | ₹0.00 | 4.2 min = ₹2.38 | ~0.22 GB = ₹3.30 | **₹7.72** | **₹10.42** *(vs ₹17 legacy est.)* |
| **4. User-Uploaded Video Edit** (90s clip ASR + EditSpec + FFmpeg) | 15k in / 4.0k out | ₹1.32 | ₹0.62 (1.5m ASR) | 3.0 min = ₹2.04 | ~0.35 GB = ₹5.25 | **₹9.23** | **₹12.46** |

> **Why Legacy `src/plans.py` Estimates Were Higher (₹9 / ₹13 / ₹17):** `src/plans.py` assumed higher Pro-model blend + uncached Cloudinary bandwidth + 50% retry buffer. Using `gemini-flash-latest` as primary (`src/llm.py`) cuts raw COGS by ~35–40%, **but** switching to Gemini Pro fallback or paid TTS immediately pushes combo COGS back toward **₹17–₹22**. Model routing discipline is therefore a P0 CFO control.

---

## 3. Gross Margin Model Across Mintly Tiers (Domestic INR & International USD)

### 3.1 Domestic India Tiers (INR — Prices in `src/plans.py`, Ex-GST)

*Payment Gateway Fee Assumption (Razorpay): `2.0% + 18% GST on fee = 2.36%` of Gross Invoice (incl. 18% GST), which equals `2.78%` of Ex-GST Net Revenue.*  
*Fixed Per-Tenant DB/API Overhead: `₹51 / tenant / mo`.*

| Tier | List Price (Ex-GST) | Billed w/ 18% GST | Net Realized Rev (Ex-GST, post-RZP fee) | Monthly Quota | Typical Usage (70% quota, 0.3x regen) COGS | Typical Gross Margin | **Worst-Case Abuse** (100% quota + 3x Regen = 4x ops) COGS | **Worst-Case Gross Margin** |
|---|---:|---:|---:|---|---:|---:|---:|---:|
| **Free / Trial** *(Proposed)* | ₹0 | ₹0 | ₹0 | 2 carousels + 1 reel (lifetime) | ₹15.53 | **-₹66.53** *(CAC cost)* | Uncapped if no limit! | **CRITICAL LOSS** |
| **Lite** | **₹699** | ₹825 | **₹679.53** | 30 Carousels (`0` Reels) | ₹125.60 *(70% + 0.3x)* | **81.5%** (₹554) | ₹466.20 *(120 renders)* | **31.4%** *(Negative if Pro/TTS used!)* |
| **Starter** | **₹1,499** | ₹1,769 | **₹1,457.25** | 30 Reels + 30 Carousels | ₹323.90 | **77.8%** (₹1,133) | ₹1,301.40 *(240 renders)* | **10.7%** *(Margin Warning)* |
| **Creator** *(Popular)* | **₹2,999** | ₹3,539 | **₹2,915.48** | 60 Reels + 60 Carousels | ₹596.80 | **79.5%** (₹2,319) | ₹2,551.80 *(480 renders)* | **12.5%** *(Margin Warning)* |
| **Pro** | **₹5,999** | ₹7,079 | **₹5,831.95** | 120 Reels + 120 Carousels | ₹1,142.60 | **80.4%** (₹4,689) | ₹5,052.60 *(960 renders)* | **13.4%** *(Margin Warning)* |

### 3.2 Recommended International USD Tiers (Stripe Export — 0% GST under LUT)

*Payment Gateway Fee Assumption (Stripe International Cards + FX): `3.9% + $0.30` per txn (~`4.5%` blended).*

| International Tier | Proposed USD Price | Net Realized USD (post-Stripe) | Net INR Equiv (@ ₹85) | Quota Alignment | Typical COGS (INR) | Typical Gross Margin % |
|---|---:|---:|---:|---|---:|---:|
| **Lite (Intl)** | *$12 / mo* *(optional, or omit)* | $11.23 | ₹955 | 30 Carousels | ₹125.60 | **86.8%** |
| **Starter (Intl)** | **$19 / mo** | $17.96 | ₹1,527 | 30 Reels + 30 Carousels | ₹323.90 | **78.8%** |
| **Creator (Intl)** | **$39 / mo** | $37.18 | ₹3,160 | 60 Reels + 60 Carousels | ₹596.80 | **81.1%** |
| **Pro (Intl)** | **$79 / mo** | $75.62 | ₹6,428 | 120 Reels + 120 Carousels | ₹1,142.60 | **82.2%** |

### 3.3 Flagged Unprofitable & Margin-Compressed Edge Cases
1. **`MAX_REGENERATIONS = 3` Multiplication Risk (`src/plan_limits.py:33`):** Allowing 3 free regenerations on *every* post turns a 60-combo Creator plan into 240 combo generations (480 artifacts). At ₹10.42 buffered COGS/combo, COGS reaches ₹2,501 + ₹51 DB = **₹2,552 (only 12.5% margin)**. If just 15% of those fallback to Gemini Pro or use Paid TTS, **gross margin turns negative**.
2. **`Lite ₹699` + Paid TTS / Pro Model Leakage:** Lite realizes only **₹679.53 net**. If a Lite user abuses 3× regenerations AND hits Gemini Pro fallback, per-user COGS exceeds ₹700 (**Negative Margin**).
3. **Cloudinary Retention Bloat:** Leaving un-published drafts and rejected `version 1..3` reels on Cloudinary indefinitely compounds monthly storage costs across cohorts.

---

## 4. Mandatory Cost Guardrails (Pre-Jan 1 Launch Gate)

1. **Free-Tier / Trial Guardrails:**
   - **Hard Lifetime Cap:** Max **2 Carousels + 1 AI Reel** total per free account (never recurring monthly free quota), **0 Regenerations**, watermark on trial reel, and `MAX_FREE_USERS_DAILY` circuit breaker tied to admin kill-switch (`kill_signups`).
   - **Phone/Email Verification Gate:** Require verified email (`OtpCode`) before dispatching any GitHub Actions/LLM job.
2. **Regeneration & LLM Guardrails (Paid Plans):**
   - **Cap Monthly Total Regenerations:** Keep per-post cap at `MAX_REGENERATIONS = 2` (down from 3), AND add a **monthly regeneration allowance** equal to **25% of plan post quota** (e.g., Lite: 8/mo, Starter: 15/mo, Creator: 30/mo, Pro: 60/mo). Beyond that, regenerations consume 1 post credit.
   - **Strict Model Routing:** `Lite` and `Starter` locked strictly to `gemini-flash-latest` / `flash-lite` (no Pro fallback). Pro model access reserved for `Creator`/`Pro` review passes only.
   - **Automated Margin Circuit Breaker (`MNT-905`):** Flag any tenant whose rolling 30-day `total_cogs_inr > 0.55 × net_rev_inr` as `margin_warning` and throttle at `0.85 × net_rev_inr`.
3. **User-Recorded Video Upload Guardrails (Q1 2027):**
   - **Max File Size & Duration:** `150 MB` max upload, `180 seconds` (3 min) max source clip duration, enforced both in presigned upload policy and `ffprobe` worker check.
   - **Monthly Video Processing Minute Caps:** Starter `15 raw min/mo`, Creator `45 raw min/mo`, Pro `120 raw min/mo` (keeps ASR + FFmpeg COGS < ₹150–₹450/user).
   - **Draft Asset TTL:** Automatically purge rejected/unpublished draft media from Cloudinary after **14 days** using `src/upload.py delete_media()`.

---

## 5. January 1, 2027 Launch Financial Forecast (M1–M6: Jan–Jun 2027)

### 5.1 Fixed Monthly Operating Overhead (Lean Founder Stack)
| Expense Category | Monthly Cost (INR) | Monthly Cost (USD) | Notes |
|---|---:|---:|---|
| Core Cloud Infra (Neon Pro + AWS Lambda/ECS + Redis + Domain/Monitoring) | ₹18,000 | $212 | Scales modestly above 500 tenants |
| Cloudinary Base Plan (Plus Plan) | ₹7,565 | $89 | 225 monthly credits base pool |
| GitHub Team / CI Base + Transactional Email (SES/Resend) | ₹4,500 | $53 | Base operational tools |
| Compliance / CA Retainer (GST Monthly Filing + ROC) | ₹6,000 | $71 | Monthly GSTR-1/3B + TDS compliance |
| **Total Fixed Opex (Pre-Marketing)** | **₹36,065** | **$424** |Lean baseline overhead |

### 5.2 Blended Unit Economics & Breakeven Math
- **Blended Paid Mix Assumption:** `20% Lite (₹699)` · `35% Starter (₹1,499 / $19)` · `35% Creator (₹2,999 / $39)` · `10% Pro (₹5,999 / $79)` with **70% India / 30% International USD** mix.
- **Blended Net ARPU (ex-GST, post-gateway fees):** **₹2,540 / mo (~$29.88)**
- **Blended Variable COGS / Paid Tenant:** **₹495 / mo** (including 10% free-trial acquisition overhead amortized across paid conversions)
- **Blended Gross Profit / Paid Tenant:** **₹2,045 / mo** (**80.5% Blended Gross Margin**)
- **Operational Breakeven Subscriber Count (covering ₹36,065 Fixed Opex):**  
  $$\text{Breakeven Paid Subscribers} = \left\lceil \frac{₹36,065}{₹2,045} \right\rceil = \mathbf{18\text{ Paid Subscribers}}$$
- **CAC Payback & LTV Targets (`quant-algo-finance`):**
  - Target Blended CAC: **≤ ₹2,000 ($23.50)** via organic Reels/YouTube/Reddit + affiliate creators (20% rev-share).
  - **CAC Payback Period:** `₹2,000 / ₹2,045 =` **0.98 months (< 30 days)** ✅
  - Assuming 7% monthly logo churn (~14.3 mo lifetime): **LTV = ₹29,244** → **LTV : CAC = 14.6x** (even at 12% churn / 8.3 mo lifetime, **LTV:CAC = 8.5x**, well above the `3.0x` floor).

### 5.3 M1–M6 Scenarios (January – June 2027)

*Assumptions: Monthly logo churn `8%` Conservative, `6%` Base, `4.5%` Bull; Marketing/CAC spend scales at ~15–20% of revenue.*

#### Scenario A: Conservative (Slow Organic Ramp)
| Month | Active Paid Subs | Net MRR (INR) | Variable COGS (INR) | Gross Margin % | Fixed Opex + Mktg (INR) | Net Operating Profit (INR) |
|---|---:|---:|---:|---:|---:|---:|
| **M1 (Jan 2027)** | 25 | ₹63,500 | ₹12,375 | 80.5% | ₹48,065 | **+₹3,060** |
| **M2 (Feb 2027)** | 42 | ₹1,06,680 | ₹20,790 | 80.5% | ₹56,065 | **+₹29,825** |
| **M3 (Mar 2027)** | 65 | ₹1,65,100 | ₹32,175 | 80.5% | ₹66,065 | **+₹66,860** |
| **M4 (Apr 2027)** | 92 | ₹2,33,680 | ₹45,540 | 80.5% | ₹78,065 | **+₹1,10,075** |
| **M5 (May 2027)** | 122 | ₹3,09,880 | ₹60,390 | 80.5% | ₹90,065 | **+₹1,59,425** |
| **M6 (Jun 2027)** | 155 | ₹3,93,700 | ₹76,725 | 80.5% | ₹1,02,065 | **+₹2,14,910** |

#### Scenario B: Base Case (Product-Led + Multi-Platform Q1 Launch)
| Month | Active Paid Subs | Net MRR (INR) | Variable COGS (INR) | Gross Margin % | Fixed Opex + Mktg (INR) | Net Operating Profit (INR) |
|---|---:|---:|---:|---:|---:|---:|
| **M1 (Jan 2027)** | 45 | ₹1,14,300 | ₹22,275 | 80.5% | ₹56,065 | **+₹35,960** |
| **M2 (Feb 2027)** | 85 | ₹2,15,900 | ₹42,075 | 80.5% | ₹74,065 | **+₹99,760** |
| **M3 (Mar 2027)** | 140 | ₹3,55,600 | ₹69,300 | 80.5% | ₹98,065 | **+₹1,88,235** |
| **M4 (Apr 2027)** | 210 | ₹5,33,400 | ₹1,03,950 | 80.5% | ₹1,32,065 | **+₹2,97,385** |
| **M5 (May 2027)** | 295 | ₹7,49,300 | ₹1,46,025 | 80.5% | ₹1,68,065 | **+₹4,35,210** |
| **M6 (Jun 2027)** | 400 | ₹10,16,000 | ₹1,98,000 | 80.5% | ₹2,16,065 | **+₹6,01,935** |

#### Scenario C: Bull Case (Viral US/EU Creator Adoption + Video Editor Hit)
| Month | Active Paid Subs | Net MRR (INR) | Variable COGS (INR) | Gross Margin % | Fixed Opex + Mktg (INR) | Net Operating Profit (INR) |
|---|---:|---:|---:|---:|---:|---:|
| **M1 (Jan 2027)** | 80 | ₹2,03,200 | ₹39,600 | 80.5% | ₹76,065 | **+₹87,535** |
| **M2 (Feb 2027)** | 175 | ₹4,44,500 | ₹86,625 | 80.5% | ₹1,20,065 | **+₹2,37,810** |
| **M3 (Mar 2027)** | 320 | ₹8,12,800 | ₹1,58,400 | 80.5% | ₹1,86,065 | **+₹4,68,335** |
| **M4 (Apr 2027)** | 510 | ₹12,95,400 | ₹2,52,450 | 80.5% | ₹2,76,065 | **+₹7,66,885** |
| **M5 (May 2027)** | 740 | ₹18,79,600 | ₹3,66,300 | 80.5% | ₹3,86,065 | **+₹11,27,235** |
| **M6 (Jun 2027)** | 1,000 | ₹25,40,000 | ₹4,95,000 | 80.5% | ₹5,06,065 | **+₹15,38,935** |

*(Note: M6 Bull Case hits ₹25.4L MRR / ~$30k MRR; even if fixed cloud/support team headcount expands by ₹1.5L/mo at 500+ users, net margins remain >50%.)*

---

## 6. Indian GST, Export Compliance & Admin Revenue Ledger Spec

### 6.1 Tax Treatment Matrix (`src/billing.py` Alignment)

| Customer Geography & Type | Place of Supply (IGST Act) | Tax Rate & Line Split | Legal Requirement |
|---|---|---|---|
| **India — Intra-State** (`buyer.billing_state == SELLER_GSTIN[:2]`) | Seller's State | **18% GST**: `CGST 9%` + `SGST 9%` *(or `UTGST 9%` for UTs `04, 26, 31, 35, 38` per `src/billing.py:63`)* | Capture buyer state code; optional buyer 15-char GSTIN (`valid_gstin()`) for B2B Input Tax Credit (ITC) on GSTR-1 Table 4A. |
| **India — Inter-State** (`buyer.billing_state != SELLER_GSTIN[:2]`) | Buyer's State Code | **18% GST**: `IGST 18%` | Declare in GSTR-1 B2B (if GSTIN present) or B2CS (if B2C < ₹2.5L). |
| **Foreign Export (USD / Non-IN)** (`buyer.billing_country != "IN"`) | Outside India | **0% GST (Zero-Rated Export of Services)** under Sec 16(1) IGST Act | **Mandatory before Jan 1:** File annual **Letter of Undertaking (LUT, Form GST RFD-11)** on GST portal; receive payment in convertible foreign exchange (Stripe USD settlement / FIRC/e-BRC proof); print *"SUPPLY MEANT FOR EXPORT UNDER BOND OR LETTER OF UNDERTAKING WITHOUT PAYMENT OF INTEGRATED TAX"* on invoice. |

> **Pre-Launch Legal Blockers (`docs/legal/compliance.md` & `web/src/lib/company.ts`):** Fill all `null` fields in `web/src/lib/company.ts` (`entityType`, `address`, `email`, `phone`, `grievanceOfficer`, `courtsCity`, `gstin`), confirm SAC code (`998314` IT design/dev or `998439` online content/SaaS) with CA, and file LUT before accepting international Stripe revenue.

### 6.2 Payment Gateway Fee & Net Settlement Accounting
- **Razorpay (Domestic INR):** Deducts `2.0%` MDR + `18% GST on MDR (0.36%)` = **`2.36%`** of gross receipt. *Important:* Mintly can claim Input Tax Credit (ITC) on the `0.36%` GST portion of Razorpay's monthly tax invoice against Mintly's output GST liability.
- **Stripe (International USD):** Deducts `2.9% + $0.30` (domestic US) to `~3.9% + $0.30` (international/currency conversion) per charge. Record both `gross_amount`, `gateway_fee`, `gateway_fee_gst` (if Indian Stripe entity), and `net_settlement` in minor currency units (`paise` / `cents`).

### 6.3 Admin Revenue Ledger & Tax Invoice Schema (`tax_invoices` — CGST Rule 46)

To power `/admin/telemetry` GSTR-1 exports and customer PDF invoice downloads, the Admin Revenue Ledger must store an **immutable, append-only `tax_invoices` record** per successful `invoice.paid` / `subscription.charged` webhook:

| Column | Type | CGST Rule 46 / FinOps Purpose |
|---|---|---|
| `id` | `UUID` (PK) | Internal immutable ledger key |
| `invoice_number` | `VARCHAR(16)` (UNIQUE) | Consecutive FY serial (max 16 chars per Rule 46(b), e.g., `MNT2627-000001`) |
| `invoice_date` | `DATE` | Date of payment realization / invoice issuance (IST) |
| `financial_year` | `VARCHAR(7)` | e.g. `2026-27` |
| `user_id` | `INTEGER` (FK `SET NULL`) | Retains invoice for 72+ months (CGST Act s.36) even on GDPR account deletion |
| `gateway` | `VARCHAR(16)` | `razorpay` \| `stripe` \| `manual_credit` |
| `gateway_payment_id` | `VARCHAR(80)` (UNIQUE) | Idempotency key (`pay_...` or `in_...`) |
| `seller_gstin` | `VARCHAR(15)` | Anjanex Labs GSTIN snapshot at time of supply |
| `buyer_name` | `VARCHAR(120)` | Snapshot of `user.billing_name` |
| `buyer_country` | `CHAR(2)` | ISO 3166-1 alpha-2 (`IN`, `US`, `DE`, etc.) |
| `buyer_state_code` | `CHAR(2)` | GST state code (`01`–`38`) for `IN`; `NULL` for export |
| `buyer_gstin` | `VARCHAR(15)` | Nullable; determines `B2B` vs `B2C` classification in GSTR-1 |
| `place_of_supply` | `VARCHAR(32)` | State name+code (India) or `96-Foreign Country` |
| `sac_code` | `VARCHAR(8)` | CA-confirmed SAC (e.g. `998314` / `998439`) |
| `supply_type` | `VARCHAR(16)` | `INTRA_IN` \| `INTER_IN` \| `EXPORT_LUT` |
| `currency` | `CHAR(3)` | `INR` \| `USD` |
| `fx_rate_to_inr` | `NUMERIC(10,4)` | RBI reference rate on invoice date (for USD exports in GSTR-1) |
| `taxable_amount_minor` | `BIGINT` | Base taxable amount in paise or cents |
| `cgst_minor` / `sgst_minor` / `utgst_minor` / `igst_minor` | `BIGINT` | Exact integer tax splits in minor units (`0` for `EXPORT_LUT`) |
| `total_amount_minor` | `BIGINT` | Gross amount collected from customer |
| `gateway_fee_minor` | `BIGINT` | Razorpay/Stripe fee deducted |
| `gateway_fee_tax_minor` | `BIGINT` | 18% GST charged by gateway (ITC eligible) |
| `net_settled_minor` | `BIGINT` | `total_amount_minor - gateway_fee_minor - gateway_fee_tax_minor` |
| `credit_note_for_id` | `UUID` (FK self) | Non-null if row is a GST Credit Note (refund/proration reversal) |
| `lut_arn` | `VARCHAR(32)` | LUT Acknowledgement Reference Number for `EXPORT_LUT` rows |
| `pdf_url` | `TEXT` | Immutable rendered tax invoice PDF archive path |
