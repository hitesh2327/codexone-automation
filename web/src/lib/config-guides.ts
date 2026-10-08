// Setup guides, troubleshooting and glossary for the Config section (rendered by pages/ConfigGuide.tsx and
// the "Where do I get this?" side sheet). Pure data: web/tests/config.test.mts and
// tests/test_verify_catalogue.py read it.
//
// Rules for this file (owner's "no assumptions"):
//  * every step is backed by the official page listed in the guide's `sources` (fetched on VERIFIED_ON);
//  * anything we could NOT confirm in official documentation carries `unverified` with the reason, is shown
//    with an "Unverified" tag, and is listed in docs/specs/config-implementation-notes.md with the test that
//    settles it;
//  * TROUBLESHOOTING has exactly one entry per verifier code in src/verify/base.py CODES (a test enforces it).

export const VERIFIED_ON = "2026-10-06";

export type Link = { href: string; label: string };
export type Step = { text: string; link?: Link; unverified?: string };
export type Guide = {
  id: "gemini" | "telegram" | "cloudinary" | "github" | "database";
  title: string;
  minutes: number;
  purpose: string;
  before: string[];
  steps: Step[];
  success: string;
  mistakes: string[];
  security: string;
  sources: Link[];
};

export const GUIDES: Guide[] = [
  {
    id: "gemini",
    title: "Gemini API key",
    minutes: 2,
    purpose: "Gemini writes every reel script, caption and carousel. The key lets this app call it on your behalf.",
    before: ["A Google account.", "If you already use Google Cloud, AI Studio may ask you to import a project first."],
    steps: [
      { text: "Open Google AI Studio's API keys page and sign in.", link: { href: "https://aistudio.google.com/api-keys", label: "aistudio.google.com/api-keys" } },
      { text: "First time: accept the Terms of Service. New users get a default Google Cloud project and an API key created for them." },
      { text: "Click Create API key (new keys are created as “auth keys”). If the button is greyed out, you lack permission in that project: pick or import another project." },
      { text: "Copy the key and paste it into the API key field on the Config page." },
      { text: "Click Verify & save. We ask Gemini to list models and count the tokens of one word. Nothing is generated (whether these two calls count toward rate limits isn't documented)." },
    ],
    success: "The card turns Valid and shows how many models the key can see, e.g. “42 models visible to this key”.",
    mistakes: [
      "Copying with a trailing space or line break (the page removes these for you and says so).",
      "Pasting GEMINI_API_KEY=… from a .env file (also removed for you).",
      "Using an old “standard” key: Google rejects unrestricted standard keys and blocks dormant ones. Create a new key if yours is refused.",
      "Expecting a second key from the same project to add quota: limits apply per project, not per key.",
    ],
    security: "Anyone with this key can spend your project's quota. It's stored encrypted and never shown again; to revoke it, delete it on the same AI Studio page.",
    sources: [
      { href: "https://ai.google.dev/gemini-api/docs/api-key", label: "Gemini API: Using API keys" },
      { href: "https://ai.google.dev/gemini-api/docs/rate-limits", label: "Gemini API: Rate limits (per project; daily quota resets at midnight Pacific)" },
      { href: "https://ai.google.dev/gemini-api/docs/billing", label: "Gemini API: Billing (data use on the Paid Tier)" },
      { href: "https://ai.google.dev/gemini-api/docs/troubleshooting", label: "Gemini API: Troubleshooting (leaked/blocked keys)" },
    ],
  },
  {
    id: "telegram",
    title: "Telegram bot and approval chat",
    minutes: 3,
    purpose: "Every new post is sent to you in Telegram with Approve / Reject / Regenerate buttons. Nothing is published without your approval.",
    before: ["The Telegram app on your phone or desktop."],
    steps: [
      { text: "Open @BotFather in Telegram and send /newbot. Follow its questions (a display name, then a username).", link: { href: "https://t.me/BotFather", label: "t.me/BotFather" } },
      { text: "BotFather replies with a token that looks like 123456:ABC-DEF…. Copy it and paste it into Bot token." },
      { text: "Open a chat with your new bot and press Start. (After you paste the token, the Config page shows a direct link to your bot.)" },
      {
        text: "Click Detect my chat and pick your chat. For a group: add the bot to the group, send /start@yourbot in the group, then Detect; group ids start with a minus sign.",
        unverified: "That a bot can't message you until you press Start, and that a group bot with privacy mode on sees /start@bot, are widely reported but not stated on the pages we checked. Test S9 settles it.",
      },
      { text: "Click Verify & save. We check the token (getMe), that no webhook is set (getWebhookInfo) and that the bot can see your chat (getChat)." },
      { text: "Optional: Send test message. It has no buttons and posts nothing anywhere else." },
    ],
    success: "The card turns Valid and shows your bot's @username and the chat type.",
    mistakes: [
      "Typing the chat id by hand: use Detect my chat.",
      "A webhook left on the bot by another tool: Telegram can't deliver button presses to this app while a webhook is set (the card offers to remove it).",
      "Using the same bot token in another app that also reads updates: Telegram answers “Conflict” to one of them.",
    ],
    security: "The token controls the bot. If it leaks, revoke it through @BotFather and paste the new token here.",
    sources: [
      { href: "https://core.telegram.org/bots/tutorial", label: "Telegram: Bot tutorial (/newbot, token)" },
      { href: "https://core.telegram.org/bots/api", label: "Telegram Bot API (getMe, getWebhookInfo, getChat, getUpdates)" },
      { href: "https://core.telegram.org/bots/features", label: "Telegram: Bot features (Start button, deep links)" },
    ],
  },
  {
    id: "cloudinary",
    title: "Cloudinary",
    minutes: 2,
    purpose: "Rendered slides and reels are uploaded to Cloudinary so Instagram, YouTube and Telegram can fetch them from a public link.",
    before: ["A Cloudinary account (the free plan works). You need the Master admin, Admin or Technical admin role to see API keys."],
    steps: [
      { text: "Sign in to the Cloudinary Console and open Settings > API Keys.", link: { href: "https://console.cloudinary.com/settings/api-keys", label: "console.cloudinary.com/settings/api-keys" }, unverified: "The deep link was not confirmed against the live console. If it 404s, use Settings (gear) > API Keys." },
      { text: "Find the API environment variable: cloudinary://<your_api_key>:<your_api_secret>@your-cloud. It is shown as a template." },
      { text: "Replace <your_api_key> and <your_api_secret> with the API key and API secret listed on the same page." },
      { text: "Paste the whole line into the field and click Verify & save. We ping the account, upload an 8×8 test JPEG to codexone/_selftest, fetch its public link, then delete it." },
    ],
    success: "The card turns Valid and shows your cloud name.",
    mistakes: [
      "Pasting the template with <your_api_key> still in it (the page catches this).",
      "Pasting only the API key or only the secret: the field needs the whole cloudinary://… line.",
      "Copying CLOUDINARY_URL=cloudinary://… from a .env file (the prefix is removed for you).",
    ],
    security: "The secret allows uploads and deletes in your account. Rotate it on the same API Keys page if it leaks, then paste the new line here.",
    sources: [
      { href: "https://cloudinary.com/documentation/product_environment_settings", label: "Cloudinary: API Keys page and API environment variable" },
      { href: "https://cloudinary.com/documentation/admin_api", label: "Cloudinary: Admin API (ping, rate limits, errors)" },
      { href: "https://cloudinary.com/documentation/image_upload_api_reference", label: "Cloudinary: Upload API (upload, destroy, Basic authentication)" },
    ],
  },
  {
    id: "github",
    title: "GitHub automation",
    minutes: 3,
    purpose: "Rendering and publishing run as GitHub Actions workflows in your copy of the repository. The token lets the dashboard start them and read their progress.",
    before: ["Your own copy of the automation repository, with GitHub Actions enabled."],
    steps: [
      { text: "Enter the repository as owner/name (pasting its github.com link also works)." },
      { text: "Open GitHub's new fine-grained token page.", link: { href: "https://github.com/settings/personal-access-tokens/new", label: "github.com/settings/personal-access-tokens/new" } },
      { text: "Name it (e.g. “content dashboard”), choose an Expiration you'll remember, and under Resource owner pick the account or organisation that owns the repository." },
      { text: "Repository access: Only select repositories, then select this one repository. (Tokens always include read-only access to public repositories.)" },
      { text: "Permissions > Repository permissions > Actions: Read and write. Nothing else is needed (Metadata: read is added automatically).", unverified: "That Metadata: read is added automatically was not confirmed on the pages we read; the token works either way." },
      { text: "Click Generate token, copy it (it starts with github_pat_) and paste it here. Click Verify & save." },
    ],
    success: "The card turns Valid: the repository is visible and both workflows (daily-generate.yml, poll-approvals.yml) are enabled. Write access is confirmed the first time you start a generation.",
    mistakes: [
      "A classic token (ghp_…): it reaches every repository you can. Use a fine-grained one.",
      "Forgetting to select the repository under Repository access: GitHub then answers “Not Found”.",
      "A fork or an inactive public repository: GitHub disables scheduled workflows in forks by default, and in public repositories after 60 days without activity. Re-enable them in the Actions tab.",
      "An organisation that requires approval for fine-grained tokens: the token stays pending until an owner approves it.",
    ],
    security: "This token can start and cancel workflows in this one repository. Revoke it under Settings > Developer settings > Fine-grained tokens.",
    sources: [
      { href: "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens", label: "GitHub: Managing personal access tokens" },
      { href: "https://docs.github.com/en/rest/actions/workflows", label: "GitHub REST: Workflows (permissions per endpoint)" },
      { href: "https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows", label: "GitHub: Disabling and enabling a workflow" },
      { href: "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github", label: "GitHub: Token formats (github_pat_, ghp_)" },
    ],
  },
  {
    id: "database",
    title: "Database (Neon / Postgres)",
    minutes: 0,
    purpose: "Posts, settings and this configuration live in Postgres. DATABASE_URL and CONFIG_MASTER_KEY are set when the app is installed; this page only checks them.",
    before: ["Access to the server's environment (SSM on AWS) and the repository's GitHub secrets: the installer or your administrator."],
    steps: [
      { text: "In the Neon console open your project and click Connect. Neon shows a pooled connection string by default (its host contains -pooler).", link: { href: "https://console.neon.tech", label: "console.neon.tech" } },
      { text: "Turn the Connection pooling toggle off to get the direct connection string, which the API needs." },
      { text: "The installer stores it as DATABASE_URL on the server and as a GitHub secret. It is never entered on this page." },
      { text: "CONFIG_MASTER_KEY encrypts the values saved here. Generate one with: python -m src.config_store generate-key. Store the same key on the server and as a GitHub secret, and keep a copy in a password manager." },
    ],
    success: "The Database card shows Valid: connected, schema current, writable, and the master key opens the saved settings.",
    mistakes: [
      "Using the pooled (-pooler) string for the API.",
      "Different CONFIG_MASTER_KEY values on the server and in GitHub: saved secrets can't be read in one of them.",
      "Losing the master key: saved secrets can't be recovered; you would re-enter them.",
    ],
    security: "DATABASE_URL contains the database password; CONFIG_MASTER_KEY unlocks every saved secret. Neither is ever shown in the dashboard.",
    sources: [
      { href: "https://neon.com/docs/connect/connect-from-any-app", label: "Neon: Connect from any application (pooled vs direct)" },
      { href: "https://neon.com/docs/introduction/scale-to-zero", label: "Neon: Scale to zero (idle after 5 minutes)" },
    ],
  },
];

