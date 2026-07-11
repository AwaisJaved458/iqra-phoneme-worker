# Countertop advertisers — full-creative extraction

Pulls the full creative for every ad from the 7 countertop advertisers behind
our "top 20 longest-running ads" list, straight from Meta's official
`ads_archive` Graph API.

## Run

```bash
export FACEBOOK_ACCESS_TOKEN=...        # already set in the web environment
python fb-ads-scraper/extract_countertop_creatives.py
```

Outputs (in `fb-ads-scraper/output/`):

- `countertop_ads_creative.csv` — one row per ad:
  `advertiser, page_id, ad_id, body_text, link_title, snapshot_url, delivery_start, status`
- `countertop_ads_report.json` — per-advertiser US vs EU counts + raw API errors.

## Advertisers

| Advertiser | page_id |
|---|---|
| RS Custom Countertops | 1582026298728590 |
| Pacific Stone SoCal | 471114526327906 |
| Stone Masters, Inc. | 175590904720 |
| Sk Stones USA | 172343479474457 |
| Spencer Granite Co | 1881955151887046 |
| ART STONE Surfaces (Atlanta) | 116918619388 |
| Stone Elegance Quartz | 151841294689427 |

## How it works

- Page-level precision via `search_page_ids` (the vendored MCP `search_facebook_ads`
  tool only takes a keyword `search_terms`), so we hit each advertiser's page_id
  exactly instead of guessing by brand string.
- `ad_active_status=ALL` so inactive/expired ads are included (longest-running
  ads are often no longer active), and it pages through every `paging.next`
  cursor so nothing is truncated.
- **US → EU retry.** Meta only populates `ad_creative_bodies` (and the other
  creative-text fields) for ads that reached the EU. These are US advertisers,
  so we query `ad_reached_countries=["US"]` first and, when bodies come back
  empty (or the US query is empty), retry with `["NL"]` then `["DE"]`. The
  `status` column records provenance + body presence, e.g. `US/empty`,
  `US/body`, `NL/body`.

## ⚠️ Access blocker (current state)

Every `ads_archive` call currently returns:

```
OAuthException  code=10  error_subcode=2332002
"Authorization and login needed"
"To access the API, you'll need to follow the steps at facebook.com/ads/library/api."
```

The token itself is fine — it is valid (expires 2026‑09‑09), belongs to user
`Mubashar Javed` / app `Claude scrape` (947226971706085), and has the
`ads_read` scope granted. But the **Ad Library API** additionally requires the
person behind the token to complete a one-time gate that `ads_read` does **not**
cover:

1. Confirm identity + location at <https://www.facebook.com/ID>.
2. Get approved for the Ad Library API at
   <https://www.facebook.com/ads/library/api>.

This is verified: the same `2332002` error is returned for every country (US,
NL, DE), for both `search_page_ids` and `search_terms`, with and without
`ad_active_status`, and across API versions v19–v23 — so it is an account gate,
not a query-shape problem. The vendored MCP server uses the same token and
endpoint, so it hits the identical wall.

Once step 1–2 are done, **re-run the command above** — the script needs no
changes and will emit the populated CSV and the real body-vs-empty tally.
