#!/usr/bin/env python3
"""Download the video/image creatives for the 124 countertop ads.

Meta's ads_archive API has NO video field. The actual media URLs
(video_hd_url / video_sd_url / original_image_url on *.fbcdn.net) are embedded
as JSON inside each ad's public snapshot page on www.facebook.com. This script
fetches each snapshot page, extracts those URLs (plus the ad's primary body
text, which the API also withholds for US ads), and downloads the media.

NETWORK REQUIREMENT
-------------------
This environment's egress policy currently allows only graph.facebook.com.
Both www.facebook.com and *.fbcdn.net are DENIED (proxy CONNECT 403), so this
script cannot run here until the session's network policy allows:

    www.facebook.com   (snapshot pages)
    web.facebook.com   (redirect host)
    *.fbcdn.net        (video/image CDN, e.g. video-xxx.fbcdn.net, scontent-xxx.fbcdn.net)

Change it at claude.ai/code -> your environment -> network policy, or run this
script on any normal machine (it has no sandbox-specific dependencies):

    pip install requests
    python fb-ads-scraper/scrape_ad_videos.py

Notes on reliability: Ad Library snapshot pages are public (no login), but
Facebook rate-limits and sometimes interstitials automated traffic. The script
uses a browser User-Agent, polite delays, and retries; anything it still can't
fetch is recorded in the output CSV as an error instead of crashing. If plain
HTTP fetches come back empty, install Playwright and re-run with --render to
fully render pages in Chromium (in this sandbox: executablePath
/opt/pw-browsers/chromium is preinstalled).

Usage:
    python scrape_ad_videos.py                 # all ads from the full CSV
    python scrape_ad_videos.py --limit 5       # first 5 (smoke test)
    python scrape_ad_videos.py --ids 994840666762380,1911986836153287
    python scrape_ad_videos.py --no-download   # extract URLs only, skip mp4/jpg downloads
    python scrape_ad_videos.py --render        # use Playwright/Chromium rendering

Outputs:
    output/media/<page_id>/<ad_id>/*.mp4|*.jpg   downloaded creatives
    output/countertop_ads_media.csv              one row per ad: media URLs, body text, local paths, status
"""
import argparse
import csv
import json
import os
import re
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.join(HERE, "output", "countertop_ads_full.csv")
OUT_CSV = os.path.join(HERE, "output", "countertop_ads_media.csv")
MEDIA_DIR = os.path.join(HERE, "output", "media")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Media + body text live in embedded JSON on the snapshot page. Escaped JSON
# string bodies are captured intact and decoded with json.loads afterwards.
JSON_STR = r'"((?:[^"\\]|\\.)*)"'
PATTERNS = {
    "video_hd": re.compile(r'"video_hd_url"\s*:\s*' + JSON_STR),
    "video_sd": re.compile(r'"video_sd_url"\s*:\s*' + JSON_STR),
    "video_preview_img": re.compile(r'"video_preview_image_url"\s*:\s*' + JSON_STR),
    "image_original": re.compile(r'"original_image_url"\s*:\s*' + JSON_STR),
    "image_resized": re.compile(r'"resized_image_url"\s*:\s*' + JSON_STR),
}
BODY_PATTERNS = [
    re.compile(r'"body"\s*:\s*\{\s*"text"\s*:\s*' + JSON_STR),
    re.compile(r'"body"\s*:\s*\{\s*"markup"\s*:\s*\{\s*"__html"\s*:\s*' + JSON_STR),
]


def decode_json_str(raw):
    """Decode a raw escaped JSON string body ('https:\\/\\/...') to text."""
    try:
        return json.loads('"' + raw + '"')
    except ValueError:
        return raw.replace("\\/", "/")


def fetch_html(session, url, retries=3, sleep=2.0):
    last_err = None
    for attempt in range(retries):
        try:
            resp = session.get(url, headers=HEADERS, timeout=45)
            if resp.status_code == 200 and resp.text:
                return resp.text, None
            last_err = "HTTP {}".format(resp.status_code)
        except requests.exceptions.RequestException as exc:
            last_err = str(exc)[:200]
        time.sleep(sleep * (attempt + 1))
    return None, last_err


def render_html(url):
    """Optional Playwright path for JS-walled pages (--render)."""
    from playwright.sync_api import sync_playwright  # imported lazily on purpose
    exe = os.environ.get("CCR_CHROMIUM", "/opt/pw-browsers/chromium")
    with sync_playwright() as pw:
        kwargs = {"headless": True}
        if os.path.exists(exe):
            kwargs["executable_path"] = exe
        browser = pw.chromium.launch(**kwargs)
        try:
            page = browser.new_page(user_agent=UA)
            page.goto(url, wait_until="networkidle", timeout=60000)
            return page.content(), None
        finally:
            browser.close()


