/**
 * Mintly's legal pages: Terms, Privacy, Refunds and cancellations, Contact and grievances, Data deletion.
 *
 * Plain text with [link](href) and **bold**; LegalPage renders it. Keep each statement true to how the product
 * actually works (src/billing.py, src/plan_limits.py, the integrations): if the product changes, change this.
 * Drafted by engineering for review by a lawyer; see docs/legal/compliance.md.
 */
import { COMPANY, field } from "@/lib/company";

export type Block = string | { list: string[] };
export type Section = { id: string; title: string; body: Block[] };
export type LegalDoc = { slug: string; title: string; summary: string; sections: Section[] };

const P = COMPANY.product;
const FIRM = COMPANY.legalName;
const CONTACT = COMPANY.email ? `[${COMPANY.email}](mailto:${COMPANY.email})` : field("email");

const terms: LegalDoc = {
  slug: "terms",
  title: "Terms of service",
  summary: `The agreement between you and ${FIRM} for using ${P}.`,
  sections: [
    { id: "agreement", title: "Who we are and this agreement", body: [
      `${P} is a service of ${FIRM}, ${field("entityType")}, at ${field("address")} ("we", "us"). By creating an account or using ${P} you agree to these terms, the [privacy policy](/legal/privacy) and the [refund and cancellation policy](/legal/refunds).`,
      "You must be at least 18 years old and able to enter a binding contract. If you use Mintly for a business, you confirm you can accept these terms for it.",
    ]},
    { id: "service", title: "What Mintly does", body: [
      `${P} finds trending topics in your niche, writes and designs reels and carousels with AI, sends each one to you for approval on Telegram or the dashboard, and publishes **only the posts you approve** to the accounts you connect (Instagram, and YouTube Shorts on plans that include it).`,
      "AI-written content can contain mistakes. You review every post before approving it and you are responsible for what you approve and publish, including its accuracy and its compliance with the rules of the platform it goes to.",
    ]},
    { id: "account", title: "Your account", body: [
      "Keep your sign-in details secret and tell us at once if you think someone else has used your account. You are responsible for activity under your account.",
      "Give accurate billing details: your state decides how GST is charged, and a GSTIN you enter must be yours.",
    ]},
    { id: "plans", title: "Plans, prices and renewals", body: [
      "Plans, their monthly limits (reels, carousels, posts per day, platforms) and prices are shown on the Subscription page. Prices are in Indian rupees and exclude GST; GST is added where the law requires it and shown before you pay.",
      { list: [
        "**Renewal:** a subscription renews automatically every month or year through Razorpay (UPI Autopay, card or e-mandate) until you cancel. As required by the Reserve Bank of India, you are notified before each renewal charge.",
        "**Upgrades** start immediately: you pay the new plan's price minus the unused value of your current plan.",
        "**Downgrades** start when your current paid period ends. Nothing is refunded for the higher plan, which you keep until then.",
        "**Limits** reset on the 1st of each calendar month (India time). Unused reels and carousels don't carry over. Each post can be regenerated up to 3 times.",
        "**Failed payments:** Razorpay retries a failed renewal; your plan keeps working while it does. If every retry fails, the plan stops until you pay again.",
      ]},
      "We may change prices for future periods. We'll tell you at least 15 days before a new price applies to your next renewal, and you can cancel before then.",
    ]},
    { id: "cancel", title: "Cancelling and refunds", body: [
      "You can cancel anytime on the Subscription page. Your plan runs to the end of the period you've paid for and then stops. Refunds are covered by the [refund and cancellation policy](/legal/refunds).",
    ]},
    { id: "content", title: "Your content", body: [
      "You keep the rights you have in what you give us (your niche, instructions, brand and feedback) and in the posts made for you. You let us use them only to run Mintly for you: to generate, store, preview and publish your posts.",
      "AI can produce content similar to content made for others, so we can't promise that a post is unique. Don't approve a post that you believe infringes someone else's rights.",
    ]},
    { id: "connected", title: "Connected accounts", body: [
      "When you connect Instagram, YouTube or Telegram, you authorise us to post on those accounts on your behalf, and only posts you have approved. You must follow those platforms' own terms ([Instagram](https://help.instagram.com/581066165581870), [YouTube](https://www.youtube.com/t/terms)). We are not responsible for a platform's decisions, such as removing a post or limiting an account. You can disconnect an account anytime.",
    ]},
    { id: "use", title: "Acceptable use", body: [
      "Don't use Mintly to make or publish content that is illegal, misleading, defamatory, hateful, sexually explicit, infringing, or that impersonates someone. Don't send spam, try to get around plan limits or payments, overload or probe the service, or access other people's accounts or data.",
    ]},
    { id: "third-parties", title: "Services we rely on", body: [
      "Mintly uses third-party services to work, including Google (Gemini AI, sign-in, YouTube), Meta (Instagram), Telegram, Cloudinary (media hosting), Amazon Web Services and our database provider (hosting), GitHub (running generation jobs) and Razorpay (payments). Their outages or changes can affect Mintly; we'll work to keep the service running but can't control them.",
    ]},
    { id: "availability", title: "Availability and changes to the service", body: [
      "We aim to keep Mintly available but don't promise it will be uninterrupted or error-free. We may improve or change features; if a change takes away something important you're paying for, we'll tell you in advance and you may cancel.",
    ]},
    { id: "liability", title: "Liability", body: [
      "To the extent the law allows, Mintly is provided as is, and our total liability for any claim relating to the service is limited to the fees you paid us in the 3 months before the claim. We aren't liable for indirect losses such as lost profits, followers or reach. Nothing here limits rights you have under Indian consumer law that can't be limited.",
      "You agree to cover our reasonable costs if a claim is brought against us because of content you approved or your breach of these terms.",
    ]},
    { id: "termination", title: "Suspension and termination", body: [
      "We may suspend or close an account that breaks these terms or the law, after a warning where that's reasonable. You can stop using Mintly and ask us to delete your account anytime (see [data deletion](/legal/data-deletion)).",
    ]},
    { id: "changes", title: "Changes to these terms", body: [
      "We may update these terms. For important changes we'll tell you by email or in the dashboard at least 15 days before they apply; continuing to use Mintly after that means you accept them.",
    ]},
    { id: "law", title: "Law, disputes and contact", body: [
      `These terms are governed by the laws of India, and the courts at ${field("courtsCity")} have jurisdiction. Before going to court, please contact us at ${CONTACT} or our grievance officer (see [contact and grievances](/legal/contact)); we'll try to resolve it quickly.`,
    ]},
  ],
};

