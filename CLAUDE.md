# codexonebyhitesh content automation

## Goal

Daily: find trending topics (AI, Dev, DSA, System Design, Interview, OS) → generate 1 reel + 1 carousel per topic → send to Telegram for approval → publish approved items to Instagram, and approved reels
also to YouTube Shorts.

## Stack (free only)

Python 3.11, Gemini API (google-genai), edge-tts, MoviePy + FFmpeg, Playwright (HTML→PNG), Cloudinary (public URLs), python-telegram-bot, GitHub Actions cron. Secrets from .env (python-dotenv) locally, GitHub Secrets in CI. Brand settings in brand/config.yaml.

## Instagram API (Instagram Login, NOT Facebook Graph)

Base: https://graph.instagram.com/v21.0

- Image/carousel item: POST /{IG_USER_ID}/media (image_url, is_carousel_item=true)
- Carousel: POST /{IG_USER_ID}/media (media_type=CAROUSEL, children=ids, caption)
- Reel: POST /{IG_USER_ID}/media (media_type=REELS, video_url, caption)
- Poll container: GET /{container_id}?fields=status_code until FINISHED
- Publish: POST /{IG_USER_ID}/media_publish (creation_id)
- Refresh token: GET https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=...

## Structure

src/fetch_topics.py HN, Reddit, dev.to, GitHub trending, arXiv; dedupe vs data/posted.json
src/rank_topics.py Gemini picks topics per category weights
src/gen_content.py JSON: reel script, carousel slides, caption, hashtags
src/render_post.py HTML/CSS templates → PNG slides (brand colors/fonts/logo/handle)
src/render_reel.py edge-tts voice + animated text slides + subtitles → MP4 (H.264/AAC, 1080x1920)
src/upload.py Cloudinary upload → public URLs
src/approve_bot.py Telegram preview with Approve / Reject / Regenerate buttons
src/publish.py IG publish with retries, then YouTube for reels (per-platform status, --platform ig|yt|all)
src/publish_youtube.py YouTube Data API v3 Shorts upload (same MP4, resumable, YT_PRIVACY default private)
src/refresh_token.py weekly token refresh
main.py orchestrates the pipeline
templates/ HTML slide templates
output/, logs/, data/

## Rules

- NEVER publish without Telegram approval (applies to Instagram AND YouTube).
- Content must be technically accurate; no clickbait lies.
- Log every run; handle API errors with retries + clear messages.
- Build and test one module at a time; add a --dry-run flag everywhere.
- Keep a README with setup + run steps.
