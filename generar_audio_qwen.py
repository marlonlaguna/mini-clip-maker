"""Worker de síntesis Qwen3-TTS ejecutado con .venv-qwen."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel


MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
LANGUAGE = "Spanish"
MAX_CHARS_PER_CHUNK = 280
PAUSE_SECONDS = 0.18


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
        print(
            "Uso: generar_audio_qwen.py <guion.txt> <salida.wav> <voz>",
            file=sys.stderr,
        )
        return 2

    script_path = Path(sys.argv[1]).resolve()
    output_path = Path(sys.argv[2]).resolve()
    speaker = sys.argv[3].strip()

    if not script_path.is_file():
        raise FileNotFoundError(f"No existe el guion: {script_path}")
    if not speaker:
        raise ValueError("La voz Qwen no puede estar vacía.")
    if not torch.cuda.is_available():
        raise RuntimeError(
            "Qwen requiere CUDA para esta configuración. "
            "Comprueba torch.cuda.is_available() dentro de .venv-qwen."
        )

    text = script_path.read_text(encoding="utf-8-sig").strip()
    chunks = split_text(text)
    if not chunks:
        raise ValueError("El guion no contiene texto para sintetizar.")

    print(f"[QWEN] Cargando {MODEL_ID} en la GPU...")
    print("[QWEN] Se usa float32 por compatibilidad con RTX 2070 (Turing).")
    model = Qwen3TTSModel.from_pretrained(
        MODEL_ID,
        device_map="cuda:0",
        dtype=torch.float32,
    )

    pieces: list[np.ndarray] = []
    sample_rate: int | None = None
    pause = np.zeros(int(PAUSE_SECONDS * 24000), dtype=np.float32)

    for index, chunk in enumerate(chunks, start=1):
        print(f"[QWEN] Generando fragmento {index}/{len(chunks)}...")
        wavs, current_sample_rate = model.generate_custom_voice(
            text=chunk,
            language=LANGUAGE,
            speaker=speaker,
        )

        if sample_rate is None:
            sample_rate = int(current_sample_rate)
            pause = np.zeros(
                int(PAUSE_SECONDS * sample_rate),
                dtype=np.float32,
            )
        elif sample_rate != int(current_sample_rate):
            raise RuntimeError("Qwen devolvió frecuencias de muestreo distintas.")

        audio = np.asarray(wavs[0], dtype=np.float32).reshape(-1)
        if audio.size == 0:
            raise RuntimeError(f"Qwen devolvió audio vacío en el fragmento {index}.")
        pieces.append(audio)
        if index < len(chunks):
            pieces.append(pause)

    final_audio = np.concatenate(pieces)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_path, final_audio, sample_rate)
    print(
        f"[QWEN] Audio guardado: {output_path} "
        f"({len(final_audio) / sample_rate:.1f} s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