const privacy: LegalDoc = {
  slug: "privacy",
  title: "Privacy policy",
  summary: `What personal data ${P} collects, why, who it goes to, and your rights.`,
  sections: [
    { id: "who", title: "Who is responsible", body: [
      `${FIRM} (${field("address")}) decides how your personal data is used in ${P} and is the data fiduciary under India's Digital Personal Data Protection Act, 2023. Questions or requests: ${CONTACT}, or our grievance officer, ${field("grievanceOfficer")} (see [contact and grievances](/legal/contact)).`,
    ]},
    { id: "collect", title: "What we collect", body: [
      { list: [
        "**Account:** name, username, email address, a hashed password (never the password itself), or your Google profile name and email if you sign in with Google; optional profile details (photo, phone, job title, bio, time zone).",
        "**Preferences:** your niche, tone, audience, brand style, posting schedule and default platforms.",
        "**Billing:** name or business name, country, Indian state, GSTIN if you give one, your plan and payment status. Card, UPI and bank details are entered with Razorpay and never reach our servers.",
        "**Connected accounts:** your Instagram user ID and access token, your YouTube authorisation, and your Telegram chat ID. Tokens are stored encrypted.",
        "**Content:** the topics, scripts, slides, reels, captions and voiceovers made for you, your approvals, rejections and feedback.",
        "**Technical:** a sign-in cookie, your IP address for rate limiting (kept for 1 day), and an activity log of account and posting events (kept for 90 days).",
      ]},
    ]},
    { id: "why", title: "Why we use it", body: [
      { list: [
        "To run your account and sign you in.",
        "To generate, preview, schedule and publish your posts to the accounts you connect, after your approval.",
        "To bill you, apply GST correctly and keep the tax records the law requires.",
        "To keep Mintly secure: preventing abuse, investigating errors and enforcing plan limits.",
        "To tell you about your account: approvals, payments, renewals and changes to these policies.",
      ]},
      "We process your data with your consent, given when you sign up and when you connect an account, and where the law requires or permits it (for example tax records). We don't sell your data or show you ads, and we don't use it for anything you haven't asked for.",
    ]},
    { id: "share", title: "Who we share it with", body: [
      "Only with the services that make Mintly work, and only what each needs:",
      { list: [
        "**Google Gemini** writes your posts from your niche, preferences and the day's topic (never your password, tokens or payment details). While we use Gemini's free tier, Google may use those prompts and outputs to improve its products; we'll update this policy when we move to a paid tier, where it doesn't.",
        "**Google Sign-In and YouTube**, **Meta (Instagram)** and **Telegram**: what's needed to sign you in, send previews and publish approved posts.",
        "**Cloudinary** hosts your rendered images and videos at links the platforms fetch them from.",
        "**Amazon Web Services**, our database provider and **GitHub** (which runs the generation jobs) host and run Mintly.",
        "**Razorpay** processes payments and subscriptions.",
        "Our email provider, to send sign-in codes and account messages.",
      ]},
      "We may also disclose data when the law requires it, for example to a court or a tax authority.",
    ]},
    { id: "transfers", title: "Where your data is stored", body: [
      "Some of these services store data outside India, including in the United States. We use providers that protect data with recognised safeguards, and we won't transfer data to a country the Government of India restricts.",
    ]},
    { id: "retention", title: "How long we keep it", body: [
      { list: [
        "Account, preferences, connected accounts and content: while your account is open, then deleted within 30 days of you closing it.",
        "Billing and invoice records: as long as tax and company law require, generally 6 to 8 years.",
        "Activity log: 90 days. Rate-limit records with IP addresses: 1 day.",
      ]},
    ]},
    { id: "rights", title: "Your rights", body: [
      "Under the Digital Personal Data Protection Act you can ask us for a summary of your personal data and how we use it, correct or update it, have it erased, withdraw your consent, nominate someone to act for you, and raise a grievance. Most details can be changed in Profile and Config, and you can delete your account yourself in Profile (see [deleting your data](/legal/data-deletion)); for anything else write to " + CONTACT + ". We'll respond within 30 days. If you're not satisfied, you can complain to the Data Protection Board of India.",
      "Withdrawing consent stops the processing that depends on it (for example disconnecting Instagram stops publishing there) but doesn't undo what was done before.",
    ]},
    { id: "youtube", title: "YouTube", body: [
      "If you connect YouTube, Mintly uses YouTube API Services to upload the Shorts you approve. By connecting, you agree to the [YouTube Terms of Service](https://www.youtube.com/t/terms), and Google's use of data is covered by the [Google Privacy Policy](https://policies.google.com/privacy). We use your YouTube authorisation only to upload approved videos and read their status.",
      "You can revoke Mintly's access anytime at [Google security settings](https://myaccount.google.com/permissions), which stops it working at once, and disconnect YouTube in Mintly, which deletes the stored authorisation.",
    ]},
    { id: "instagram", title: "Instagram", body: [
      "If you connect Instagram, we use Meta's Instagram API to publish the posts you approve. You can remove Mintly in Instagram's settings (Apps and websites) or disconnect it in Mintly. How to have your data deleted: [data deletion](/legal/data-deletion).",
    ]},
    { id: "cookies", title: "Cookies", body: [
      "We use one cookie, to keep you signed in; it's strictly necessary and has no tracking purpose. Your light or dark theme choice is kept in your own browser. There are no analytics or advertising cookies.",
    ]},
    { id: "security", title: "Security", body: [
      "Connections are encrypted (HTTPS), passwords are stored only as salted hashes, integration tokens are encrypted, and payment confirmations are verified with signatures. No system is perfectly secure; if a breach affects your data we'll tell you and the Data Protection Board as the law requires.",
    ]},
    { id: "children", title: "Children", body: [
      "Mintly is for people aged 18 and over. We don't knowingly collect data from children; if you think a child has signed up, write to us and we'll delete the account.",
    ]},
    { id: "changes", title: "Changes to this policy", body: [
      "If we change how we use your data in an important way, we'll tell you by email or in the dashboard before it applies, and ask for your consent again where the law requires.",
    ]},
  ],
};

