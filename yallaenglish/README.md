# YallaEnglish prospecting routine

The end-to-end routine for finding influencer prospects for YallaEnglish
(English-learning for Arabic speakers) on **Instagram and TikTok**. **No
prospect list gets sent to Telegram without passing through
`prospect_filter.py` first.**

## 1. Discover

Research candidates on BOTH platforms, Arabic and English queries:

- Arabic: `تعلم الانجليزية انستقرام / تيك توك`, `معلم انجليزي مشهور`,
  `أفضل حسابات تعلم الإنجليزية`
- English: `best instagram/tiktok accounts to learn english`,
  `english teacher instagram/tiktok Egypt|Saudi|Dubai|Arab`, `ielts teacher arab`
- Influencer stat sites (StarNgage, HypeAuditor, SocialVeins…) for education
  niches in Egypt, Saudi, UAE, Jordan, Kuwait, Iraq, Morocco. Many block
  direct fetches — search-result snippets quoting the page are acceptable.

**Evidence rule: a candidate only counts when a source explicitly shows the
handle AND the follower count together. Never guess or invent handles or
numbers. Record the source URL for every account.**

## 2. Screen

Every threshold is a CLI flag; the defaults are the bar:

| Check | Threshold | On missing data |
|---|---|---|
| Account visibility | must be **public** | reject — scraper must provide it |
| Followers | **≥ 10,000** | reject — scraper must provide it |
| Follower cap | **≤ 1,000,000** — mega accounts / big media brands (BBC etc.) never collab with small brands; `--max-followers 0` disables | reject — scraper must provide it |
| Posts | ≥ 12 | skipped |
| Followers/following ratio | ≥ 1.0 (filters follow-for-follow spam) | skipped |
| Engagement rate | ≥ 1.0% | skipped |
| Last post | within 60 days | skipped |

Also exclude by hand regardless of numbers:
- **competitor apps/brands** (other English-learning products),
- **off-niche celebrities** (edutainment/lifestyle accounts that don't teach
  English),
- duplicate handles of the same brand (keep the biggest active one).

```bash
python yallaenglish/prospect_filter.py prospects.json --telegram
```

- Input: JSON array or CSV. Each row may set `"platform": "instagram" |
  "tiktok"` (default instagram). Field names are normalised
  (`followers` / `follower_count` / `followersCount` all work; counts like
  `12.5k` are parsed).
- Output: `passed.json` (send these) and `rejected.json` (each entry carries
  `rejected_because`). `--telegram` prints a ready-to-paste digest ranked by
  engagement then followers, with per-platform profile links.

## 3. Deliver

Send **only** screened accounts, grouped in two tiers:

1. **Arabic-native English-teaching accounts** — best fit, list first.
2. **Global learn-English creators** — bigger reach, less targeted.

Per account: handle, platform, follower count, one-line niche/audience note.
State what was cut and why (private / too small / over cap / off-niche /
competitor), and the as-of date of the follower counts.
