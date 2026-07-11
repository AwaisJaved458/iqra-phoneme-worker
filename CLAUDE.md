# Repo notes for Claude

Two unrelated things live in this repo:

## 1. Iqra phoneme worker (repo root)
RunPod serverless worker for Quran phoneme transcription — see `README.md`.
Don't touch unless asked about Iqra.

## 2. YallaEnglish prospecting (`yallaenglish/`, branch `claude/yallaenglish-prospect-filter-157fww`)
Daily scheduled routine that finds Instagram + TikTok influencer prospects
for YallaEnglish (English-learning for Arabic speakers) and sends **50
DM-ready cards** per day to the user's Telegram.

Standing rules (user-set, do not relax without being asked):
- **Never send unscreened prospects.** Everything goes through
  `yallaenglish/prospect_filter.py` (bar: public, 10k–1M followers, activity
  and spam checks — see `yallaenglish/README.md`).
- **Never repeat a handle.** `yallaenglish/sent_ledger.json` records all
  previously sent accounts (`--ledger` handles exclude+append). Commit and
  push the ledger after every run. Ledger was reset 2026-07-11.
- **Never invent handles or follower counts.** A candidate counts only when
  a source explicitly shows handle + follower count together.
- **Broaden the search instead of coming up short** — the broadening ladder
  is in `yallaenglish/README.md`. If 50 genuinely can't be verified, deliver
  fewer with an explicit shortfall note.
- Hand-exclude competitor English-learning apps (zAmericanEnglish, EWA…),
  off-niche celebrities, and reputational risks.
