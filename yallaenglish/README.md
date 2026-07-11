# YallaEnglish prospect screening

Minimum quality bar for Instagram prospects. **No prospect list gets sent to
Telegram without passing through `prospect_filter.py` first.**

## The bar (defaults)

| Check | Threshold | On missing data |
|---|---|---|
| Account visibility | must be **public** | reject — scraper must provide it |
| Followers | **≥ 10,000** | reject — scraper must provide it |
| Follower cap | **≤ 1,000,000** — mega accounts / big brands (BBC etc.) never collab with small brands; `--max-followers 0` disables | reject — scraper must provide it |
| Posts | ≥ 12 | skipped |
| Followers/following ratio | ≥ 1.0 (filters follow-for-follow spam) | skipped |
| Engagement rate | ≥ 1.0% | skipped |
| Last post | within 60 days | skipped |

Every threshold is a CLI flag (`--min-followers`, `--min-posts`, `--min-ratio`,
`--min-engagement`, `--max-days-since-post`, `--max-followers`,
`--allow-private`), so the bar can be raised per run without code changes.

## Usage

```bash
python yallaenglish/prospect_filter.py prospects.json --telegram
```

- Input: JSON array or CSV of scraped accounts. Field names are normalised
  (`followers` / `follower_count` / `followersCount` all work; counts like
  `12.5k` are parsed).
- Output: `passed.json` (send these) and `rejected.json` (each entry carries
  `rejected_because` so you can see why it was cut). `--telegram` prints a
  ready-to-paste digest ranked by engagement, then followers.

## Rule for future prospecting runs

1. Scrape candidates **including** `is_private`, `followers`, `following`,
   `posts`, and when available `engagement_rate`/`avg_likes` and
   `last_post_date`. Private flag and follower count are mandatory — the
   filter rejects anything missing them.
2. Run the filter.
3. Send **only** the contents of `passed.json` to Telegram, using the digest
   format.