def extract_media(html):
    """Pull media URLs + body text out of the snapshot page HTML."""
    found = {}
    for key, pat in PATTERNS.items():
        urls = []
        for m in pat.findall(html):
            u = decode_json_str(m)
            if u.startswith("http") and u not in urls:
                urls.append(u)
        found[key] = urls
    body = ""
    for pat in BODY_PATTERNS:
        m = pat.search(html)
        if m:
            body = decode_json_str(m.group(1))
            body = re.sub(r"<[^>]+>", " ", body)          # markup variant -> plain text
            body = re.sub(r"\s+", " ", body).strip()
            if body:
                break
    return found, body


def download(session, url, dest, retries=2):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return True, "cached"
    for attempt in range(retries + 1):
        try:
            with session.get(url, headers={"User-Agent": UA}, timeout=120, stream=True) as r:
                r.raise_for_status()
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as fh:
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        fh.write(chunk)
            return True, "downloaded"
        except requests.exceptions.RequestException as exc:
            err = str(exc)[:200]
            time.sleep(2 * (attempt + 1))
    return False, err


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", default=DEFAULT_CSV, help="input CSV with ad_id + advertiser columns")
    ap.add_argument("--limit", type=int, default=0, help="only process the first N ads")
    ap.add_argument("--ids", default="", help="comma-separated ad_ids to process")
    ap.add_argument("--sleep", type=float, default=1.5, help="delay between page fetches")
    ap.add_argument("--no-download", action="store_true", help="extract URLs only")
    ap.add_argument("--render", action="store_true", help="render pages with Playwright/Chromium")
    args = ap.parse_args()

    with open(args.csv, newline="", encoding="utf-8") as fh:
        ads = list(csv.DictReader(fh))
    if args.ids:
        wanted = {i.strip() for i in args.ids.split(",") if i.strip()}
        ads = [a for a in ads if a["ad_id"] in wanted]
    if args.limit:
        ads = ads[: args.limit]
    if not ads:
        print("No ads matched.", file=sys.stderr)
        sys.exit(1)

    session = requests.Session()
    rows = []
    n_video = n_image = n_err = 0

    for i, ad in enumerate(ads, 1):
        ad_id = ad["ad_id"]
        page_id = ad.get("page_id", "")
        url = ad.get("ad_snapshot_url") or "https://www.facebook.com/ads/library/?id=" + ad_id
        print("[{}/{}] {} {}".format(i, len(ads), ad.get("advertiser", ""), ad_id))

        if args.render:
            try:
                html, err = render_html(url)
            except Exception as exc:  # playwright missing / crashed
                html, err = None, "render failed: {}".format(str(exc)[:200])
        else:
            html, err = fetch_html(session, url)

        row = {
            "advertiser": ad.get("advertiser", ""),
            "page_id": page_id,
            "ad_id": ad_id,
            "snapshot_url": url,
            "media_type": "",
            "video_hd_url": "",
            "video_sd_url": "",
            "image_urls": "",
            "body_text_scraped": "",
            "local_files": "",
            "status": "",
        }

        if html is None:
            row["status"] = "FETCH_ERROR: {}".format(err)
            n_err += 1
            rows.append(row)
            continue

        media, body = extract_media(html)
        row["body_text_scraped"] = body
        row["video_hd_url"] = " | ".join(media["video_hd"])
        row["video_sd_url"] = " | ".join(media["video_sd"])
        images = media["image_original"] or media["image_resized"]
        row["image_urls"] = " | ".join(images)

        if media["video_hd"] or media["video_sd"]:
            row["media_type"] = "video"
            n_video += 1
        elif images:
            row["media_type"] = "image"
            n_image += 1
        else:
            row["media_type"] = "none_found"
            row["status"] = "no media urls in page (JS wall? try --render)"

        if not args.no_download:
            local = []
            addir = os.path.join(MEDIA_DIR, page_id, ad_id)
            vids = media["video_hd"] or media["video_sd"]  # prefer HD, one quality tier
            for j, vu in enumerate(vids):
                dest = os.path.join(addir, "video_{}.mp4".format(j))
                ok, note = download(session, vu, dest)
                if ok:
                    local.append(os.path.relpath(dest, HERE))
                else:
                    row["status"] = (row["status"] + "; " if row["status"] else "") + \
                        "video dl failed: {}".format(note)
            for j, iu in enumerate(images[:5]):
                dest = os.path.join(addir, "image_{}.jpg".format(j))
                ok, note = download(session, iu, dest)
                if ok:
                    local.append(os.path.relpath(dest, HERE))
            row["local_files"] = " | ".join(local)

        if not row["status"]:
            row["status"] = "ok"
        rows.append(row)
        time.sleep(args.sleep)

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print("-" * 56)
    print("Processed {} ads -> {}".format(len(rows), OUT_CSV))
    print("  video ads:  {}".format(n_video))
    print("  image ads:  {}".format(n_image))
    print("  errors:     {}".format(n_err))
    if n_err == len(rows):
        print("\nEvery fetch failed. If errors mention the proxy (CONNECT 403),")
        print("www.facebook.com is still blocked by this session's network policy —")
        print("see the header of this file for the domains to allow.")


if __name__ == "__main__":
    main()
