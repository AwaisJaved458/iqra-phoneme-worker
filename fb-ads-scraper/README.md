# Facebook Ads Library MCP Server

An MCP server that lets Claude search and analyze ads from Meta's public
[Ad Library](https://www.facebook.com/ads/library/) — competitor research,
creative analysis, spend estimation, and data export.

Vendored from [RamsesAguirre777/facebook-ads-library-mcp](https://github.com/RamsesAguirre777/facebook-ads-library-mcp)
(MIT License, see [LICENSE](LICENSE)), with fixes:

- The upstream code imported `WebCrawler` from crawl4ai, which was removed in
  crawl4ai ≥ 0.7 (the version upstream itself pins), so the server crashed on
  startup. Snapshot scraping now uses `AsyncWebCrawler` when crawl4ai is
  installed and falls back to `requests` + BeautifulSoup otherwise, so
  crawl4ai (and its heavy Selenium/browser stack) is optional.
- The Graph API returns `impressions` and `spend` as
  `{"lower_bound": "...", "upper_bound": "..."}` objects; upstream parsed them
  as strings, which crashed several analysis tools. All aggregation now goes
  through a range-midpoint helper.

## Tools

| Tool | What it does |
|------|--------------|
| `search_facebook_ads` | Search the Ad Library by brand/keyword, country, ad type |
| `discover_competitor_brands` | Find active advertisers for industry keywords |
| `analyze_ad_creative_elements` | Scrape an ad snapshot and extract text/CTAs/urgency words |
| `analyze_ad_performance_metrics` | Aggregate impressions/spend/platform/demographic estimates |
| `competitive_ad_analysis` | Compare multiple brands' ad strategies |
| `generate_facebook_intelligence_report` | Full report for one brand incl. competitors |
| `export_facebook_ads_data` | Export results as JSON, CSV, or Markdown |

## Setup

### 1. Install dependencies

```bash
cd fb-ads-scraper
pip install -r requirements.txt
```

### 2. Get a Facebook access token

The server calls Meta's official `ads_archive` Graph API endpoint, which
requires your own token:

1. You need a Facebook developer account and an app
   ([developers.facebook.com](https://developers.facebook.com/)).
2. Open the [Graph API Explorer](https://developers.facebook.com/tools/explorer/),
   select your app, and generate a **User access token** with the `ads_read`
   permission.
3. Optionally [extend it to ~60 days](https://developers.facebook.com/tools/debug/accesstoken/).

### 3. Run / register the server

Standalone check:

```bash
python facebook_ads_mcp.py --facebook-token YOUR_TOKEN
# or
export FACEBOOK_ACCESS_TOKEN=YOUR_TOKEN
python facebook_ads_mcp.py
```

Claude Code:

```bash
claude mcp add facebook-ads -- python /path/to/fb-ads-scraper/facebook_ads_mcp.py --facebook-token YOUR_TOKEN
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "facebook_ads": {
      "command": "python",
      "args": [
        "/path/to/fb-ads-scraper/facebook_ads_mcp.py",
        "--facebook-token",
        "YOUR_FACEBOOK_ACCESS_TOKEN"
      ]
    }
  }
}
```

## Important limitations (read before expecting "all ads")

Despite how this project is marketed on social media, Meta's `ads_archive`
API does **not** expose every ad to everyone:

- **Political/social-issue ads** are available worldwide, but querying them
  requires completing Meta's [identity confirmation](https://www.facebook.com/ID)
  for Ad Library API access.
- **All ad categories (commercial ads included)** are only returned for ads
  that reached the **EU** (Digital Services Act transparency). Searching with
  an EU country code (e.g. `NL`, `DE`, `FR`) returns commercial ads;
  a US-only query generally returns political/issue ads only.
- `impressions` and `spend` are **ranges**, not exact numbers — everything
  labeled "estimated" here is a midpoint of Meta's published range.
- Rate limits apply per app/token; heavy bulk extraction can get the token
  throttled or the app flagged. Keep queries targeted.

The [Ad Library website](https://www.facebook.com/ads/library/) shows all
active ads in every country; the API simply exposes less than the website.
