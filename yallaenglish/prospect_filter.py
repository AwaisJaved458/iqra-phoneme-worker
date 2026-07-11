#!/usr/bin/env python3
"""YallaEnglish prospect screening filter.

Takes a raw list of Instagram prospect accounts (JSON or CSV) and applies a
minimum quality bar before anything is sent to Telegram. Accounts that fail
any hard check are rejected with the reason recorded, so the outreach list
only contains public, active, reasonably-sized accounts.

Hard checks (defaults, all configurable via CLI flags):
  - account must be PUBLIC            (private accounts are useless for outreach)
  - followers >= 10,000
  - posts >= 12                       (weeds out empty/parked accounts)
  - followers/following ratio >= 1.0  (weeds out follow-for-follow spam)
  - engagement rate >= 1.0%           (only when the data is available)
  - posted within the last 60 days    (only when the data is available)

Checks that need optional data (engagement, last post date) are skipped when
the scraper didn't provide it — they never reject on missing data. Missing
*mandatory* data (followers, private flag) is a rejection, so the scraper is
forced to supply it.

Usage:
    python prospect_filter.py prospects.json
    python prospect_filter.py prospects.csv --min-followers 25000 --telegram

Outputs passed.json / rejected.json next to the input file (override with
--out-dir) and prints a summary. --telegram additionally prints a
ready-to-paste digest of the accepted accounts.
"""

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Scrapers name the same fields differently; normalise the common aliases.
FIELD_ALIASES = {
    "username": ["username", "handle", "user_name", "account", "ig_username"],
    "full_name": ["full_name", "name", "fullName"],
    "followers": ["followers", "follower_count", "followers_count", "followersCount", "edge_followed_by"],
    "following": ["following", "following_count", "followings", "followingCount", "edge_follow"],
    "posts": ["posts", "post_count", "media_count", "postsCount", "edge_owner_to_timeline_media"],
    "is_private": ["is_private", "private", "isPrivate"],
    "is_verified": ["is_verified", "verified", "isVerified"],
    "engagement_rate": ["engagement_rate", "engagement", "er", "engagementRate"],
    "avg_likes": ["avg_likes", "average_likes", "avgLikes"],
    "avg_comments": ["avg_comments", "average_comments", "avgComments"],
    "last_post_date": ["last_post_date", "last_post", "latest_post_date", "lastPostDate"],
    "bio": ["bio", "biography", "description"],
    "url": ["url", "profile_url", "link"],
}

TRUTHY = {"true", "1", "yes", "y", "private"}


@dataclass
class Verdict:
    prospect: dict
    reasons: list = field(default_factory=list)

    @property
    def passed(self):
        return not self.reasons


def _get(raw, key):
    for alias in FIELD_ALIASES[key]:
        if alias in raw and raw[alias] not in (None, ""):
            return raw[alias]
    return None


def _as_int(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower().replace(",", "").replace(" ", "")
    try:
        if text.endswith("k"):
            return int(float(text[:-1]) * 1_000)
        if text.endswith("m"):
            return int(float(text[:-1]) * 1_000_000)
        return int(float(text))
    except ValueError:
        return None


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    return str(value).strip().lower() in TRUTHY


def _as_float(value):
    if value is None:
        return None
    try:
        return float(str(value).strip().rstrip("%"))
    except ValueError:
        return None


def _days_since(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):  # unix timestamp
        dt = datetime.fromtimestamp(value, tz=timezone.utc)
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).days


def normalize(raw):
    prospect = {key: _get(raw, key) for key in FIELD_ALIASES}
    prospect["followers"] = _as_int(prospect["followers"])
    prospect["following"] = _as_int(prospect["following"])
    prospect["posts"] = _as_int(prospect["posts"])
    prospect["is_private"] = _as_bool(prospect["is_private"])
    prospect["is_verified"] = _as_bool(prospect["is_verified"])
    prospect["avg_likes"] = _as_int(prospect["avg_likes"])
    prospect["avg_comments"] = _as_int(prospect["avg_comments"])
    prospect["engagement_rate"] = _as_float(prospect["engagement_rate"])
    # Derive engagement from avg likes/comments when not given directly.
    if prospect["engagement_rate"] is None and prospect["followers"]:
        interactions = (prospect["avg_likes"] or 0) + (prospect["avg_comments"] or 0)
        if interactions:
            prospect["engagement_rate"] = round(interactions / prospect["followers"] * 100, 2)
    prospect["days_since_post"] = _days_since(prospect["last_post_date"])
    return prospect


