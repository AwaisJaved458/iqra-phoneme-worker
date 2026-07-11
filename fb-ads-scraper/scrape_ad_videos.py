#!/usr/bin/env python3
"""Download the video/image creatives + body text for the countertop ads.

Meta's ads_archive API has NO video field and withholds body text for
US-reached ads. Both live in each ad's public snapshot page
(www.facebook.com/ads/library/?id=<ad_id>) as embedded JSON. This script
fetches each page, solves Meta's request-deflection challenge, extracts the
media URLs + primary body text scoped to that ad's snapshot object, and
downloads the creatives from *.fbcdn.net.

How the fetch works (verified live 2026-07-11):
  1. First hit returns HTTP 403 with a tiny JS "challenge" that just POSTs to
     /__rd_verify_<token>?challenge=N and reloads. We replay that POST
     directly; it sets an `rd_challenge` cookie valid for the whole session.
  2. The page then serves ~700-900 KB of HTML which embeds the ad's snapshot
     JSON: videos[].video_hd_url / video_sd_url, images[].original_image_url,
     body.text, plus extra_videos/extra_images/cards for carousels.
  3. IMPORTANT: the page also embeds a feed of UNRELATED ads, so extraction is
     scoped by brace-matching the "snapshot" object that follows OUR
     "ad_archive_id" — never regex the whole page.
  4. Full Chrome header set (Sec-Fetch-*, Sec-Ch-Ua) is required; without it
     Facebook answers 400.

Network requirements: www.facebook.com and *.fbcdn.net must be reachable
(this session's egress policy was updated to allow them; graph.facebook.com
alone is not enough).

Usage:
    python scrape_ad_videos.py                 # all ads from the full CSV
    python scrape_ad_videos.py --limit 5       # smoke test
    python scrape_ad_videos.py --ids 994840666762380,1911986836153287
    python scrape_ad_videos.py --no-download   # extract URLs/body only
    python scrape_ad_videos.py --max-videos 3  # cap videos downloaded per ad

Outputs:
    output/media/<page_id>/<ad_id>/*.mp4|*.jpg   downloaded creatives
    output/countertop_ads_media.csv              per-ad: media urls, body text, local paths, status
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
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Ch-Ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}


def get_page(session, url, retries=3):
    """GET a snapshot page, solving the __rd_verify challenge when served."""
    last = None
    for attempt in range(retries):
        try:
            r = session.get(url, headers=HEADERS, timeout=45)
        except requests.exceptions.RequestException as exc:
            last = str(exc)[:200]
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 403 and "executeChallenge" in r.text:
            m = re.search(r"fetch\('([^']+)'", r.text)
            if m:
                try:
                    session.post("https://www.facebook.com" + m.group(1),
                                 headers=HEADERS, timeout=30)
                except requests.exceptions.RequestException:
                    pass
                continue  # reload on next loop iteration
        if r.status_code == 200 and len(r.text) > 10000:
            return r.text, None
        last = "HTTP {} ({} bytes)".format(r.status_code, len(r.text))
        time.sleep(2 * (attempt + 1))
    return None, last


def brace_match(text, start):
    """Return the balanced JSON object substring starting at text[start]=='{'."""
    depth, i, in_str, esc = 0, start, False, False
    n = len(text)
    while i < n:
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        i += 1
    return None


def extract_for_ad(html, ad_id):
    """Media + body scoped to THIS ad's snapshot (the page embeds other ads too)."""
    out = {"videos_hd": [], "videos_sd": [], "images": [], "preview_imgs": [], "body": ""}
    for m in re.finditer(r'"ad_archive_id"\s*:\s*"?' + re.escape(ad_id) + r'"?', html):
        snap = html.find('"snapshot"', m.end())
        if snap == -1 or snap - m.end() > 5000:
            continue
        obr = html.find("{", snap)
        blob = brace_match(html, obr) if obr != -1 else None
        if not blob:
            continue
        try:
            data = json.loads(blob)
        except ValueError:
            continue
        for v in (data.get("videos") or []) + (data.get("extra_videos") or []):
            if v.get("video_hd_url"):
                out["videos_hd"].append(v["video_hd_url"])
            if v.get("video_sd_url"):
                out["videos_sd"].append(v["video_sd_url"])
            if v.get("video_preview_image_url"):
                out["preview_imgs"].append(v["video_preview_image_url"])
        for im in (data.get("images") or []) + (data.get("extra_images") or []):
            u = im.get("original_image_url") or im.get("resized_image_url")
            if u:
                out["images"].append(u)
        body = data.get("body") or {}
        if isinstance(body, dict):
            out["body"] = out["body"] or (body.get("text") or "")
        for c in (data.get("cards") or []):
            if c.get("video_hd_url"):
                out["videos_hd"].append(c["video_hd_url"])
            if c.get("video_sd_url"):
                out["videos_sd"].append(c["video_sd_url"])
            u = c.get("original_image_url") or c.get("resized_image_url")
            if u:
                out["images"].append(u)
            out["body"] = out["body"] or (c.get("body") or "")
        if out["videos_hd"] or out["videos_sd"] or out["images"] or out["body"]:
            break
    for k in ("videos_hd", "videos_sd", "images", "preview_imgs"):
        out[k] = list(dict.fromkeys(out[k]))
    return out


