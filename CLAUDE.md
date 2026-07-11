# Project memory

This repo is the `iqra-phoneme-worker` (a RunPod wav2vec2 phoneme worker), but
it also vendors a **Facebook Ads Library research toolkit** under
`fb-ads-scraper/`. Most agent work here has been ad-creative extraction.

## Facebook Ads Library extraction — how it actually works

Goal pattern: pull every ad (headlines, body text, and video/image creatives)
for a set of advertisers given by Facebook `page_id`.

### The 7 countertop advertisers (reference set)
| Advertiser | page_id |
|---|---|
| RS Custom Countertops | 1582026298728590 |
| Pacific Stone SoCal | 471114526327906 |
| Stone Masters, Inc. | 175590904720 |
| Sk Stones USA | 172343479474457 |
| Spencer Granite Co | 1881955151887046 |
| ART STONE Surfaces (Atlanta) | 116918619388 |
| Stone Elegance Quartz | 151841294689427 |

### Three data sources, and which to trust

1. **`FB` MCP server → `mcp__FB__ads_library_search`** — THE working path for
   ad inventory. Backed by credentials that have Ad Library API access. Query by
   `page_ids` + `countries` (+ `ad_active_status:"ALL"`). Returns id, page_name,
   `ad_creative_link_title`, ad_creation_time, ad_delivery_start_time,
   ad_snapshot_url, currency. Caps at 50 results/page, **no pagination cursor** —
   fine under 50 ads/advertiser, else you lose the tail. Does NOT return body
   text, captions, descriptions, publisher_platforms, or any video.

2. **Raw `ads_archive` Graph API** via `FACEBOOK_ACCESS_TOKEN` (env; vendored
   MCP `facebook_ads_mcp.py` uses it too) — can request the FULL field set
   (`ad_creative_bodies`, captions, descriptions, `publisher_platforms`) with
   `search_page_ids` for precision. **Currently GATED**: every call returns
   `OAuthException code=10 / error_subcode=2332002` ("Authorization and login
   needed"). Token is valid with `ads_read`, but the Ad Library API additionally
   needs the account holder to finish identity+location verification at
   facebook.com/ID → facebook.com/ads/library/api. `ads_read` alone is NOT
   enough. Confirmed unfixable from code (same error across US/NL/DE,
   page-id/keyword, all API versions). Script ready for when it clears:
   `extract_countertop_creatives.py`.

3. **Snapshot pages** (`www.facebook.com/ads/library/?id=<ad_id>`) — THE only
   way to get **videos** (the API has no video field) and the **body text** the
   API withholds for US ads. Script: `scrape_ad_videos.py`. Gotchas that took
   real work to solve:
   - Meta fronts these pages with a deflection challenge: first GET → HTTP 403 +
     a tiny JS that POSTs `/__rd_verify_<token>?challenge=N` and reloads. Replay
     that POST in `requests` (no browser needed); it sets an `rd_challenge`
     cookie for the session.
   - A FULL Chrome header set (`Sec-Fetch-*`, `Sec-Ch-Ua`) is required or FB
     answers 400 after the challenge.
   - The page embeds a feed of UNRELATED ads too — brace-match the `"snapshot"`
     JSON adjacent to the requested `"ad_archive_id"`; never regex the whole page.
   - Media lives at `videos[].video_hd_url/video_sd_url`,
     `images[].original_image_url`, `body.text`, plus `extra_videos/extra_images`
     and carousel `cards`. Download from `*.fbcdn.net`.
   - **Playwright/Chromium does NOT work here** — Chromium can't reach Meta
     hosts through the egress gateway (ERR_CONNECTION_RESET, any HTTP version);
     python-`requests` works. The challenge needs no JS anyway.

### Network policy (remote-environment egress allowlist)
- `graph.facebook.com` — allowed by default (API paths 1 & 2).
- `www.facebook.com`, `web.facebook.com`, `*.fbcdn.net` — NOT default; must be
  added to the environment's network policy for snapshot scraping (path 3).
  Diagnose blocks via `curl -sS "$HTTPS_PROXY/__agentproxy/status"` (403 CONNECT
  = policy denial). For Chromium TLS through the proxy, import the CA into NSS:
  `certutil -d sql:/root/.pki/nssdb -A -t "C,," -n ccr-agent-proxy -i /root/.ccr/agent-proxy-ca.crt`.

### Scripts (all in `fb-ads-scraper/`)
- `build_countertop_csv.py` — embeds live `FB` MCP responses verbatim, builds
  `output/countertop_ads_creative.csv` (8 cols) + `countertop_ads_full.csv`
  (16 cols) + `countertop_ads_report.json`. Asserts parsed count ==
  `estimated_total_count` so a bad copy fails loudly.
- `extract_countertop_creatives.py` — raw `ads_archive` full-field extractor
  (blocked until the token is verified).
- `scrape_ad_videos.py` — snapshot-page video/image/body scraper + downloader.
  Reads `countertop_ads_full.csv`; writes `output/countertop_ads_media.csv` and
  `output/media/<page_id>/<ad_id>/*.mp4|*.jpg`.

### Outputs (last full run: 124 ads, 0 errors)
- 124 ads across the 7 advertisers; **0 had API-exposed body text** (EU-only
  field; these local US advertisers ran 0 EU ads — NL×7 + DE×1 all returned 0).
- Snapshot scrape recovered creatives + body text: **88 video ads, 36 image
  ads, 123/124 body texts**; 125 videos + 50 images (~545 MB).
- `output/media/` is **gitignored** (large, reproducible). The
  `countertop_ads_media.csv` index (URLs, local paths, body text) IS tracked.

## Conventions
- Development branch for this line of work: `claude/fb-ads-countertop-creative-lkqbf2`.
- Don't commit the media binaries or `.local-secrets/`.
- Use the scratchpad dir for temp files, not `/tmp`.
