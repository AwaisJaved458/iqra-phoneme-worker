#!/usr/bin/env python3
"""
Extract the FULL creative for every ad from the 7 countertop advertisers
behind our "top 20 longest-running ads" list, straight from Meta's official
`ads_archive` Graph API endpoint.

Why a script and not the vendored MCP tool
-------------------------------------------
The vendored server (fb-ads-scraper/facebook_ads_mcp.py) only searches by
keyword (`search_terms`), which is imprecise for a specific advertiser. This
script adds page-level precision by passing `search_page_ids` to the same
`ads_archive` call, and pulls exactly the fields we need, paginating through
every ad each page has ever run.

EU-only creative bodies
-----------------------
Per Meta's transparency rules, `ad_creative_bodies` (and the other creative
text fields) are only populated for ads that reached the EU. These are US
advertisers, so we query `ad_reached_countries=["US"]` first and, when the
bodies come back empty (or the US query returns nothing), we retry with an EU
country code (NL, then DE) and report what each returns.

Access requirement
------------------
FACEBOOK_ACCESS_TOKEN must have Ad Library API access. NOTE: the `ads_read`
scope alone is NOT sufficient — the person behind the token must additionally
complete identity + location confirmation at https://www.facebook.com/ID and
be approved for the Ad Library API (https://www.facebook.com/ads/library/api).
Until then every ads_archive call returns OAuthException code 10 /
error_subcode 2332002 ("Authorization and login needed"), which this script
captures per-advertiser and records in the output rather than crashing.

Usage
-----
    export FACEBOOK_ACCESS_TOKEN=...   # (already set in this environment)
    python fb-ads-scraper/extract_countertop_creatives.py
"""
import os
import sys
import json
import csv
import time
import argparse

import requests

BASE_URL = "https://graph.facebook.com/v19.0/ads_archive"

# advertiser display name -> Facebook page_id
ADVERTISERS = [
    ("RS Custom Countertops",        "1582026298728590"),
    ("Pacific Stone SoCal",          "471114526327906"),
    ("Stone Masters, Inc.",          "175590904720"),
    ("Sk Stones USA",                "172343479474457"),
    ("Spencer Granite Co",           "1881955151887046"),
    ("ART STONE Surfaces (Atlanta)", "116918619388"),
    ("Stone Elegance Quartz",        "151841294689427"),
]

# exactly the fields the task asked for
FIELDS = [
    "id",
    "ad_creation_time",
    "ad_delivery_start_time",
    "ad_creative_bodies",
    "ad_creative_link_titles",
    "ad_creative_link_captions",
    "ad_creative_link_descriptions",
    "ad_snapshot_url",
    "publisher_platforms",
    "currency",
]

US_COUNTRY = ["US"]
EU_FALLBACKS = [["NL"], ["DE"]]  # try NL first, then DE

PAGE_LIMIT = 100      # ads per page (Graph API max is ~100 for this endpoint)
SLEEP_BETWEEN = 0.3   # be gentle between paged requests
MULTI_JOIN = " || "   # how multiple creative bodies/titles are flattened


def fetch_all(token, page_id, countries):
    """Page through EVERY ad for one page_id in one country set.

    Returns (ads:list, error:dict|None). Follows Graph API `paging.next`
    cursors until exhausted. On the first error the ads collected so far are
    returned alongside the error dict.
    """
    params = {
        "search_page_ids": json.dumps([page_id]),
        "ad_reached_countries": json.dumps(countries),
        "ad_active_status": "ALL",       # include active AND inactive/expired ads
        "fields": ",".join(FIELDS),
        "limit": PAGE_LIMIT,
        "access_token": token,
    }
    ads = []
    url, use_params, first = BASE_URL, params, True
    while True:
        try:
            resp = requests.get(url, params=(use_params if first else None), timeout=60)
        except requests.exceptions.RequestException as exc:
            return ads, {"message": str(exc), "transport_error": True}
        first = False
        try:
            payload = resp.json()
        except ValueError:
            return ads, {"message": resp.text[:300], "http_status": resp.status_code}
        if "error" in payload:
            err = dict(payload["error"])
            err["http_status"] = resp.status_code
            return ads, err
        ads.extend(payload.get("data", []))
        next_url = payload.get("paging", {}).get("next")
        if not next_url:
            return ads, None
        url = next_url  # already contains access_token + params
        time.sleep(SLEEP_BETWEEN)


def has_body(ad):
    """True if the ad carries at least one non-empty creative body string."""
    return any((b or "").strip() for b in (ad.get("ad_creative_bodies") or []))


def join_field(ad, key):
    """Flatten a list-valued creative field into one CSV-safe cell."""
    vals = [str(v).strip() for v in (ad.get(key) or []) if str(v).strip()]
    return MULTI_JOIN.join(vals)


