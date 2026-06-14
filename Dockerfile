FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 HF_HUB_DISABLE_TELEMETRY=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip ffmpeg ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir \
        runpod \
        "torch==2.3.1" \
        "transformers==4.44.2" \
        librosa soundfile

ENV PHONEME_MODEL=TBOGamer22/wav2vec2-quran-phonetics

# Bake the model into the image so cold starts don't download it.
RUN python3 -c "from transformers import Wav2Vec2Processor, Wav2Vec2ForCTC; \
Wav2Vec2Processor.from_pretrained('TBOGamer22/wav2vec2-quran-phonetics'); \
Wav2Vec2ForCTC.from_pretrained('TBOGamer22/wav2vec2-quran-phonetics')"

COPY handler.py /handler.py
CMD ["python3", "-u", "/handler.py"]