const refunds: LegalDoc = {
  slug: "refunds",
  title: "Refunds and cancellations",
  summary: "How cancelling, plan changes, refunds and delivery work.",
  sections: [
    { id: "cancel", title: "Cancelling", body: [
      "Cancel anytime on the Subscription page. Your plan keeps working until the end of the period you've paid for, then stops, and you aren't charged again. Changed your mind before then? Choose the same plan again and it carries on from the end of the period, with nothing charged now.",
      "Deleting your account is different: it cancels the subscription straight away, with no refund for the time left, because the account it pays for no longer exists.",
    ]},
    { id: "changes", title: "Changing plan", body: [
      { list: [
        "**Upgrade:** starts immediately. You pay the new plan's price minus the unused value of your current plan, shown with GST before you pay.",
        "**Downgrade:** starts when your current paid period ends. You keep the higher plan until then, so nothing is refunded.",
      ]},
    ]},
    { id: "refunds", title: "When we refund", body: [
      "Subscriptions aren't refunded for unused time after cancelling or downgrading, because the plan keeps working until the period ends. We do refund:",
      { list: [
        "a charge made in error, such as a duplicate charge or a renewal after your cancellation took effect;",
        "the unused part of a period when the service was unavailable or didn't work as described for a significant time because of a fault on our side;",
        "any other case where Indian consumer law entitles you to a refund.",
      ]},
      `Write to ${CONTACT} within 30 days of the charge with the payment reference. We'll reply within 48 hours and, once a refund is approved, return it to the original payment method within 7 working days (your bank may take a few more days to show it).`,
    ]},
    { id: "failed", title: "Failed payments", body: [
      "If a renewal fails, Razorpay retries it and your plan keeps working meanwhile. If every retry fails, the plan stops; nothing is lost, and you can subscribe again anytime.",
    ]},
    { id: "delivery", title: "Delivery", body: [
      "Mintly is an online service: there's nothing to ship. Your plan is available as soon as your payment is confirmed, usually within a minute, and posts are delivered to you on Telegram and the dashboard for approval.",
    ]},
  ],
};

