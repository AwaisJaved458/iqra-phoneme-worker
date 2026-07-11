# Countertop advertisers — full-creative extraction

Extracts the creative for every ad from the 7 countertop advertisers behind our
"top 20 longest-running ads" list, from Meta's Ad Library.

## Result (as of 2026-07-11)

**124 ads** pulled across all 7 advertisers, **0 with real body text**, 124 with
empty body, **98 carrying a headline (link title)**.

| Advertiser | page_id | US ads | Link titles | EU ads |
|---|---|---:|---:|---:|
| RS Custom Countertops | 1582026298728590 | 25 | 11 | 0 |
| Pacific Stone SoCal | 471114526327906 | 32 | 32 | 0 |
| Stone Masters, Inc. | 175590904720 | 13 | 8 | 0 |
| Sk Stones USA | 172343479474457 | 3 | 3 | 0 |
| Spencer Granite Co | 1881955151887046 | 40 | 33 | 0 |
| ART STONE Surfaces (Atlanta) | 116918619388 | 5 | 5 | 0 |
| Stone Elegance Quartz | 151841294689427 | 6 | 6 | 0 |
| **Total** | | **124** | **98** | **0** |

Outputs in `output/`:
- `countertop_ads_creative.csv` — one row per ad
  (`advertiser, page_id, ad_id, body_text, link_title, snapshot_url, delivery_start, status`)
- `countertop_ads_report.json` — per-advertiser US/EU counts + provenance.

## Why body_text is empty for all 124 ads

Meta only populates `ad_creative_bodies` for ads that **reached the EU**. These
are local US advertisers:

- The US query returns their ads but with no body text (Meta withholds it).
- The EU query (`NL` for all 7, plus `DE` for RS as a second probe) returned
  **0 ads** for every one of them — they simply don't run ads in the EU.

So there is no EU-reached ad from which a body could ever come. The ad's
headline lives in `link_title` (captured, 98 of 124); the full visual creative
(image/video + primary text) is viewable at each `ad_snapshot_url`. The snapshot
pages live on `www.facebook.com`, which this environment's network policy blocks
(only `graph.facebook.com` is allowlisted), so the visual text can't be scraped
here — open the snapshot URLs in a browser to see it.

## How the data was obtained — two paths

**Path used (works): the session's `FB` MCP server** (`mcp__FB__ads_library_search`),
backed by credentials that have Ad Library API access. Queried by `page_id` per
advertiser, US then EU. `build_countertop_csv.py` embeds those exact live
responses verbatim and builds the CSV (fully reproducible from that one file;
it asserts each advertiser's parsed count matches Meta's `estimated_total_count`
so a bad copy fails loudly). Note this tool's response schema returns
`ad_creative_link_title` but not `ad_creative_bodies` / `link_captions` /
`link_descriptions` / `publisher_platforms`.

```bash
python fb-ads-scraper/build_countertop_csv.py
```

**Path for the full field set (blocked): the raw `ads_archive` Graph API** via
the repo's `FACEBOOK_ACCESS_TOKEN`. `extract_countertop_creatives.py` implements
this properly — `search_page_ids` for page-level precision, the full field list
(`ad_creative_bodies`, `link_captions`, `link_descriptions`,
`publisher_platforms`, …), `ad_active_status=ALL`, full pagination, US→EU retry.
It is **currently gated**: every call returns

```
OAuthException  code=10  error_subcode=2332002  "Authorization and login needed"
"To access the API, you'll need to follow the steps at facebook.com/ads/library/api."
```

The token is otherwise valid (expires 2026-09-09, user `Mubashar Javed`, app
`Claude scrape`, scope `ads_read`), but the Ad Library API additionally requires
the account holder to complete a one-time gate that `ads_read` does not cover:

1. Confirm identity + location at <https://www.facebook.com/ID>.
2. Get approved for the Ad Library API at <https://www.facebook.com/ads/library/api>.

Verified: the same `2332002` is returned for every country (US/NL/DE), for both
`search_page_ids` and `search_terms`, with and without `ad_active_status`, across
API versions v19–v23 — so it's an account gate, not a query-shape problem.

Once steps 1–2 are done, run `extract_countertop_creatives.py` for the full
field set (it needs no changes). Note that even then, `ad_creative_bodies` will
stay empty for these advertisers unless they run EU-reached ads.
