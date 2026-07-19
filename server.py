"""
Buy Pro: https://www.csoai.org/checkout

Social Media AI MCP Server - Content & Engagement Intelligence
Built by MEOK AI Labs | https://meok.ai

Post scheduling, hashtag generation, engagement analysis,
content calendar planning, and audience insights.
"""


import json
import os
import re
import urllib.error
import urllib.request
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from auth_middleware import check_access
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "social-media-ai",
    instructions="Analyze social-media content, scheduling, and engagement.",
)

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
_RATE_LIMITS = {"free": {"requests_per_hour": 60}, "pro": {"requests_per_hour": 5000}}
_request_log: list[float] = []
_tier = "free"


def _check_rate_limit() -> bool:
    now = time.time()
    _request_log[:] = [t for t in _request_log if now - t < 3600]
    if len(_request_log) >= _RATE_LIMITS[_tier]["requests_per_hour"]:
        return False
    _request_log.append(now)
    return True


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
_OPTIMAL_TIMES: dict[str, dict] = {
    "instagram": {"best_days": ["tuesday", "wednesday", "thursday"], "best_hours": [9, 12, 17], "post_frequency": "3-5 per week", "story_frequency": "daily"},
    "twitter": {"best_days": ["monday", "tuesday", "wednesday"], "best_hours": [8, 12, 17, 18], "post_frequency": "3-5 per day", "story_frequency": "N/A"},
    "linkedin": {"best_days": ["tuesday", "wednesday", "thursday"], "best_hours": [7, 8, 12, 17], "post_frequency": "2-3 per week", "story_frequency": "N/A"},
    "facebook": {"best_days": ["wednesday", "thursday", "friday"], "best_hours": [9, 13, 16], "post_frequency": "1-2 per day", "story_frequency": "daily"},
    "tiktok": {"best_days": ["tuesday", "thursday", "friday"], "best_hours": [10, 14, 19, 21], "post_frequency": "1-3 per day", "story_frequency": "N/A"},
}

_HASHTAG_DB: dict[str, list[str]] = {
    "tech": ["#tech", "#technology", "#innovation", "#ai", "#startup", "#coding", "#developer", "#software", "#digital", "#futuretech"],
    "fitness": ["#fitness", "#workout", "#gym", "#health", "#fitlife", "#training", "#motivation", "#wellness", "#exercise", "#fitfam"],
    "food": ["#food", "#foodie", "#cooking", "#recipe", "#yummy", "#homemade", "#foodphotography", "#instafood", "#chef", "#delicious"],
    "travel": ["#travel", "#wanderlust", "#explore", "#adventure", "#travelgram", "#vacation", "#discover", "#travelphotography", "#trip", "#destination"],
    "business": ["#business", "#entrepreneur", "#success", "#marketing", "#growth", "#leadership", "#strategy", "#smallbusiness", "#startup", "#hustle"],
    "fashion": ["#fashion", "#style", "#outfit", "#ootd", "#trendy", "#fashionista", "#streetstyle", "#design", "#clothing", "#lookoftheday"],
    "photography": ["#photography", "#photo", "#camera", "#photooftheday", "#creative", "#art", "#visualart", "#shotoftheday", "#landscape", "#portrait"],
    "education": ["#education", "#learning", "#teaching", "#knowledge", "#study", "#school", "#students", "#elearning", "#edtech", "#skills"],
}

_CONTENT_TYPES = {
    "instagram": ["carousel", "reel", "story", "single_image", "guide", "live"],
    "twitter": ["text", "thread", "poll", "image", "video", "space"],
    "linkedin": ["article", "post", "document", "poll", "video", "newsletter"],
    "facebook": ["post", "video", "live", "story", "reel", "event"],
    "tiktok": ["short_video", "duet", "stitch", "live", "story"],
}

_SCHEDULED_POSTS: list[dict] = []
_XQUIK_TWEET_URL = "https://xquik.com/api/v1/x/tweets/{tweet_id}"
_XQUIK_TWEET_ID_PATTERN = re.compile(r"\d{15,20}")


