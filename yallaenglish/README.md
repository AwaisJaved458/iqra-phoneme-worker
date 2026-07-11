# YallaEnglish prospecting routine

The end-to-end **daily** routine for finding influencer prospects for
YallaEnglish (English-learning for Arabic speakers) on **Instagram and
TikTok**. Each run delivers **50 DM-ready cards** to Telegram. **No prospect
gets sent without passing through `prospect_filter.py` first**, and no handle
is ever repeated — `sent_ledger.json` records everything already sent
(ledger reset on 2026-07-11 at the user's request).

## 1. Discover (until 50 new accounts pass the bar)

Research candidates on BOTH platforms, Arabic and English queries:

- Arabic: `تعلم الانجليزية انستقرام / تيك توك`, `معلم انجليزي مشهور`,
  `أفضل حسابات تعلم الإنجليزية`
- English: `best instagram/tiktok accounts to learn english`,
  `english teacher instagram/tiktok Egypt|Saudi|Dubai|Arab`, `ielts teacher arab`
- Influencer stat sites (StarNgage, HypeAuditor, SocialVeins…) for education
  niches in MENA countries. Many block direct fetches — search-result
  snippets quoting the page are acceptable evidence.

**Evidence rule: a candidate only counts when a source explicitly shows the
handle AND the follower count together. Never guess or invent handles or
numbers. Record the source URL for every account.**

### Broadening ladder — climb it whenever a run comes up short of 50

1. **More countries**: Egypt, Saudi, UAE, Jordan, Kuwait, Qatar, Bahrain,
   Oman, Iraq, Yemen, Syria, Lebanon, Palestine, Algeria, Morocco, Tunisia,
   Libya, Sudan — query each by name in Arabic and English.
2. **Adjacent niches with the same audience**: IELTS/TOEFL/STEP prep, kids'
   English & bilingual parenting, business/job-interview English, English for
   travel/aviation/medicine, study-abroad advisors, polyglot creators with
   Arab followings, English-teaching YouTube/Telegram brands' IG/TikTok
   handles.
3. **Global learn-English creators** in the 10k–1M band (they still reach
   Arab learners).
4. **Long-tail micro accounts (10k–100k)** via hashtag pages
   (#تعلم_الانجليزية, #انجليزي, #learnenglish) and list articles — the micro
   tier is the deepest pool and the most likely to reply to a DM.
5. **Cross-platform mining**: for every good account found on one platform,
   check whether the same creator has a qualifying account on the other.

**Honesty rule: if even the full ladder can't produce 50 *verifiable* new
accounts, send what passed with an explicit shortfall note. Never pad the
list with unverified or invented handles.**

## 2. Screen

```bash
python yallaenglish/prospect_filter.py prospects.json \
    --ledger yallaenglish/sent_ledger.json --take 50 --cards
```

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
| Already sent | not in `sent_ledger.json` | n/a |

Also exclude by hand regardless of numbers:
- **competitor apps/brands** (other English-learning products, e.g.
  zAmericanEnglish, EWA),
- **off-niche celebrities** (edutainment/lifestyle accounts that don't teach
  English),
- **reputational risks** (creators involved in scandals),
- duplicate handles of the same brand (keep the biggest active one).

Input rows may set `"platform": "instagram" | "tiktok"` (default instagram).
Field names are normalised (`followers`/`follower_count`/`followersCount` all
work; counts like `12.5k` are parsed). Put the one-line niche/audience note
in the `bio` field — it appears on the card.

`--ledger` excludes already-sent handles and appends the taken 50, so the
next day's run starts where this one stopped. **Commit and push the updated
ledger after every run.**

## 3. Deliver

Send the 50 cards printed by `--cards`. Each card: handle · platform ·
followers (+engagement when known), niche line, profile link. Add a one-line
personalized DM angle per card referencing the creator's niche. Arabic-native
accounts rank above global ones in outreach value — call out the top 10
worth DMing first. State what was cut and why, and the as-of date of the
follower counts.