const contact: LegalDoc = {
  slug: "contact",
  title: "Contact and grievances",
  summary: `How to reach ${FIRM} and how complaints are handled.`,
  sections: [
    { id: "company", title: "The company", body: [
      { list: [
        `**Legal name:** ${FIRM} (${field("entityType")})`,
        `**Registered address:** ${field("address")}`,
        `**Email:** ${CONTACT}`,
        `**Phone:** ${field("phone")}`,
        ...(COMPANY.gstin ? [`**GSTIN:** ${COMPANY.gstin}`] : []),
      ]},
    ]},
    { id: "grievance", title: "Grievance officer", body: [
      `**${field("grievanceOfficer")}**, ${FIRM}, ${field("address")}. Email ${CONTACT}.`,
      "We acknowledge every complaint within 48 hours with a reference number and resolve it within one month of receiving it, as the Consumer Protection (E-Commerce) Rules, 2020 require. Data protection grievances are answered within 30 days.",
    ]},
    { id: "support", title: "Help with your account", body: [
      "For questions about posts, connected accounts or billing, write to us from the email address on your account so we can find it quickly. Include the payment reference for anything about a charge.",
    ]},
  ],
};

const deletion: LegalDoc = {
  slug: "data-deletion",
  title: "Deleting your data",
  summary: "How to close your Mintly account and have your data deleted.",
  sections: [
    { id: "request", title: "Delete your account", body: [
      "**Yourself, right away:** sign in, open Profile, then Security, and choose Delete account. You confirm with your password (or a code we email you if you sign in with Google) and by typing DELETE. Your account and data are erased at once and your subscription is cancelled.",
      `**By email:** if you can't sign in, write to ${CONTACT} from the address on your Mintly account with the subject "Delete my Mintly account". We confirm the request within 48 hours and complete it within 30 days.`,
    ]},
    { id: "what", title: "What's deleted", body: [
      "Your account, profile, preferences, billing details, connected-account tokens (Instagram, YouTube, Telegram), and the content made for you, including images and videos stored with our media host. Our activity records keep what happened (for example that a post was published) but no longer say who it was. Posts already published to Instagram or YouTube stay on those platforms; delete them there if you want them gone.",
      "We keep only what the law requires, such as invoices and payment records for tax purposes (generally 6 to 8 years), and nothing else.",
    ]},
    { id: "platforms", title: "Disconnect Instagram and YouTube yourself", body: [
      { list: [
        "**Instagram:** Settings, then Apps and websites, then remove Mintly. Or disconnect Instagram in Mintly.",
        "**YouTube:** remove Mintly at [Google security settings](https://myaccount.google.com/permissions), or disconnect YouTube in Mintly.",
      ]},
      "Disconnecting stops all publishing to that account straight away and deletes the stored token.",
    ]},
  ],
};

export const LEGAL_DOCS: LegalDoc[] = [terms, privacy, refunds, contact, deletion];
export const LEGAL_BY_SLUG: Record<string, LegalDoc> = Object.fromEntries(LEGAL_DOCS.map((d) => [d.slug, d]));
