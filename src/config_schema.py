"""Every setting the dashboard's Config page knows about: which integration it belongs to, whether it is
secret, whether "ready to generate" needs it, and the shape a user should paste (never a real value).

Names are the environment-variable names the code already reads with get_env(), so a value saved on the
Config page and an environment variable are two sources of the same setting (src/config.py decides which
wins). Bootstrap values (DATABASE_URL, CONFIG_MASTER_KEY, JWT_SECRET, ...) are deliberately absent: they
can never come from the store, because the store needs them to open.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    name: str
    integration: str
    label: str
    secret: bool
    required: bool              # needed for "ready to generate" (Tier 1) or for its integration to work
    shape: str                  # what the value looks like (an example of the SHAPE, never a real value)
    help: str
    advanced: bool = False
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class Integration:
    name: str
    title: str
    tier: int                   # 1 = needed to generate; 2+ = publishing / optional
    blurb: str
    minutes: int                # honest estimate for a first-time user (to be measured, spec S-UX)
    implemented: bool           # has a live verifier in this release
    editable: bool              # values can be saved from the dashboard


INTEGRATIONS: tuple[Integration, ...] = (
    Integration("database", "Database", 1, "Where posts, settings and this configuration live. Set at install; read-only here.",
                0, True, False),
    Integration("gemini", "Gemini", 1, "Writes the scripts, captions and slides.", 2, True, True),
    Integration("telegram", "Telegram", 1, "Sends you each post for approval and tells you what happened.", 3, True, True),
    Integration("cloudinary", "Cloudinary", 1, "Hosts the rendered images and videos at public links.", 2, True, True),
    Integration("github", "GitHub automation", 1, "Runs the rendering and publishing jobs in your repository.", 3, True, True),
    Integration("instagram", "Instagram", 2, "Publishes approved posts to your professional account.", 9, False, False),
    Integration("youtube", "YouTube", 3, "Uploads approved reels as Shorts.", 10, False, False),
    Integration("email", "Email (SMTP)", 4, "Sends password-reset and verification codes.", 4, False, False),
    Integration("google", "Sign in with Google", 4, "Lets allowed Google accounts sign in to this dashboard.", 5, False, False),
)
BY_NAME = {i.name: i for i in INTEGRATIONS}
TIER1 = tuple(i.name for i in INTEGRATIONS if i.tier == 1)

FIELDS: tuple[Field, ...] = (
    # Gemini
    Field("GEMINI_API_KEY", "gemini", "API key", True, True, "a long string of letters, digits, - and _",
          "Google AI Studio > Get API key > Create API key. Paste the key only."),
    Field("GEMINI_MODEL", "gemini", "Model", False, False, "gemini-flash-latest",
          "Leave empty to use the default (gemini-flash-latest).", advanced=True),
    Field("GEMINI_FALLBACK_MODELS", "gemini", "Fallback models", False, False, "model-a,model-b",
          "Comma-separated models tried when the main one is busy. Leave empty for the default list.", advanced=True),
    # Telegram
    Field("TG_BOT_TOKEN", "telegram", "Bot token", True, True, "123456789:AA... (digits, a colon, then letters)",
          "@BotFather > /newbot, then copy the token it sends."),
    Field("TG_CHAT_ID", "telegram", "Chat ID", False, True, "123456789 (a group starts with -)",
          "Press Start on your bot in Telegram, then use Detect my chat."),
    # Cloudinary
    Field("CLOUDINARY_URL", "cloudinary", "API environment variable", True, True, "cloudinary://<key>:<secret>@<cloud name>",
          "Cloudinary > Settings > API Keys: copy the whole 'API environment variable'."),
    # GitHub
    Field("GITHUB_REPOSITORY", "github", "Repository", False, True, "owner/name",
          "Your copy of the automation repository, as owner/name."),
    Field("GITHUB_DISPATCH_TOKEN", "github", "Access token", True, True, "github_pat_...",
          "Fine-grained token: only this repository, Repository permissions > Actions: Read and write."),
    # Not verified from the dashboard yet (listed so status and readiness can show them honestly)
    Field("IG_ACCESS_TOKEN", "instagram", "Access token", True, True, "a long token from the Meta App Dashboard", ""),
    Field("IG_USER_ID", "instagram", "Instagram user ID", False, False, "17841400000000000", ""),
    Field("YT_CLIENT_ID", "youtube", "OAuth client ID", False, True, "....apps.googleusercontent.com", ""),
    Field("YT_CLIENT_SECRET", "youtube", "OAuth client secret", True, True, "GOCSPX-...", ""),
    Field("YT_REFRESH_TOKEN", "youtube", "Refresh token", True, True, "1//...", ""),
    Field("SMTP_HOST", "email", "SMTP host", False, True, "smtp.example.com", ""),
    Field("SMTP_PORT", "email", "SMTP port", False, False, "587", ""),
    Field("SMTP_USER", "email", "SMTP username", False, False, "you@example.com", ""),
    Field("SMTP_PASS", "email", "SMTP password", True, False, "an app password", ""),
    Field("MAIL_FROM", "email", "From address", False, False, "you@example.com", ""),
    Field("GOOGLE_WEB_CLIENT_ID", "google", "Web client ID", False, True, "....apps.googleusercontent.com", ""),
    Field("GOOGLE_WEB_CLIENT_SECRET", "google", "Web client secret", True, True, "GOCSPX-...", ""),
)
FIELDS_BY_NAME = {f.name: f for f in FIELDS}
# Names the resolver may look up in the store (everything above; bootstrap names are never here).
STORE_NAMES = frozenset(FIELDS_BY_NAME)
SECRET_NAMES = frozenset(f.name for f in FIELDS if f.secret)
BOOTSTRAP = frozenset({"DATABASE_URL", "CONFIG_MASTER_KEY", "CONFIG_PRECEDENCE", "JWT_SECRET", "SESSION_SECRET",
                       "ADMIN_USERNAME", "ADMIN_PASSWORD", "ADMIN_PASSWORD_FORCE", "ORIGIN_VERIFY", "PUBLIC_URL",
                       "COOKIE_SECURE", "SSM_PREFIX", "PUBLISH_VIA", "WEB_ORIGIN", "API_DEBUG"})
assert not STORE_NAMES & BOOTSTRAP


def fields_of(integration: str) -> tuple[Field, ...]:
    return tuple(f for f in FIELDS if f.integration == integration)
