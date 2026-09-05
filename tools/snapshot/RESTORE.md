# Restoring Quran Iqra - phoneme worker

How to get this business back after a bad deploy, a wiped database, a lost laptop, or a
deleted note. Written for someone who has this file and nothing else.

> Generated from `~/Code/iqra-phoneme-worker/tools/snapshot/config.json` by
> `node ~/.claude/skills/biz-snapshot/restore-doc.mjs`. **Do not hand-edit** - change the
> config (or the generator) and regenerate, or your edit is lost and, worse, wrong.

## Read this first

Three different things can go wrong and they have three different answers. Pick one:

| What happened | What you actually want | Section |
| --- | --- | --- |
| Code got lost or you need yesterday's source | Check out the dated git tag. | [4](#4-get-the-code-back) |
| Data was deleted or corrupted | Restore from a dated export. **Destructive - read the warning.** | [5](#5-get-the-data-back-the-dangerous-one) |
| This Mac is gone | Fetch the backups from Google Drive first. | [1](#1-if-this-mac-is-gone-get-the-files-first) |

**The single most important rule:** rolling the APP back and rolling the DATA back are
different operations. An image rollback is safe and reversible. A data restore throws
away everything that happened since the snapshot - every lead, order and edit. Default
to the app rollback and leave the data alone unless the data is the thing that broke.

## 0. Where the copies live

| Copy | Location | Holds |
| --- | --- | --- |
| Local (this Mac) | `~/Business-Snapshots/iqra-phoneme-worker/<YYYY-MM-DD>/` | last 60 days |
| Off-machine (Google Drive, `climb-drive` = climblovers@gmail.com) | `climb-drive:Projects Backups/Quran Iqra - phoneme worker/snapshots/<YYYY-MM-DD>/` | **full history** - the local 60-day prune does not propagate |
| Code, off-machine | `climb-drive:Projects Backups/Quran Iqra - phoneme worker/repo.bundle` | full git history, all branches, fixed filename (overwritten nightly, verified before overwrite) |
| Code, off-machine | https://github.com/AwaisJaved458/iqra-phoneme-worker.git | whatever has been pushed |

Each dated folder has a `manifest.json` listing exactly what was captured that night,
including the ready-to-run restore commands with that day's real image refs in them.

## 1. If this Mac is gone: get the files first

On any machine, install rclone and authenticate the `climb-drive` remote against
**climblovers@gmail.com** (the Drive account that owns these backups):

```bash
brew install rclone        # or: curl https://rclone.org/install.sh | sudo bash
rclone config              # n) new remote, name: climb-drive, storage: drive, then the browser login
```
If the config helper on the old Mac is still reachable, `~/.claude/skills/biz-snapshot/setup-own-clientid.sh`
does this with our own published OAuth client (project `rclone-backups`), which is what
the nightly uses. A plain `rclone config` on rclone's shared client also works for reading.

See what dates exist, then pull one:

```bash
rclone lsf "climb-drive:Projects Backups/Quran Iqra - phoneme worker/snapshots/"
rclone copy "climb-drive:Projects Backups/Quran Iqra - phoneme worker/snapshots/<YYYY-MM-DD>" ./restore -P
```
And the code:
```bash
rclone copy "climb-drive:Projects Backups/Quran Iqra - phoneme worker/repo.bundle" . -P
git clone repo.bundle "iqra-phoneme-worker"
```

## 2. Pick a snapshot and read what is in it

```bash
ls "$HOME/Business-Snapshots/iqra-phoneme-worker"
cat "$HOME/Business-Snapshots/iqra-phoneme-worker/<date>/manifest.json"
```
In `manifest.json`:

- `git` - the commit, branch and tag that were live that day
- `data` / `extras` - which exports succeeded that night (`ok: false` means that night's copy is missing - use an earlier date)
- `restore` - **the commands below, pre-filled with that date's real values**. Prefer copying from there over retyping from this file.
- `captured` - artifact count. A snapshot with `captured: 0` is an empty folder; the runner fails on that now, but old folders predate the check.

## 4. Get the code back

Every snapshot sets a local git tag `snap/<date>` on the commit that was checked out,
plus `uncommitted.patch` (tracked-file changes that were not committed) and
`untracked.tar.gz` (new files that were not committed).

```bash
cd "$HOME/Code/iqra-phoneme-worker"
git checkout -b restore/<date> snap/<date>
```
> Never `git reset --hard` main to do this, and never discard the working tree: about two
> dozen Claude sessions share these checkouts and the files you would throw away may be
> another session's live work.

Work that was in flight and never committed that day:

```bash
git apply "<date>/uncommitted.patch"        # tracked files that were modified
tar -xzf "<date>/untracked.tar.gz" -C .     # files that were never added to git
```
If the repo itself is gone (laptop dead, GitHub gone), the bundle is a complete clone
source with all branches and full history:

```bash
rclone copy "climb-drive:Projects Backups/Quran Iqra - phoneme worker/repo.bundle" . -P
git clone repo.bundle "iqra-phoneme-worker"
```
**Gitignored files are NOT in any of this** - tokens, `.env` files and local secrets are
deliberately excluded from the snapshot. After a code restore you will need to put those
back by hand. Live Fly secrets are unaffected by a code restore, so this only matters for
running locally.

## 5. Get the data back (the dangerous one)

> **Read this before running anything in this section.** Restoring data overwrites what is
> live now with what existed on the snapshot date. Everything since - leads, orders,
> messages, edits - is gone, and there is no undo. Restoring the APP (section 3) does not
> touch data; do that first and see whether it was enough.

> Always unpack into a scratch directory and LOOK at it before pushing anything back.

A safe sequence: pull the snapshot to a scratch dir, open it read-only, confirm it holds
what you think it holds, take a fresh snapshot of the CURRENT state (`node ~/.claude/skills/biz-snapshot/snapshot.mjs <config>`)
so today is recoverable too, and only then write.

Every pull helper also writes a `<name>.status.txt` beside its archive with row counts
and a file listing from the night it ran. Diffing two nights' status files is the fastest
way to see a database that has been emptying out. A `<name>.SKIPPED.txt` instead means
the app was not visible that night and nothing was captured.

## 6. Verify, then say what you verified

A restore is not finished when the command exits. Check the thing a customer touches:

Then load the actual page or log in. Report what you checked and what you saw, not that it
"should be working".

## What this backup does NOT cover

Be honest about these when someone asks whether everything is safe:

- **Secret VALUES.** Fly only exposes names and digests. An image rollback keeps the current
  secrets, which is normally what you want, but a from-scratch rebuild needs them re-entered by hand.
- **SaaS state.** Meta/Google Ads settings, Twilio config, Google Business Profile, Shopify
  admin, Chatwoot history and similar live where they live. Nothing here backs them up.
- **Gitignored files** (tokens, `.env`) are excluded on purpose.
- **Freshness.** A pull is only as recent as the last nightly run (21:30, with a launchd
  catch-up at 23:30 if a night is missed). Worst case you lose up to a day.

## Project notes (verbatim from the config)

Hard-won, project-specific detail - which tokens, which account, which restore route was
actually proved to work, and which gaps are known. Read it before a real restore.

```text
Second repo of the Quran Iqra business (vault is covered by the Quran Learning App config). Likely a Cloudflare worker - deployed state not captured, code + history are.
```

---

Full operating detail for the backup system itself - how the nightly runs, the missed-run
guard, Drive auth, and what an INCOMPLETE report means - is in
`~/.claude/skills/biz-snapshot/SKILL.md` (backed up nightly under the "Claude Ops" project).
