#!/usr/bin/env python3
"""Fetch subreddit posts and format as markdown."""

import json
import sys
import urllib.request
from datetime import datetime

def fetch_subreddit(subreddit: str, limit: int = 100) -> str:
    """Fetch subreddit JSON and return formatted markdown."""
    url = f"https://www.reddit.com/r/{subreddit}/.json?limit={limit}"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Claude-Reddit-Skill/1.0"}
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        return f"Error: HTTP {e.code} - Could not fetch r/{subreddit}"
    except urllib.error.URLError as e:
        return f"Error: {e.reason}"

    posts = data.get("data", {}).get("children", [])
    if not posts:
        return f"No posts found in r/{subreddit}"

    lines = [f"# r/{subreddit}", ""]

    for i, post in enumerate(posts, 1):
        p = post.get("data", {})
        title = p.get("title", "No title")
        author = p.get("author", "[deleted]")
        score = p.get("score", 0)
        num_comments = p.get("num_comments", 0)
        permalink = f"https://reddit.com{p.get('permalink', '')}"
        created = datetime.fromtimestamp(p.get("created_utc", 0))
        flair = p.get("link_flair_text", "")
        selftext = p.get("selftext", "")[:200]  # First 200 chars
        is_self = p.get("is_self", False)
        url = p.get("url", "")

        lines.append(f"## {i}. {title}")
        lines.append("")
        lines.append(f"**Score:** {score} | **Comments:** {num_comments} | **Author:** u/{author}")
        if flair:
            lines.append(f"**Flair:** {flair}")
        lines.append(f"**Posted:** {created.strftime('%Y-%m-%d %H:%M')}")
        lines.append("")

        if selftext and is_self:
            preview = selftext.replace("\n", " ").strip()
            if len(p.get("selftext", "")) > 200:
                preview += "..."
            lines.append(f"> {preview}")
            lines.append("")
        elif not is_self and url:
            lines.append(f"**Link:** {url}")
            lines.append("")

        lines.append(f"[View post]({permalink})")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: fetch_subreddit.py <subreddit> [limit]")
        sys.exit(1)

    subreddit = sys.argv[1].lstrip("r/")
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 100

    print(fetch_subreddit(subreddit, limit))