def ad_row(advertiser, page_id, ad, country_label):
    """Build one CSV row for a real ad."""
    return {
        "advertiser": advertiser,
        "page_id": page_id,
        "ad_id": ad.get("id", ""),
        "body_text": join_field(ad, "ad_creative_bodies"),
        "link_title": join_field(ad, "ad_creative_link_titles"),
        "snapshot_url": ad.get("ad_snapshot_url", ""),
        "delivery_start": ad.get("ad_delivery_start_time", ""),
        "status": "{}/{}".format(country_label, "body" if has_body(ad) else "empty"),
    }


def error_status(country_label, err):
    """Compact one-line status describing an API error."""
    code = err.get("code")
    sub = err.get("error_subcode")
    title = err.get("error_user_title") or err.get("message") or "error"
    return "ERROR {} code={}/{} {}".format(country_label, code, sub, title)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "output"),
        help="directory for the CSV + JSON report (default: fb-ads-scraper/output)",
    )
    parser.add_argument(
        "--no-eu-retry",
        action="store_true",
        help="do not fall back to an EU country when US bodies are empty",
    )
    args = parser.parse_args()

    token = os.getenv("FACEBOOK_ACCESS_TOKEN")
    if not token:
        print("FACEBOOK_ACCESS_TOKEN is not set.", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.out_dir, exist_ok=True)
    csv_path = os.path.join(args.out_dir, "countertop_ads_creative.csv")
    report_path = os.path.join(args.out_dir, "countertop_ads_report.json")

    rows = []
    report = []
    totals = {"ads": 0, "with_body": 0, "empty_body": 0}

    for name, pid in ADVERTISERS:
        print("\n=== {}  (page_id {}) ===".format(name, pid))
        entry = {"advertiser": name, "page_id": pid}

        # 1) US first
        us_ads, us_err = fetch_all(token, pid, US_COUNTRY)
        us_bodies = sum(has_body(a) for a in us_ads)
        entry["US"] = {
            "ads": len(us_ads),
            "with_body": us_bodies,
            "error": us_err,
        }
        if us_err:
            print("  US: API error -> {}".format(error_status("US", us_err)))
        else:
            print("  US: {} ads, {} with real body text".format(len(us_ads), us_bodies))

        advertiser_rows = []
        for ad in us_ads:
            advertiser_rows.append(ad_row(name, pid, ad, "US"))

        # 2) EU retry when US gave no usable bodies
        need_eu = (not args.no_eu_retry) and (us_err is not None or len(us_ads) == 0 or us_bodies == 0)
        entry["EU"] = None
        if need_eu:
            for cc in EU_FALLBACKS:
                label = cc[0]
                eu_ads, eu_err = fetch_all(token, pid, cc)
                eu_bodies = sum(has_body(a) for a in eu_ads)
                entry["EU"] = {
                    "country": label,
                    "ads": len(eu_ads),
                    "with_body": eu_bodies,
                    "error": eu_err,
                }
                if eu_err:
                    print("  {}: API error -> {}".format(label, error_status(label, eu_err)))
                    # same token/endpoint => same auth error for every country; stop retrying
                    break
                print("  {}: {} ads, {} with real body text".format(label, len(eu_ads), eu_bodies))
                for ad in eu_ads:
                    advertiser_rows.append(ad_row(name, pid, ad, label))
                if len(eu_ads) > 0:
                    break  # got EU data; no need to try the next EU country

        # 3) if this advertiser produced no ad rows at all, emit a placeholder
        #    row so all 7 advertisers remain visible in the CSV with a reason.
        if not advertiser_rows:
            if us_err:
                status = error_status("US", us_err)
            else:
                eu = entry.get("EU") or {}
                status = "no ads returned (US:{}{})".format(
                    len(us_ads),
                    "; {}:{}".format(eu.get("country"), eu.get("ads")) if eu else "",
                )
            advertiser_rows.append({
                "advertiser": name,
                "page_id": pid,
                "ad_id": "",
                "body_text": "",
                "link_title": "",
                "snapshot_url": "",
                "delivery_start": "",
                "status": status,
            })

        rows.extend(advertiser_rows)
        report.append(entry)

    # tally real ad rows (placeholder rows have no ad_id)
    for r in rows:
        if not r["ad_id"]:
            continue
        totals["ads"] += 1
        if r["status"].endswith("/body"):
            totals["with_body"] += 1
        elif r["status"].endswith("/empty"):
            totals["empty_body"] += 1

    fieldnames = [
        "advertiser", "page_id", "ad_id", "body_text",
        "link_title", "snapshot_url", "delivery_start", "status",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump({"advertisers": report, "totals": totals}, fh, indent=2)

    print("\n" + "=" * 60)
    print("Wrote {} row(s) -> {}".format(len(rows), csv_path))
    print("Report -> {}".format(report_path))
    print("Ads returned:      {}".format(totals["ads"]))
    print("  with real body:  {}".format(totals["with_body"]))
    print("  empty body:      {}".format(totals["empty_body"]))
    print("=" * 60)


if __name__ == "__main__":
    main()
