# Iqra phoneme worker (tajweed / pronunciation — advisory tier)

RunPod serverless worker that runs
[`TBOGamer22/wav2vec2-quran-phonetics`](https://huggingface.co/TBOGamer22/wav2vec2-quran-phonetics)
(wav2vec2-base + CTC, 94M params, Apache-2.0) to transcribe Quran recitation
into a **phonetic** string for tajweed / pronunciation analysis.

This is the **Tier-2 advisory** model for the Iqra app. Whisper (the other
endpoint) catches wrong/skipped/extra *words*; this catches *how* a word is
pronounced. Per the research it is **advisory only** — the app compares the
learner's phonemes to the reciter's and gently flags where they may differ;
it never declares a verdict (SOTA precision on this task is ~0.74).

## Deploy on RunPod (build from this repo)

1. RunPod → **Serverless** → **New Endpoint** → **Custom deploy** → **Deploy
   from GitHub** → authorize and pick **`iqra-phoneme-worker`**, branch
   `main`. RunPod builds the Dockerfile (~10 min; the model is baked in).
2. GPU: **any 16 GB** is plenty (the model is tiny). Active Workers `0` is
   fine — the baked-in model makes cold starts quick.
3. Create an endpoint API key and note the endpoint id.

## Contract

Request — `POST https://api.runpod.ai/v2/<id>/runsync`,
`Authorization: Bearer <key>`:

```json
{"input": {"audio_base64": "<base64 m4a/aac/wav/mp3>"}}
```

Response:

```json
{"output": {"phonemes": "b i s m i | a l l a a h i | a r r a h m a a n i | ..."}}
```

The app:
1. Precomputes the **reciter's** phoneme string per ayah once (run this model
   on the everyayah audio) and ships it in the lesson data.
2. At practice time, sends the learner's recording here, gets their phonemes,
   and aligns them against the reciter's — differences become gentle
   "this letter may differ" advisory hints plus the side-by-side replay so
   the learner self-checks.

## Wiring the app

```bash
flutter build ipa --release \
  --dart-define=RUNPOD_ENDPOINT=https://api.runpod.ai/v2/<whisper-id> \
  --dart-define=RUNPOD_API_KEY=<key> \
  --dart-define=PHONEME_ENDPOINT=https://api.runpod.ai/v2/<phoneme-id> \
  --dart-define=PHONEME_API_KEY=<key>
```

If `PHONEME_ENDPOINT` is unset the app simply skips the advisory tier.