export type Trouble = { title: string; cause: string; fix: string[]; link?: Link; unverified?: string };

const AISTUDIO: Link = { href: "https://aistudio.google.com/api-keys", label: "AI Studio API keys" };
const BOTFATHER: Link = { href: "https://t.me/BotFather", label: "@BotFather" };
const CLD_KEYS: Link = { href: "https://cloudinary.com/documentation/product_environment_settings", label: "Cloudinary API Keys page" };
const GH_TOKENS: Link = { href: "https://github.com/settings/personal-access-tokens", label: "GitHub fine-grained tokens" };
const GH_ENABLE: Link = { href: "https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows", label: "Enable a workflow" };
const NEON: Link = { href: "https://neon.com/docs/connect/connect-from-any-app", label: "Neon connection strings" };

export const TROUBLESHOOTING: Record<string, Trouble> = {
  "verify.not_set": { title: "Not set yet", cause: "This setting has no value in the environment or on this page.", fix: ["Open the setup step and paste the value.", "Use “Where do I get this?” next to the field for the exact steps."] },
  "verify.not_implemented": { title: "Not verified from the dashboard yet", cause: "This integration has no live check in this release, so we can't say whether it works.", fix: ["It keeps working from the environment as before.", "Its check arrives in a later release; until then treat it as unverified."] },
  "verify.crashed": { title: "The check itself failed", cause: "Something unexpected happened while checking. Your saved value was not changed.", fix: ["Try again in a minute.", "If it keeps happening, look at the server log (secrets are scrubbed from it)."] },

  "gemini.format": { title: "That doesn't look like an API key", cause: "The value is empty or contains spaces, tabs or line breaks.", fix: ["Copy the key again from AI Studio.", "Paste only the key, nothing around it."], link: AISTUDIO },
  "gemini.model_format": { title: "Invalid model name", cause: "Model names use lowercase letters, digits, dots and dashes.", fix: ["Clear the field to use the default (gemini-flash-latest).", "Or copy a name exactly from the Gemini models page."], link: { href: "https://ai.google.dev/gemini-api/docs/models", label: "Gemini models" } },
  "gemini.key_rejected": { title: "Gemini rejected the key", cause: "The key is mistyped, was deleted, or belongs to no project.", fix: ["Copy it again from AI Studio (no spaces, no quotes).", "If it still fails, create a new key there and paste that."], link: AISTUDIO },
  "gemini.key_blocked": { title: "The key is blocked", cause: "Google blocks keys it detects as leaked, and unrestricted keys left unused for a long time.", fix: ["Create a new key in AI Studio.", "Delete the old key so it can't be used."], link: AISTUDIO },
  "gemini.forbidden": { title: "The key isn't allowed to call Gemini", cause: "The key works but its API restrictions don't allow the Generative Language API, or a project prerequisite (such as billing) isn't met.", fix: ["In Google Cloud > APIs & Services > Credentials, open the key and allow the Generative Language API.", "Or create a fresh key in AI Studio, which is restricted to Gemini by default."], link: { href: "https://console.cloud.google.com/apis/credentials", label: "Google Cloud credentials" } },
  "gemini.billing": { title: "Prepaid credit used up", cause: "Gemini answered “payment required”: the project's prepaid balance is empty.", fix: ["Add credit or turn on auto-reload in AI Studio billing.", "Or use a key from a Free Tier project."], link: { href: "https://ai.google.dev/gemini-api/docs/billing", label: "Gemini billing" } },
  "gemini.model_not_found": { title: "Model not available", cause: "The chosen model doesn't exist or isn't offered to this key.", fix: ["Clear the model field to use the default.", "Or pick a model from the Gemini models page."], link: { href: "https://ai.google.dev/gemini-api/docs/models", label: "Gemini models" } },
  "gemini.rate_limited": { title: "Rate-limited right now", cause: "Too many requests in a short time (per minute limits).", fix: ["Wait a minute and verify again. The key itself is fine."], link: { href: "https://ai.google.dev/gemini-api/docs/rate-limits", label: "Gemini rate limits" } },
  "gemini.quota": { title: "Today's quota is used up", cause: "The key works but the project's daily request quota is spent. Limits are per project, not per key.", fix: ["Wait for the reset at midnight Pacific time.", "Or move the project to a paid tier for higher limits."], link: { href: "https://ai.google.dev/gemini-api/docs/rate-limits", label: "Gemini rate limits" } },
  "gemini.unavailable": { title: "Gemini didn't answer properly", cause: "A server error or overload on Google's side.", fix: ["Try again in a few minutes. Your key may be fine.", "The pipeline retries and falls back to other models during generation."] },
  "gemini.unreachable": { title: "Couldn't reach Gemini", cause: "The server couldn't connect to generativelanguage.googleapis.com (network, DNS or firewall).", fix: ["Try again.", "If it persists, check the server's outbound internet access."] },
  "gemini.generation_empty": { title: "Test generation returned nothing usable", cause: "The model accepted the request but returned no JSON (it may have spent its output on thinking, or been filtered).", fix: ["Try another model under Advanced.", "Run the test again later."] },

  "telegram.token_format": { title: "That isn't a bot token", cause: "Bot tokens are digits, a colon, then letters, digits, - and _.", fix: ["Send /mybots to @BotFather, choose your bot and copy its token again."], link: BOTFATHER },
  "telegram.chat_format": { title: "Chat ID must be a number", cause: "Chat IDs are whole numbers; groups and channels are negative.", fix: ["Clear the field and use Detect my chat."] },
  "telegram.token_rejected": { title: "Telegram doesn't recognise the token", cause: "The token is mistyped or was revoked in @BotFather.", fix: ["Send /mybots to @BotFather, choose your bot and copy its current token.", "If the token was revoked, paste the new one."], link: BOTFATHER },
  "telegram.webhook_set": { title: "A webhook blocks approvals", cause: "Telegram delivers updates either to a webhook or through polling, never both. This app polls, so button presses can't arrive while a webhook is set.", fix: ["Click Remove webhook on the Telegram card (asks to confirm).", "Only keep the webhook if another app really needs this bot; then create a separate bot for this app."], link: { href: "https://core.telegram.org/bots/api#getting-updates", label: "Telegram: Getting updates" } },
  "telegram.chat_not_found": { title: "The bot can't see that chat", cause: "Wrong chat ID, or the bot was never started in that chat / added to that group.", fix: ["Open your bot in Telegram and press Start (or add it to the group).", "Click Detect my chat and pick the chat from the list."] },
  "telegram.blocked": { title: "The bot can't post in that chat", cause: "You blocked the bot, or it was removed from the group.", fix: ["Unblock the bot in Telegram, or add it back to the group.", "Verify again."] },
  "telegram.no_chat_found": { title: "No message to the bot yet", cause: "Detect looks at messages sent to the bot recently (Telegram keeps them up to 24 hours) and found none.", fix: ["Open your bot in Telegram and press Start or send /start.", "Click Detect my chat again."] },
  "telegram.poll_conflict": { title: "Another program reads this bot's updates", cause: "Telegram allows one reader at a time. The scheduled approval job, or another app using the same token, was reading at that moment.", fix: ["Wait a minute and try again.", "Make sure no other app uses this bot token."] },
  "telegram.rate_limited": { title: "Telegram is rate-limiting the bot", cause: "Too many requests in a short time.", fix: ["Wait a minute and try again."] },
  "telegram.unavailable": { title: "Telegram didn't answer properly", cause: "An error on Telegram's side.", fix: ["Try again in a few minutes."] },
  "telegram.unreachable": { title: "Couldn't reach Telegram", cause: "The server couldn't connect to api.telegram.org.", fix: ["Try again.", "If it persists, check the server's outbound internet access."] },

  "cloudinary.format": { title: "Not a Cloudinary API environment variable", cause: "The value must be cloudinary://<api_key>:<api_secret>@<cloud_name>.", fix: ["Copy the whole API environment variable from Settings > API Keys and fill in the key and secret."], link: CLD_KEYS },
  "cloudinary.placeholder": { title: "The placeholders are still in it", cause: "Cloudinary shows the variable as a template with <your_api_key> and <your_api_secret>.", fix: ["Replace both placeholders with the key and secret listed on the same API Keys page.", "Paste the completed line again."], link: CLD_KEYS },
  "cloudinary.rejected": { title: "Cloudinary rejected the credentials", cause: "The key, secret or cloud name don't belong together (one was mistyped, or the key was rotated/deactivated).", fix: ["Copy the API environment variable again and fill in the current key and secret.", "Check the key is Active on the API Keys page."], link: CLD_KEYS },
  "cloudinary.forbidden": { title: "This key isn't allowed to do that", cause: "The key works but its permissions don't allow uploads or admin calls.", fix: ["Use a key with full access, or adjust its permissions on the API Keys page."], link: { href: "https://cloudinary.com/documentation/permissions_custom_policies", label: "Cloudinary permissions" } },
  "cloudinary.not_found": { title: "Unknown cloud name", cause: "Cloudinary answered “not found” for this cloud name.", fix: ["The cloud name is the part after @. Copy the variable again from the API Keys page."], link: CLD_KEYS },
  "cloudinary.rate_limited": { title: "Admin API rate limit reached", cause: "The free plan allows 500 Admin API calls per hour (paid plans more). Each check uses one.", fix: ["Wait a few minutes and verify again."], link: { href: "https://cloudinary.com/documentation/admin_api", label: "Cloudinary Admin API limits" } },
  "cloudinary.upload_failed": { title: "Test upload refused", cause: "The credentials work but Cloudinary refused an 8×8 JPEG (for example: storage or credits used up, or an upload restriction).", fix: ["Check usage and limits in the Cloudinary console.", "Verify again after freeing space or credits."] },
  "cloudinary.delivery_failed": { title: "The public link doesn't serve the image", cause: "The test image uploaded, but fetching its https link didn't return an image. Instagram, YouTube and Telegram fetch media from these links.", fix: ["Check delivery/access-control settings in the Cloudinary console (e.g. restricted media types).", "Verify again."] },
  "cloudinary.cleanup_failed": { title: "The test image wasn't deleted", cause: "Everything worked, but deleting the test image failed.", fix: ["Delete it by hand: Media Library > folder codexone/_selftest."] },
  "cloudinary.unavailable": { title: "Cloudinary didn't answer properly", cause: "An error on Cloudinary's side.", fix: ["Try again in a few minutes."] },
  "cloudinary.unreachable": { title: "Couldn't reach Cloudinary", cause: "The server couldn't connect to api.cloudinary.com.", fix: ["Try again.", "If it persists, check the server's outbound internet access."] },

  "github.repo_format": { title: "Repository must be owner/name", cause: "We need the owner and repository name, e.g. acme/content-automation.", fix: ["Copy it from the repository page URL: github.com/<owner>/<name>.", "Pasting the full link also works."] },
  "github.token_format": { title: "That doesn't look like a token", cause: "The value is empty or contains spaces or line breaks.", fix: ["Copy the token again right after generating it (GitHub shows it only once).", "If you lost it, regenerate it."], link: GH_TOKENS },
  "github.token_rejected": { title: "GitHub doesn't accept the token", cause: "It is mistyped, expired, or was deleted.", fix: ["Generate a new fine-grained token (this repository only, Actions: Read and write) and paste it."], link: GH_TOKENS },
  "github.not_found": { title: "Repository not found (or not visible to the token)", cause: "GitHub answers 404 instead of 403 for private repositories you can't access, so this is either a wrong owner/name or a token without access to it.", fix: ["Check owner/name.", "Edit the token: Repository access > Only select repositories > add this repository."], link: GH_TOKENS },
  "github.forbidden": { title: "Token lacks the Actions permission", cause: "The token can see the repository, but not its workflows.", fix: ["Edit the token: Repository permissions > Actions > Read and write.", "Save, then verify again (the token value doesn't change)."], link: GH_TOKENS },
  "github.workflow_missing": { title: "A required workflow is missing", cause: "daily-generate.yml or poll-approvals.yml isn't in .github/workflows of this repository.", fix: ["Check you entered the right repository.", "Restore the workflow files from the template repository."] },
  "github.workflow_disabled": { title: "A workflow is disabled", cause: "GitHub disables workflows manually, in forks by default, and in public repositories after 60 days without activity.", fix: ["Open the repository's Actions tab, select the workflow and click Enable workflow.", "Verify again."], link: GH_ENABLE },
  "github.archived": { title: "Repository is archived", cause: "Archived repositories are read-only, which is likely to stop workflows from running.", fix: ["Unarchive it: repository Settings > General > Danger zone."], unverified: "Whether workflow_dispatch runs are refused in an archived repository was not confirmed in GitHub's docs (test S10)." },
  "github.branch": { title: "Default branch isn't main", cause: "The dashboard starts workflows on the main branch.", fix: ["Make sure a main branch exists with the workflows, or rename the default branch to main."] },
  "github.classic_token": { title: "Classic token", cause: "Classic tokens (ghp_…) can reach every repository you can, more than this app needs.", fix: ["Create a fine-grained token (github_pat_…) for this repository only, with Actions: Read and write.", "Delete the classic token if nothing else uses it."], link: GH_TOKENS },
  "github.token_expiring": { title: "Token expires soon", cause: "GitHub reported the token's expiry date and it is close. When it expires the dashboard can't start runs.", fix: ["Generate a new token (or regenerate this one) and paste it here before the date."], link: GH_TOKENS },
  "github.write_unconfirmed": { title: "Write access not proven yet", cause: "Starting a workflow is the only way to prove Actions: write, and checks never start workflows.", fix: ["Nothing to do: the first generation you start from the dashboard confirms it.", "If that start fails, edit the token: Actions > Read and write."] },
  "github.rate_limited": { title: "GitHub is rate-limiting the token", cause: "Too many API requests in the current hour.", fix: ["Wait a few minutes and verify again."] },
  "github.unavailable": { title: "GitHub didn't answer properly", cause: "An error on GitHub's side.", fix: ["Try again in a few minutes.", "Check githubstatus.com."] },
  "github.unreachable": { title: "Couldn't reach GitHub", cause: "The server couldn't connect to api.github.com.", fix: ["Try again.", "If it persists, check the server's outbound internet access."] },

  "database.not_set": { title: "No database configured", cause: "DATABASE_URL is empty, so the app runs in file mode and this page can't save anything.", fix: ["Set DATABASE_URL on the server (the installer does this)."], link: NEON },
  "database.format": { title: "DATABASE_URL isn't a Postgres URL", cause: "It must start with postgres:// or postgresql://.", fix: ["Copy the connection string from the Neon console (Connect)."], link: NEON },
  "database.unreachable": { title: "Couldn't connect to the database", cause: "Neon may be waking up (it sleeps after 5 idle minutes), or the host/network is wrong.", fix: ["Try again in a few seconds.", "If it persists, check the connection string and Neon's status."], link: { href: "https://neon.com/docs/introduction/scale-to-zero", label: "Neon scale to zero" } },
  "database.rejected": { title: "Database refused the login", cause: "The username or password in DATABASE_URL is wrong (e.g. the password was reset).", fix: ["Copy a fresh connection string from the Neon console and update DATABASE_URL on the server and in GitHub secrets."], link: NEON },
  "database.schema_ahead": { title: "Database schema is newer than the app", cause: "A newer version of the app migrated the database, then an older version was deployed (a rollback).", fix: ["Nothing breaks: schema changes are additive and older versions run on them.", "Deploy the current version again to clear this warning."] },
  "database.schema_behind": { title: "Database schema is out of date", cause: "This version of the app expects newer tables than the database has.", fix: ["Run the migration: the poll-approvals workflow runs “alembic upgrade head”, or run it locally against the database."] },
  "database.read_only": { title: "Database is read-only for this user", cause: "The database role can read but not write.", fix: ["Use a connection string for a role that owns the database."] },
  "database.pooled_url": { title: "Pooled connection string in use", cause: "Neon's default string goes through its connection pooler (host contains -pooler). The API needs the direct connection.", fix: ["In Neon > Connect, turn Connection pooling off and use that string as DATABASE_URL."], link: NEON },
  "database.master_key_missing": { title: "CONFIG_MASTER_KEY isn't set", cause: "Without it, secrets entered here can't be encrypted or read.", fix: ["Run: python -m src.config_store generate-key", "Store the output as CONFIG_MASTER_KEY on the server (SSM) and as a GitHub Actions secret, then restart the API.", "Keep a copy in a password manager."] },
  "database.master_key_invalid": { title: "CONFIG_MASTER_KEY is malformed", cause: "It must be 32 random bytes in base64 (44 characters).", fix: ["Generate a proper key: python -m src.config_store generate-key"] },
  "database.key_mismatch": { title: "Master key doesn't match", cause: "The saved settings were encrypted with a different CONFIG_MASTER_KEY than this server has.", fix: ["Set the same CONFIG_MASTER_KEY on the server and in GitHub secrets.", "If the original key is lost, the saved secrets can't be recovered: remove them and enter them again."] },
};