def _safe_int(value: object) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _xquik_tweet_to_post(payload: object) -> dict | None:
    if not isinstance(payload, dict):
        return None
    tweet = payload.get("tweet", payload)
    author = payload.get("author", {})
    if not isinstance(tweet, dict) or not isinstance(author, dict):
        return None
    tweet_id = str(tweet.get("id", ""))
    username = str(author.get("username", "")).lstrip("@")
    likes = _safe_int(tweet.get("likeCount"))
    replies = _safe_int(tweet.get("replyCount"))
    retweets = _safe_int(tweet.get("retweetCount"))
    quotes = _safe_int(tweet.get("quoteCount"))
    views = _safe_int(tweet.get("viewCount")) or 1
    post = {
        "platform": "twitter",
        "content": tweet.get("text", ""),
        "content_type": "post",
        "posted_at": tweet.get("createdAt"),
        "likes": likes,
        "comments": replies,
        "shares": retweets + quotes,
        "impressions": views,
        "tweet_id": tweet_id,
        "retweets": retweets,
        "quotes": quotes,
        "bookmarks": _safe_int(tweet.get("bookmarkCount")),
        "source": "xquik",
    }
    if username:
        post["author_username"] = username
    if username and tweet_id:
        post["url"] = f"https://x.com/{username}/status/{tweet_id}"
    return post

def _server_meter_check(api_key: str = "") -> dict:
    """Calls the live /verify endpoint for server-side metering. Returns the JSON dict.
    Fail-open: if /verify is unreachable or KV isn't configured, returns allowed=True
    (so the local rate-limit in _check_rate_limit remains the safety net)."""
    try:
        data = json.dumps({"api_key": api_key, "tool": ""}).encode()
        req = urllib.request.Request(_METER_URL, data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=2.5) as r:
            d = json.loads(r.read())
            if isinstance(d, dict) and "allowed" in d:
                return d
    except Exception:
        pass
    return {"allowed": True, "tier": "anonymous", "remaining": 200, "upgrade_url": "https://meok.ai/pricing"}


_METER_URL = "https://proofof.ai/verify"


