# Mintly (Anjanex Labs): legal and platform compliance checklist

Status as of 22 Oct 2026. This is an engineering checklist, not legal advice: have a lawyer and a CA review the
policies and the open items before taking real payments.

Legend: **Done** = in the product and the policies. **Partial** = covered in part. **Open** = not done yet.

## 1. Indian law

| Requirement | Source | Status | Notes |
|---|---|---|---|
| Publish legal name, address, contact and grievance officer | Consumer Protection (E-Commerce) Rules 2020, IT Rules 2011 | **Partial** | Pages built (`/legal/contact`); entity type, registered address, email, phone and grievance officer still to be filled in `web/src/lib/company.ts` |
| Acknowledge complaints within 48 hours, resolve within 1 month | E-Commerce Rules 2020 | **Partial** | Promised on `/legal/contact`; needs a monitored inbox and a ticket number per complaint |
| Clear refund and cancellation terms; no refusing refunds for deficient service | E-Commerce Rules 2020, Consumer Protection Act 2019 | **Done** | `/legal/refunds` |
| Privacy policy published; purpose of each use stated | IT Act 2000 s.43A + SPDI Rules 2011; DPDP Act 2023 | **Done** | `/legal/privacy` |
| DPDP consent notice: purpose-specific, plain language, withdraw as easily as give | DPDP Act 2023, DPDP Rules 2025 (phased in to May 2027) | **Partial** | Privacy policy covers it; sign-up shows a consent line linking Terms and Privacy. A separate itemised consent notice at sign-up and a consent log are still open |
| Rights: access, correction, erasure, grievance, nominee | DPDP Act 2023 | **Partial** | By email today; **no self-serve account deletion yet** (open, also needed for Meta/YouTube) |
| Children (under 18) need verifiable parental consent | DPDP Act 2023 | **Done** | Service limited to 18+ in the Terms |
| Reasonable security safeguards | IT Act s.43A, DPDP Act | **Done** | HTTPS, hashed passwords, encrypted integration tokens, signed payment webhooks, row locks |
| Breach notification to the Data Protection Board and users | DPDP Rules 2025 | **Open** | Needs an incident-response runbook |
| GST: charge 18% once registered; tax invoices with GSTIN, SAC, place of supply | CGST Act, Rule 46 | **Partial** | GST calculation built (Razorpay branch); GST invoices are roadmap item 9; SAC code to confirm with a CA |
| Exports of services at 0% under LUT | IGST Act s.16 | **Open** | File LUT once GST-registered |
| Recurring payments: e-mandate, pre-debit notice 24h before each charge | RBI e-mandate framework | **Partial** | Razorpay sends the notices (`customer_notify=1`); confirm once Subscriptions is enabled |
| Keep tax and invoice records | CGST Act s.36 (72 months), Companies Act (8 years) | **Done** | Stated in the privacy policy's retention section |

## 2. Platforms and payment providers

| Requirement | Who asks | Status | Notes |
|---|---|---|---|
| Terms, Privacy, Refund/Cancellation, Contact, Delivery pages on the website | Razorpay activation | **Done** | Delivery is a section of `/legal/refunds` (digital service, no shipping) |
| Own privacy policy saying what YouTube data is used; link YouTube ToS and Google Privacy Policy; how to revoke | YouTube API Services Developer Policies | **Done** | `/legal/privacy` section 8 |
| Don't keep YouTube data indefinitely; easy deletion | YouTube API Services Developer Policies | **Partial** | Deletion by email; self-serve deletion open |
| Data deletion instructions URL (or callback) | Meta Platform (Instagram API) | **Done** | `/legal/data-deletion` (instructions URL). A deletion callback is an option later |
| Privacy policy URL for Google Sign-In OAuth consent screen | Google | **Done** | `/legal/privacy` |
| Disclose that Gemini's free tier may use prompts to improve Google products | Gemini API terms | **Done** | `/legal/privacy` section 4; moving to the paid tier removes this |

## 3. Open items, in priority order

1. Fill in company details in `web/src/lib/company.ts` (removes the Draft notice).
2. Self-serve account deletion (DPDP erasure, Meta, YouTube).
3. GST invoices (roadmap item 9) and GST registration / LUT decisions with a CA.
4. Itemised consent notice at sign-up plus a consent record (DPDP Rules, by May 2027).
5. Incident-response runbook for breach notification.
6. Lawyer review of all four policies.