export const GLOSSARY: { term: string; text: string }[] = [
  { term: "API key", text: "A long secret string that identifies your account to a service (Gemini). Anyone holding it can use your quota." },
  { term: "Bot token", text: "The secret that controls a Telegram bot. BotFather issues it and can revoke it." },
  { term: "Chat ID", text: "The number Telegram uses for a chat. Private chats are positive, groups and channels negative." },
  { term: "Webhook vs polling", text: "Two exclusive ways a Telegram bot receives updates: Telegram pushes them to a URL (webhook), or the app asks for them (polling, getUpdates). This app polls." },
  { term: "Fine-grained token", text: "A GitHub token limited to chosen repositories and permissions (starts with github_pat_). Safer than a classic token (ghp_)." },
  { term: "Workflow", text: "An automated job in the repository's .github/workflows folder that GitHub Actions runs on a schedule or on request." },
  { term: "Quota vs rate limit", text: "A rate limit caps requests per minute (wait and retry); a quota caps requests per day (wait for the reset)." },
  { term: "API environment variable", text: "Cloudinary's single line cloudinary://key:secret@cloud that holds all three credentials." },
  { term: "Pooled vs direct connection", text: "Neon's pooler shares database connections between many clients (host has -pooler). The API uses the direct connection." },
  { term: "Scale to zero", text: "Neon pauses an idle database after 5 minutes and wakes it on the next query, within a few hundred milliseconds per Neon." },
  { term: "Master key", text: "CONFIG_MASTER_KEY: the key that encrypts the secrets saved on this page. Kept outside the database; losing it means re-entering them." },
  { term: "Verify & save", text: "We check a value against the real service before storing it. A value that fails is never saved, so a typo can't break a working setup." },
  { term: "Environment override", text: "A setting also defined on the server (environment variable or GitHub secret). During migration the environment's value wins." },
  { term: "Stale", text: "A value changed after it was last verified, so its old result no longer counts." },
  { term: "Unknown", text: "The service didn't answer (outage, network). It says nothing about whether your value is right." },
];