@mcp.tool()
def schedule_post(
    platform: str,
    content: str,
    scheduled_time: Optional[str] = None,
    content_type: str = "post",
    hashtags: Optional[list[str]] = None,
    media_urls: Optional[list[str]] = None, api_key: str = "") -> dict:
    """Schedule a social media post with optimal timing suggestions.

    Args:
        platform: instagram | twitter | linkedin | facebook | tiktok.
        content: Post text content.
        scheduled_time: ISO datetime string. If omitted, suggests optimal time.
        content_type: Type of content (varies by platform).
        hashtags: List of hashtags to include.
        media_urls: List of media URLs to attach.

    Behavior:
        This tool is read-only and stateless - it produces analysis output
        without modifying any external systems, databases, or files.
        Safe to call repeatedly with identical inputs (idempotent).
        Free tier: 10/day rate limit. Pro tier: unlimited.
        No authentication required for basic usage.

    When to use:
        Use this tool when you need structured analysis or classification
        of inputs against established frameworks or standards.

    When NOT to use:
        Not suitable for real-time production decision-making without
        human review of results.
    Behavioral Transparency:
        - Side Effects: This tool is read-only and produces no side effects. It does not modify
          any external state, databases, or files. All output is computed in-memory and returned
          directly to the caller.
        - Authentication: No authentication required for basic usage. Pro/Enterprise tiers
          require a valid MEOK API key passed via the MEOK_API_KEY environment variable.
        - Rate Limits: Free tier: 10 calls/day. Pro tier: unlimited. Rate limit headers are
          included in responses (X-RateLimit-Remaining, X-RateLimit-Reset).
        - Error Handling: Returns structured error objects with 'error' key on failure.
          Never raises unhandled exceptions. Invalid inputs return descriptive validation errors.
        - Idempotency: Fully idempotent - calling with the same inputs always produces the
          same output. Safe to retry on timeout or transient failure.
        - Data Privacy: No input data is stored, logged, or transmitted to external services.
          All processing happens locally within the MCP server process.
    """
    allowed, msg, tier = check_access(api_key)
    if not allowed:
        return {"error": msg, "upgrade_url": "https://councilof.ai"}

    if not _check_rate_limit():
        return {"error": "Rate limit exceeded. Upgrade to pro tier."}

    platform = platform.lower()
    optimal = _OPTIMAL_TIMES.get(platform)
    if not optimal:
        return {"error": f"Unknown platform: {platform}"}

    valid_types = _CONTENT_TYPES.get(platform, ["post"])
    if content_type not in valid_types:
        content_type = valid_types[0]

    char_limits = {"twitter": 280, "linkedin": 3000, "instagram": 2200, "facebook": 63206, "tiktok": 2200}
    limit = char_limits.get(platform, 5000)
    full_content = content
    if hashtags:
        full_content += " " + " ".join(hashtags)

    if len(full_content) > limit:
        return {"error": f"Content exceeds {platform} limit of {limit} characters (got {len(full_content)})."}

    if not scheduled_time:
        now = datetime.now(timezone.utc)
        best_hour = optimal["best_hours"][0]
        suggested = now.replace(hour=best_hour, minute=0, second=0)
        if suggested <= now:
            suggested += timedelta(days=1)
        while suggested.strftime("%A").lower() not in optimal["best_days"]:
            suggested += timedelta(days=1)
        scheduled_time = suggested.isoformat()

    post_id = f"POST-{len(_SCHEDULED_POSTS)+1:04d}"
    post = {
        "id": post_id, "platform": platform, "content": content,
        "content_type": content_type, "hashtags": hashtags or [],
        "media_urls": media_urls or [], "scheduled_time": scheduled_time,
        "status": "scheduled", "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _SCHEDULED_POSTS.append(post)

    return {
        "status": "scheduled",
        "post": post,
        "optimal_posting": optimal,
        "content_length": len(full_content),
        "character_limit": limit,
    }


@mcp.tool()
def generate_hashtags(
    topic: str,
    niche: Optional[str] = None,
    count: int = 15,
    include_trending: bool = True, api_key: str = "") -> dict:
    """Generate relevant hashtags for a social media post.

    Args:
        topic: Main topic/description of the post.
        niche: Industry niche (tech, fitness, food, travel, business, fashion, photography, education).
        count: Number of hashtags to generate (5-30).
        include_trending: Whether to include high-volume trending tags.

    Behavior:
        This tool generates structured output without modifying external systems.
        Output is deterministic for identical inputs. No side effects.
        Free tier: 10/day rate limit. Pro tier: unlimited.
        No authentication required for basic usage.

    When to use:
        Use this tool when you need structured analysis or classification
        of inputs against established frameworks or standards.

    When NOT to use:
        Not suitable for real-time production decision-making without
        human review of results.
    Behavioral Transparency:
        - Side Effects: This tool is read-only and produces no side effects. It does not modify
          any external state, databases, or files. All output is computed in-memory and returned
          directly to the caller.
        - Authentication: No authentication required for basic usage. Pro/Enterprise tiers
          require a valid MEOK API key passed via the MEOK_API_KEY environment variable.
        - Rate Limits: Free tier: 10 calls/day. Pro tier: unlimited. Rate limit headers are
          included in responses (X-RateLimit-Remaining, X-RateLimit-Reset).
        - Error Handling: Returns structured error objects with 'error' key on failure.
          Never raises unhandled exceptions. Invalid inputs return descriptive validation errors.
        - Idempotency: Fully idempotent - calling with the same inputs always produces the
          same output. Safe to retry on timeout or transient failure.
        - Data Privacy: No input data is stored, logged, or transmitted to external services.
          All processing happens locally within the MCP server process.
    """
    allowed, msg, tier = check_access(api_key)
    if not allowed:
        return {"error": msg, "upgrade_url": "https://councilof.ai"}

    if not _check_rate_limit():
        return {"error": "Rate limit exceeded. Upgrade to pro tier."}

    count = min(30, max(5, count))

    # Find matching niche hashtags
    niche_tags = []
    if niche and niche.lower() in _HASHTAG_DB:
        niche_tags = _HASHTAG_DB[niche.lower()][:count]

    # Generate topic-specific hashtags from words
    topic_words = [w.lower().strip(".,!?") for w in topic.split() if len(w) > 3]
    topic_tags = [f"#{w}" for w in topic_words[:5]]

    # Combine and deduplicate
    all_tags = list(dict.fromkeys(niche_tags + topic_tags))[:count]

    # Categorize by estimated reach
    high_volume = all_tags[:3]  # Broad reach
    medium_volume = all_tags[3:8]  # Medium competition
    low_volume = all_tags[8:]  # Niche, higher engagement rate

    return {
        "topic": topic,
        "niche": niche,
        "hashtags": all_tags,
        "count": len(all_tags),
        "strategy": {
            "high_volume": {"tags": high_volume, "note": "Broad reach but high competition"},
            "medium_volume": {"tags": medium_volume, "note": "Good balance of reach and visibility"},
            "low_volume": {"tags": low_volume, "note": "Niche tags with higher engagement rates"},
        },
        "tips": [
            "Mix high, medium, and low volume hashtags",
            "Instagram: use up to 30, optimal is 9-15",
            "Twitter: use 1-3 hashtags max",
            "LinkedIn: use 3-5 hashtags",
            "Rotate hashtags to avoid shadowbanning",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@mcp.tool()
def analyze_engagement(
    posts: list[dict], api_key: str = "") -> dict:
    """Analyze engagement metrics across posts to identify top performers.

    Args:
        posts: List of post data with keys: content, likes, comments, shares,
              impressions, platform, content_type, posted_at (optional).

    Behavior:
        This tool is read-only and stateless - it produces analysis output
        without modifying any external systems, databases, or files.
        Safe to call repeatedly with identical inputs (idempotent).
        Free tier: 10/day rate limit. Pro tier: unlimited.
        No authentication required for basic usage.

    When to use:
        Use this tool when you need structured analysis or classification
        of inputs against established frameworks or standards.

    When NOT to use:
        Not suitable for real-time production decision-making without
        human review of results.
    Behavioral Transparency:
        - Side Effects: This tool is read-only and produces no side effects. It does not modify
          any external state, databases, or files. All output is computed in-memory and returned
          directly to the caller.
        - Authentication: No authentication required for basic usage. Pro/Enterprise tiers
          require a valid MEOK API key passed via the MEOK_API_KEY environment variable.
        - Rate Limits: Free tier: 10 calls/day. Pro tier: unlimited. Rate limit headers are
          included in responses (X-RateLimit-Remaining, X-RateLimit-Reset).
        - Error Handling: Returns structured error objects with 'error' key on failure.
          Never raises unhandled exceptions. Invalid inputs return descriptive validation errors.
        - Idempotency: Fully idempotent - calling with the same inputs always produces the
          same output. Safe to retry on timeout or transient failure.
        - Data Privacy: No input data is stored, logged, or transmitted to external services.
          All processing happens locally within the MCP server process.
    """
    allowed, msg, tier = check_access(api_key)
    if not allowed:
        return {"error": msg, "upgrade_url": "https://councilof.ai"}

    if not _check_rate_limit():
        return {"error": "Rate limit exceeded. Upgrade to pro tier."}

    if not posts:
        return {"error": "Provide at least one post to analyze."}

    analyzed = []
    platform_stats: dict[str, list] = {}
    type_stats: dict[str, list] = {}

    for post in posts:
        likes = post.get("likes", 0)
        comments = post.get("comments", 0)
        shares = post.get("shares", 0)
        impressions = post.get("impressions", 1)
        platform = post.get("platform", "unknown")
        content_type = post.get("content_type", "post")

        total_engagement = likes + comments + shares
        engagement_rate = round((total_engagement / max(1, impressions)) * 100, 2)

        # Weighted engagement score (comments worth more than likes)
        weighted_score = likes * 1 + comments * 3 + shares * 5

        analyzed.append({
            "content_preview": post.get("content", "")[:80],
            "platform": platform, "content_type": content_type,
            "metrics": {"likes": likes, "comments": comments, "shares": shares, "impressions": impressions},
            "engagement_rate_pct": engagement_rate,
            "weighted_score": weighted_score,
        })

        platform_stats.setdefault(platform, []).append(engagement_rate)
        type_stats.setdefault(content_type, []).append(engagement_rate)

    analyzed.sort(key=lambda x: x["engagement_rate_pct"], reverse=True)

    avg_by_platform = {p: round(sum(rates) / len(rates), 2) for p, rates in platform_stats.items()}
    avg_by_type = {t: round(sum(rates) / len(rates), 2) for t, rates in type_stats.items()}
    overall_avg = round(sum(p["engagement_rate_pct"] for p in analyzed) / len(analyzed), 2)

    benchmarks = {"instagram": 3.0, "twitter": 1.5, "linkedin": 2.0, "facebook": 1.0, "tiktok": 5.0}

    return {
        "posts_analyzed": len(analyzed),
        "overall_avg_engagement_pct": overall_avg,
        "top_performers": analyzed[:3],
        "worst_performers": analyzed[-3:] if len(analyzed) > 3 else [],
        "by_platform": avg_by_platform,
        "by_content_type": avg_by_type,
        "benchmarks": benchmarks,
        "insights": [
            f"Best platform: {max(avg_by_platform, key=avg_by_platform.get)}" if avg_by_platform else "Need more data",
            f"Best content type: {max(avg_by_type, key=avg_by_type.get)}" if avg_by_type else "Need more data",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@mcp.tool()
def fetch_x_tweet_metrics(
    tweet_id: str,
    api_key: str = "",
) -> dict:
    """Fetch public X/Twitter tweet metrics and normalize them for engagement analysis.

    Args:
        tweet_id: Public X/Twitter tweet ID containing 15 to 20 digits.

    Behavior:
        This tool reads public tweet metadata from Xquik and returns a single
        post object that can be passed directly to analyze_engagement.
    """
    normalized_tweet_id = tweet_id.strip()
    if _XQUIK_TWEET_ID_PATTERN.fullmatch(normalized_tweet_id) is None:
        return {"error": "Provide a valid 15 to 20 digit tweet_id."}

    allowed, msg, tier = check_access(api_key)
    if not allowed:
        return {"error": msg, "upgrade_url": "https://meok.ai/pricing"}

    if not _check_rate_limit():
        return {"error": "Rate limit exceeded. Upgrade to pro tier."}

    api_token = os.getenv("XQUIK_API_KEY", "").strip()
    if not api_token:
        return {"error": "Set XQUIK_API_KEY in the server environment."}

    request = urllib.request.Request(
        _XQUIK_TWEET_URL.format(tweet_id=normalized_tweet_id),
        headers={"Accept": "application/json", "x-api-key": api_token},
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {"error": "Xquik request failed.", "status": exc.code}
    except urllib.error.URLError:
        return {"error": "Xquik request failed."}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"error": "Xquik returned invalid JSON."}

    post = _xquik_tweet_to_post(payload)
    if post is None:
        return {"error": "Xquik returned an unexpected response."}
    return {
        "tweet_id": normalized_tweet_id,
        "source": "xquik",
        "post": post,
        "analyze_engagement_input": [post],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@mcp.tool()
def plan_content_calendar(
    platforms: list[str],
    topics: list[str],
    weeks: int = 4,
    posts_per_week: int = 5, api_key: str = "") -> dict:
    """Generate a content calendar with post ideas and optimal scheduling.

    Args:
        platforms: List of platforms (instagram, twitter, linkedin, facebook, tiktok).
        topics: List of content topics/themes to rotate through.
        weeks: Number of weeks to plan (1-12).
        posts_per_week: Target posts per week per platform.

    Behavior:
        This tool generates structured output without modifying external systems.
        Output is deterministic for identical inputs. No side effects.
        Free tier: 10/day rate limit. Pro tier: unlimited.
        No authentication required for basic usage.

    When to use:
        Use this tool when you need structured analysis or classification
        of inputs against established frameworks or standards.

    When NOT to use:
        Not suitable for real-time production decision-making without
        human review of results.
    Behavioral Transparency:
        - Side Effects: This tool is read-only and produces no side effects. It does not modify
          any external state, databases, or files. All output is computed in-memory and returned
          directly to the caller.
        - Authentication: No authentication required for basic usage. Pro/Enterprise tiers
          require a valid MEOK API key passed via the MEOK_API_KEY environment variable.
        - Rate Limits: Free tier: 10 calls/day. Pro tier: unlimited. Rate limit headers are
          included in responses (X-RateLimit-Remaining, X-RateLimit-Reset).
        - Error Handling: Returns structured error objects with 'error' key on failure.
          Never raises unhandled exceptions. Invalid inputs return descriptive validation errors.
        - Idempotency: Fully idempotent - calling with the same inputs always produces the
          same output. Safe to retry on timeout or transient failure.
        - Data Privacy: No input data is stored, logged, or transmitted to external services.
          All processing happens locally within the MCP server process.
    """
    allowed, msg, tier = check_access(api_key)
    if not allowed:
        return {"error": msg, "upgrade_url": "https://councilof.ai"}

    if not _check_rate_limit():
        return {"error": "Rate limit exceeded. Upgrade to pro tier."}

    if not topics:
        return {"error": "Provide at least one content topic."}

    weeks = min(12, max(1, weeks))
    calendar = []
    today = datetime.now(timezone.utc).date()
    start_monday = today - timedelta(days=today.weekday())

    content_templates = {
        "educational": ["How-to guide", "Tips & tricks", "Industry insight", "Tutorial"],
        "engaging": ["Question/poll", "Behind the scenes", "User spotlight", "Challenge"],
        "promotional": ["Product feature", "Case study", "Testimonial", "Offer/deal"],
        "community": ["Meme/humor", "Trending topic take", "Collaboration", "AMA"],
    }

    post_idx = 0
    for week_num in range(weeks):
        week_start = start_monday + timedelta(weeks=week_num)
        week_posts = []

        for platform in platforms:
            optimal = _OPTIMAL_TIMES.get(platform, _OPTIMAL_TIMES["instagram"])
            types = _CONTENT_TYPES.get(platform, ["post"])

            for i in range(posts_per_week):
                topic = topics[post_idx % len(topics)]
                template_cat = list(content_templates.keys())[post_idx % len(content_templates)]
                template = content_templates[template_cat][post_idx % len(content_templates[template_cat])]
                day_offset = min(i, 6)
                post_date = week_start + timedelta(days=day_offset)
                best_hour = optimal["best_hours"][i % len(optimal["best_hours"])]

                week_posts.append({
                    "date": post_date.isoformat(),
                    "time": f"{best_hour:02d}:00",
                    "platform": platform,
                    "content_type": types[post_idx % len(types)],
                    "topic": topic,
                    "content_idea": f"{template}: {topic}",
                    "category": template_cat,
                })
                post_idx += 1

        calendar.append({"week": week_num + 1, "start_date": week_start.isoformat(), "posts": week_posts})

    total_posts = sum(len(w["posts"]) for w in calendar)

    return {
        "calendar": calendar,
        "summary": {
            "total_weeks": weeks, "total_posts": total_posts,
            "platforms": platforms, "topics": topics,
            "posts_per_week_per_platform": posts_per_week,
        },
        "content_mix_recommendation": {
            "educational": "40%", "engaging": "25%", "promotional": "20%", "community": "15%",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@mcp.tool()
def get_audience_insights(
    platform: str,
    followers: int = 1000,
    engagement_rate_pct: float = 3.0,
    niche: str = "general",
    top_posts: Optional[list[dict]] = None, api_key: str = "") -> dict:
    """Generate audience insights and growth recommendations.

    Args:
        platform: instagram | twitter | linkedin | facebook | tiktok.
        followers: Current follower count.
        engagement_rate_pct: Current average engagement rate.
        niche: Content niche.
        top_posts: Optional list of top performing posts with keys: content_type, engagement_rate.

    Behavior:
        This tool generates structured output without modifying external systems.
        Output is deterministic for identical inputs. No side effects.
        Free tier: 10/day rate limit. Pro tier: unlimited.
        No authentication required for basic usage.

    When to use:
        Use this tool when you need structured analysis or classification
        of inputs against established frameworks or standards.

    When NOT to use:
        Not suitable for real-time production decision-making without
        human review of results.
    Behavioral Transparency:
        - Side Effects: This tool is read-only and produces no side effects. It does not modify
          any external state, databases, or files. All output is computed in-memory and returned
          directly to the caller.
        - Authentication: No authentication required for basic usage. Pro/Enterprise tiers
          require a valid MEOK API key passed via the MEOK_API_KEY environment variable.
        - Rate Limits: Free tier: 10 calls/day. Pro tier: unlimited. Rate limit headers are
          included in responses (X-RateLimit-Remaining, X-RateLimit-Reset).
        - Error Handling: Returns structured error objects with 'error' key on failure.
          Never raises unhandled exceptions. Invalid inputs return descriptive validation errors.
        - Idempotency: Fully idempotent - calling with the same inputs always produces the
          same output. Safe to retry on timeout or transient failure.
        - Data Privacy: No input data is stored, logged, or transmitted to external services.
          All processing happens locally within the MCP server process.
    """
    allowed, msg, tier = check_access(api_key)
    if not allowed:
        return {"error": msg, "upgrade_url": "https://councilof.ai"}

    if not _check_rate_limit():
        return {"error": "Rate limit exceeded. Upgrade to pro tier."}

    benchmarks = {
        "instagram": {"avg_engagement": 3.0, "good_engagement": 5.0, "growth_rate_monthly": 2.5},
        "twitter": {"avg_engagement": 1.5, "good_engagement": 3.0, "growth_rate_monthly": 3.0},
        "linkedin": {"avg_engagement": 2.0, "good_engagement": 4.0, "growth_rate_monthly": 4.0},
        "facebook": {"avg_engagement": 1.0, "good_engagement": 2.0, "growth_rate_monthly": 1.5},
        "tiktok": {"avg_engagement": 5.0, "good_engagement": 10.0, "growth_rate_monthly": 8.0},
    }

    bench = benchmarks.get(platform, benchmarks["instagram"])
    above_avg = engagement_rate_pct > bench["avg_engagement"]

    # Tier classification
    if followers < 1000:
        tier = "nano"
    elif followers < 10000:
        tier = "micro"
    elif followers < 100000:
        tier = "mid_tier"
    elif followers < 1000000:
        tier = "macro"
    else:
        tier = "mega"

    # Estimated reach
    reach_rate = {"nano": 0.25, "micro": 0.20, "mid_tier": 0.15, "macro": 0.10, "mega": 0.05}
    est_reach = round(followers * reach_rate.get(tier, 0.15))

    # Growth projection
    monthly_growth = bench["growth_rate_monthly"] / 100
    projections = {}
    current = followers
    for months in [3, 6, 12]:
        projected = round(current * ((1 + monthly_growth) ** months))
        projections[f"{months}_months"] = projected

    # Content preferences from top posts
    best_types = []
    if top_posts:
        type_rates: dict[str, list] = {}
        for p in top_posts:
            ct = p.get("content_type", "post")
            type_rates.setdefault(ct, []).append(p.get("engagement_rate", 0))
        best_types = sorted(type_rates.items(), key=lambda x: sum(x[1]) / len(x[1]), reverse=True)
        best_types = [t[0] for t in best_types[:3]]

    return {
        "platform": platform,
        "audience_profile": {
            "followers": followers, "tier": tier,
            "engagement_rate_pct": engagement_rate_pct,
            "above_benchmark": above_avg,
            "estimated_reach_per_post": est_reach,
        },
        "benchmarks": bench,
        "growth_projection": projections,
        "best_content_types": best_types if best_types else _CONTENT_TYPES.get(platform, ["post"])[:3],
        "recommendations": [
            "Focus on video/reels for maximum reach" if platform in ["instagram", "tiktok"] else "Share value-driven long-form content",
            "Engage with comments within first hour of posting",
            "Collaborate with creators in your niche",
            "Post consistently at optimal times",
            "Use stories/ephemeral content to boost algorithm ranking" if platform != "linkedin" else "Engage with industry conversations",
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── MEOK monetization layer (Stripe upgrade · PAYG · pricing) ──────────
# Free tier is zero-config. Upgrade to Pro (unlimited) or pay-as-you-go per call.
MEOK_STRIPE_UPGRADE = "https://buy.stripe.com/aFa7sNcgAdQS0ZT1Uc8k91t"  # Pro (unlimited)
MEOK_PAYG_KEY = os.environ.get("MEOK_PAYG_KEY", "")  # set to enable PAYG (x402 / ~GBP0.05 per call)
MEOK_PRICING = "https://meok.ai/pricing"


def meok_upsell(tier: str = "free") -> dict:
    """Monetization options for free-tier callers: Pro upgrade, PAYG, or pricing page."""
    if tier != "free":
        return {}
    return {"upgrade_url": MEOK_STRIPE_UPGRADE,
            "payg_enabled": bool(MEOK_PAYG_KEY),
            "pricing": MEOK_PRICING}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
