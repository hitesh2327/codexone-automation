"""The Mintly plan catalogue: prices, monthly quotas and platforms. One list for the API and the pipeline.

src/plan_limits.py enforces it; api/app/routes/subscription.py sells it.
"""
from __future__ import annotations

# Prices are in INR before GST (yearly = 10x monthly, 2 months free). Costs behind them (Oct 2026, with a 50% buffer
# for retries): ~Rs 9 per carousel, ~Rs 13 per reel, ~Rs 17 per reel+carousel combo - see the roadmap, item 1.
# quota is per month; posts_per_day is the most a day's schedule can hold. Limits are enforced in roadmap item 2.
PLANS = [
    {
        "id": "lite",
        "name": "Lite",
        "badge": "Carousels only",
        "price_inr_monthly": 699,
        "price_inr_yearly": 6990,
        "posts_per_day": 1,
        "quota": {"reels": 0, "carousels": 30},
        "platforms": ["ig"],
        "features": [
            "30 carousels a month",
            "Instagram carousels",
            "AI topic discovery and writing",
            "Approve every post on Telegram before it goes live",
        ],
        "popular": False,
    },
    {
        "id": "starter",
        "name": "Starter",
        "badge": "For solopreneurs",
        "price_inr_monthly": 1499,
        "price_inr_yearly": 14990,
        "posts_per_day": 1,
        "quota": {"reels": 30, "carousels": 30},
        "platforms": ["ig", "yt"],
        "features": [
            "30 reels + 30 carousels a month (1 a day)",
            "Instagram Reels and carousels",
            "YouTube Shorts",
            "AI topics, scripts and voiceover",
            "Approve every post on Telegram before it goes live",
        ],
        "popular": False,
    },
    {
        "id": "creator",
        "name": "Creator",
        "badge": "Most popular",
        "price_inr_monthly": 2999,
        "price_inr_yearly": 29990,
        "posts_per_day": 2,
        "quota": {"reels": 60, "carousels": 60},
        "platforms": ["ig", "yt"],
        "features": [
            "60 reels + 60 carousels a month (2 a day)",
            "Instagram Reels, carousels and YouTube Shorts",
            "Your niche, tone and brand style",
            "Choice of narration voices",
            "Regenerate and publish now",
        ],
        "popular": True,
    },
    {
        "id": "pro",
        "name": "Pro",
        "badge": "Maximum reach",
        "price_inr_monthly": 5999,
        "price_inr_yearly": 59990,
        "posts_per_day": 4,
        "quota": {"reels": 120, "carousels": 120},
        "platforms": ["ig", "yt"],
        "features": [
            "120 reels + 120 carousels a month (up to 4 a day)",
            "Instagram Reels, carousels and YouTube Shorts",
            "Custom posting schedule",
            "Everything in Creator",
        ],
        "popular": False,
    },
]

BY_ID = {p["id"]: p for p in PLANS}
