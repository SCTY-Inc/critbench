---
name: reddit
description: Fetch and format Reddit subreddit content as markdown. Use when the user asks to browse a subreddit, get Reddit posts, check what's trending on Reddit, or mentions r/SubredditName. Triggers on keywords like "reddit", "subreddit", "r/", "trending on reddit", "reddit posts". (user)
---

# Reddit

Fetch subreddit posts via Reddit's public JSON API and format as readable markdown.

## Usage

Run the fetch script with a subreddit name:

```bash
python3 scripts/fetch_subreddit.py CaregiverSupport
python3 scripts/fetch_subreddit.py CaregiverSupport 10  # limit to 10 posts
```

Accepts subreddit with or without `r/` prefix.

## Output Format

Returns markdown with:
- Post title as heading
- Score, comments, author, flair, date
- Preview of self-text or external link
- Direct link to post

## Alternative: WebFetch

For quick one-off fetches without the script:

```
WebFetch: https://www.reddit.com/r/{subreddit}/.json
```

Then parse the JSON response manually.

## Notes

- Reddit rate limits: add `User-Agent` header
- Some subreddits may be private or quarantined
- `.json` endpoint returns top 100 posts by default
