#!/usr/bin/env python3
"""Join the full ad list with the scraped media/body data into one master CSV.

countertop_ads_full.csv    (from build_countertop_csv.py) -> headline + metadata
countertop_ads_media.csv   (from scrape_ad_videos.py)     -> body text + media
                                                              joined on ad_id.

Output: output/countertop_ads_master.csv — the single spreadsheet with the
primary ad copy (scraped body text) sitting next to the headline, plus media
type, video/image URLs, and local downloaded file paths.
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FULL = os.path.join(HERE, "output", "countertop_ads_full.csv")
MEDIA = os.path.join(HERE, "output", "countertop_ads_media.csv")
OUT = os.path.join(HERE, "output", "countertop_ads_master.csv")


def main():
    media = {}
    with open(MEDIA, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            media[r["ad_id"]] = r

    with open(FULL, newline="", encoding="utf-8") as fh:
        full = list(csv.DictReader(fh))

    fields = [
        "advertiser", "page_id", "page_name", "ad_id",
        "ad_creation_time", "ad_delivery_start_time", "currency",
        "link_title", "body_text", "media_type", "n_videos",
        "video_hd_urls", "image_urls", "local_files", "ad_snapshot_url",
    ]

    rows, n_body, n_video = [], 0, 0
    for r in full:
        m = media.get(r["ad_id"], {})
        body = m.get("body_text_scraped", "") or r.get("body_text", "")
        if body:
            n_body += 1
        if (m.get("media_type") or "") == "video":
            n_video += 1
        rows.append({
            "advertiser": r["advertiser"],
            "page_id": r["page_id"],
            "page_name": r.get("page_name", ""),
            "ad_id": r["ad_id"],
            "ad_creation_time": r.get("ad_creation_time", ""),
            "ad_delivery_start_time": r.get("ad_delivery_start_time", ""),
            "currency": r.get("currency", ""),
            "link_title": r.get("link_title", ""),
            "body_text": body,                                  # scraped primary text
            "media_type": m.get("media_type", ""),
            "n_videos": m.get("n_videos", ""),
            "video_hd_urls": m.get("video_hd_urls", ""),
            "image_urls": m.get("image_urls", ""),
            "local_files": m.get("local_files", ""),
            "ad_snapshot_url": r.get("ad_snapshot_url", "")
            or m.get("snapshot_url", ""),
        })

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print("Wrote {} rows -> {}".format(len(rows), OUT))
    print("  with body text: {}".format(n_body))
    print("  video ads:      {}".format(n_video))


if __name__ == "__main__":
    main()
