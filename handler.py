"""RunPod serverless handler — Quran phoneme transcription for the Iqra app.

Runs TBOGamer22/wav2vec2-quran-phonetics (wav2vec2-base + CTC, Apache-2.0):
audio -> a phonetic string (word-delimited by '|'), for tajweed/pronunciation
analysis. This is the ADVISORY (Tier-2) model: the app compares the learner's
phonemes against the reciter's and gently flags where they may differ — never
an authoritative verdict (research SOTA precision is ~0.74).

Request:  {"input": {"audio_base64": "<base64 m4a/aac/wav/mp3>"}}
Response: {"output": {"phonemes": "b i s m i | a l l a a h i | ..."}}
"""

import base64
import io
import os

import librosa
import runpod
import torch
from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

MODEL = os.environ.get("PHONEME_MODEL", "TBOGamer22/wav2vec2-quran-phonetics")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

processor = Wav2Vec2Processor.from_pretrained(MODEL)
model = Wav2Vec2ForCTC.from_pretrained(MODEL).to(DEVICE).eval()


def handler(job):
    inp = job.get("input") or {}
    b64 = inp.get("audio_base64") or inp.get("audio_base_64")
    if not b64:
        return {"error": "Missing 'audio_base64' in input."}

    try:
        audio_bytes = base64.b64decode(b64)
        wav, _ = librosa.load(io.BytesIO(audio_bytes), sr=16000, mono=True)
    except Exception as e:  # noqa: BLE001
        return {"error": f"Could not decode audio: {e}"}

    if wav.size == 0:
        return {"phonemes": "", "empty": True}

    try:
        values = processor(
            wav, sampling_rate=16000, return_tensors="pt"
        ).input_values.to(DEVICE)
        with torch.no_grad():
            logits = model(values).logits
        ids = torch.argmax(logits, dim=-1)
        phonemes = processor.batch_decode(ids)[0]
        return {"phonemes": phonemes.strip(), "model": MODEL}
    except Exception as e:  # noqa: BLE001
        return {"error": f"Inference failed: {e}"}


runpod.serverless.start({"handler": handler})
