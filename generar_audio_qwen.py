"""Worker de síntesis Qwen3-TTS ejecutado con .venv-qwen."""

from __future__ import annotations

import re
import json
import sys
import io
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from guion_audio import parsear_bloques_audio
from audio_timeline import assemble_audio


MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
LANGUAGE = "Spanish"
MAX_CHARS_PER_CHUNK = 280
PAUSE_SECONDS = 0.18
VELOCIDAD_VOZ = 1.10


def acelerar_voz(audio, rate):
    entrada = io.BytesIO()
    sf.write(entrada, np.asarray(audio), rate, format="WAV", subtype="FLOAT")
    resultado = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
         "-af", f"atempo={VELOCIDAD_VOZ}", "-f", "wav",
         "-acodec", "pcm_f32le", "pipe:1"],
        input=entrada.getvalue(), capture_output=True,
    )
    if resultado.returncode:
        raise RuntimeError(resultado.stderr.decode("utf-8", errors="replace"))
    return sf.read(io.BytesIO(resultado.stdout), dtype="float32")


def split_text(text: str, max_chars: int = MAX_CHARS_PER_CHUNK) -> list[str]:
    """Divide el guion en fragmentos cortos sin perder frases."""
    chunks: list[str] = []

    for paragraph in text.splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        sentences = re.split(r"(?<=[.!?…])\s+", paragraph)
        current = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            if len(sentence) > max_chars:
                if current:
                    chunks.append(current)
                    current = ""
                words = sentence.split()
                piece = ""
                for word in words:
                    candidate = f"{piece} {word}".strip()
                    if len(candidate) > max_chars and piece:
                        chunks.append(piece)
                        piece = word
                    else:
                        piece = candidate
                if piece:
                    current = piece
                continue

            candidate = f"{current} {sentence}".strip()
            if len(candidate) > max_chars and current:
                chunks.append(current)
                current = sentence
            else:
                current = candidate

        if current:
            chunks.append(current)

    return chunks


def main() -> int:
    if len(sys.argv) != 4:
        print("Uso: generar_audio_qwen.py <guion.txt> <salida.wav> <voz>", file=sys.stderr)
        return 2
    script_path, output_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    speaker = sys.argv[3].strip()
    blocks = parsear_bloques_audio(script_path.read_text(encoding="utf-8-sig"))
    model = None
    supports_instruct = False

    def synthesize(text, voice, instruction):
        nonlocal model, supports_instruct
        if model is None:
            import torch
            from qwen_tts import Qwen3TTSModel
            if not torch.cuda.is_available():
                raise RuntimeError("Qwen requiere CUDA. Comprueba PyTorch dentro de .venv-qwen.")
            print(f"[QWEN] Cargando {MODEL_ID} en GPU, float32...")
            model = Qwen3TTSModel.from_pretrained(MODEL_ID, device_map="cuda:0", dtype=torch.float32)
            size = getattr(getattr(model, "model", None), "tts_model_size", "")
            supports_instruct = size != "0b6" and "0.6b" not in MODEL_ID.lower()
            if not supports_instruct and any(b.get("instruction") for b in blocks):
                print("[QWEN] Aviso: el modelo 0.6B conserva INSTRUCCION pero no controla emociones.")
        print(f"[QWEN] Voz {voice}: {text[:70]}")
        kwargs = {"instruct": instruction} if supports_instruct and instruction else {}
        wavs, rate = model.generate_custom_voice(text=text, language=LANGUAGE, speaker=voice, **kwargs)
        return acelerar_voz(wavs[0], rate)

    audio, timeline = assemble_audio(blocks, synthesize, split_text, speaker)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_path, audio, timeline["sample_rate"])
    output_path.with_suffix(".timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[QWEN] Audio y tiempos guardados: {output_path} ({timeline['duration']:.2f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