def screen(prospect, args):
    verdict = Verdict(prospect)
    reject = verdict.reasons.append

    if not prospect["username"]:
        reject("missing username")
        return verdict

    if prospect["is_private"] is None:
        reject("missing private/public flag — scraper must provide it")
    elif prospect["is_private"] and not args.allow_private:
        reject("private account")

    if prospect["followers"] is None:
        reject("missing follower count — scraper must provide it")
    elif prospect["followers"] < args.min_followers:
        reject(f"only {prospect['followers']:,} followers (min {args.min_followers:,})")
    elif args.max_followers and prospect["followers"] > args.max_followers:
        reject(f"{prospect['followers']:,} followers exceeds cap of {args.max_followers:,}")

    if prospect["posts"] is not None and prospect["posts"] < args.min_posts:
        reject(f"only {prospect['posts']} posts (min {args.min_posts})")

    if prospect["followers"] and prospect["following"]:
        ratio = prospect["followers"] / prospect["following"]
        if ratio < args.min_ratio:
            reject(
                f"followers/following ratio {ratio:.2f} below {args.min_ratio}"
                " — looks like follow-for-follow"
            )

    if prospect["engagement_rate"] is not None and prospect["engagement_rate"] < args.min_engagement:
        reject(f"engagement {prospect['engagement_rate']}% below {args.min_engagement}%")

    if prospect["days_since_post"] is not None and prospect["days_since_post"] > args.max_days_since_post:
        reject(f"last post {prospect['days_since_post']} days ago (max {args.max_days_since_post})")

    return verdict


def load_prospects(path):
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as fh:
            return list(csv.DictReader(fh))
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):  # tolerate {"prospects": [...]} wrappers
        for value in data.values():
            if isinstance(value, list):
                return value
        raise SystemExit("No prospect list found inside the JSON object.")
    return data


def telegram_digest(passed):
    lines = ["YallaEnglish prospects — screened, all public & above the minimum bar:", ""]
    ranked = sorted(passed, key=lambda p: (p["engagement_rate"] or 0, p["followers"] or 0), reverse=True)
    for i, p in enumerate(ranked, 1):
        bits = [f"{p['followers']:,} followers"]
        if p["engagement_rate"] is not None:
            bits.append(f"{p['engagement_rate']}% engagement")
        if p["posts"] is not None:
            bits.append(f"{p['posts']} posts")
        lines.append(f"{i}. @{p['username']} — {', '.join(bits)}")
        lines.append(f"   https://instagram.com/{p['username']}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Screen YallaEnglish Instagram prospects.")
    parser.add_argument("input", type=Path, help="prospects file (.json or .csv)")
    parser.add_argument("--min-followers", type=int, default=10_000)
    parser.add_argument("--max-followers", type=int, default=None,
                        help="optional cap, e.g. 500000 to skip mega accounts that never reply")
    parser.add_argument("--min-posts", type=int, default=12)
    parser.add_argument("--min-ratio", type=float, default=1.0,
                        help="minimum followers/following ratio")
    parser.add_argument("--min-engagement", type=float, default=1.0,
                        help="minimum engagement %% (skipped when data missing)")
    parser.add_argument("--max-days-since-post", type=int, default=60,
                        help="reject accounts inactive longer than this (skipped when data missing)")
    parser.add_argument("--allow-private", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="where to write passed.json / rejected.json (default: next to input)")
    parser.add_argument("--telegram", action="store_true",
                        help="print a ready-to-send Telegram digest of the accepted accounts")
    args = parser.parse_args()

    verdicts = [screen(normalize(raw), args) for raw in load_prospects(args.input)]
    passed = [v.prospect for v in verdicts if v.passed]
    rejected = [{**v.prospect, "rejected_because": v.reasons} for v in verdicts if not v.passed]

    out_dir = args.out_dir or args.input.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "passed.json").write_text(json.dumps(passed, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "rejected.json").write_text(json.dumps(rejected, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Screened {len(verdicts)} prospects: {len(passed)} passed, {len(rejected)} rejected.")
    for entry in rejected:
        print(f"  ✗ @{entry.get('username') or '<no username>'}: {'; '.join(entry['rejected_because'])}")
    print(f"\nWrote {out_dir / 'passed.json'} and {out_dir / 'rejected.json'}")

    if args.telegram:
        if passed:
            print("\n--- Telegram digest ---\n")
            print(telegram_digest(passed))
        else:
            print("\nNothing passed the bar — nothing to send.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