def download(session, url, dest, retries=2):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return True, "cached"
    err = "unknown"
    for attempt in range(retries + 1):
        try:
            with session.get(url, headers={"User-Agent": UA}, timeout=180, stream=True) as r:
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
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids", default="", help="comma-separated ad_ids")
    ap.add_argument("--sleep", type=float, default=1.5)
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--max-videos", type=int, default=5, help="videos downloaded per ad (dynamic ads carry up to ~10 variants)")
    ap.add_argument("--max-images", type=int, default=5)
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
    n_video = n_image = n_none = n_err = n_body = 0

    for i, ad in enumerate(ads, 1):
        ad_id = ad["ad_id"]
        page_id = ad.get("page_id", "")
        url = "https://www.facebook.com/ads/library/?id=" + ad_id
        html, err = get_page(session, url)

        row = {
            "advertiser": ad.get("advertiser", ""),
            "page_id": page_id,
            "ad_id": ad_id,
            "snapshot_url": url,
            "media_type": "",
            "n_videos": 0,
            "video_hd_urls": "",
            "image_urls": "",
            "body_text_scraped": "",
            "local_files": "",
            "status": "",
        }

        if html is None:
            row["status"] = "FETCH_ERROR: {}".format(err)
            n_err += 1
            rows.append(row)
            print("[{}/{}] {} {} -> FETCH_ERROR".format(i, len(ads), ad.get("advertiser", ""), ad_id))
            time.sleep(args.sleep)
            continue

        media = extract_for_ad(html, ad_id)
        row["body_text_scraped"] = media["body"]
        if media["body"]:
            n_body += 1
        vids = media["videos_hd"] or media["videos_sd"]
        row["n_videos"] = len(vids)
        row["video_hd_urls"] = " | ".join(vids)
        row["image_urls"] = " | ".join(media["images"])

        if vids:
            row["media_type"] = "video"
            n_video += 1
        elif media["images"]:
            row["media_type"] = "image"
            n_image += 1
        else:
            row["media_type"] = "none_found"
            n_none += 1

        if not args.no_download:
            local = []
            addir = os.path.join(MEDIA_DIR, page_id, ad_id)
            for j, vu in enumerate(vids[: args.max_videos]):
                dest = os.path.join(addir, "video_{}.mp4".format(j))
                ok, note = download(session, vu, dest)
                if ok:
                    local.append(os.path.relpath(dest, HERE))
                else:
                    row["status"] = (row["status"] + "; " if row["status"] else "") + \
                        "video {} dl failed: {}".format(j, note)
            for j, iu in enumerate(media["images"][: args.max_images]):
                dest = os.path.join(addir, "image_{}.jpg".format(j))
                ok, note = download(session, iu, dest)
                if ok:
                    local.append(os.path.relpath(dest, HERE))
            row["local_files"] = " | ".join(local)

        if not row["status"]:
            row["status"] = "ok"
        rows.append(row)
        print("[{}/{}] {} {} -> {} ({} videos, {} images){}".format(
            i, len(ads), ad.get("advertiser", ""), ad_id, row["media_type"],
            len(vids), len(media["images"]),
            " body:yes" if media["body"] else ""))
        time.sleep(args.sleep)

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print("-" * 60)
    print("Processed {} ads -> {}".format(len(rows), OUT_CSV))
    print("  video ads:   {}".format(n_video))
    print("  image ads:   {}".format(n_image))
    print("  no media:    {}".format(n_none))
    print("  fetch errors:{}".format(n_err))
    print("  with body:   {}".format(n_body))


if __name__ == "__main__":
    main()
