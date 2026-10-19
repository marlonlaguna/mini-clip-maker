"""Worker de síntesis Qwen3-TTS ejecutado con .venv-qwen."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel
from guion_audio import parsear_bloques_audio


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

    script = script_path.read_text(encoding="utf-8-sig").strip()
    blocks = parsear_bloques_audio(script)
    if not blocks:
        raise ValueError("El guion no contiene texto para sintetizar.")

    print(f"[QWEN] Cargando {MODEL_ID} en la GPU...")
    print("[QWEN] Se usa float32 por compatibilidad con RTX 2070 (Turing).")
    model = Qwen3TTSModel.from_pretrained(
        MODEL_ID,
        device_map="cuda:0",
        dtype=torch.float32,
    )

    # La variante CustomVoice 0.6B no acepta instrucciones de estilo.
    # Conservamos la metadata para que el formato sea editable y compatible
    # con una variante que sí admita instruct, sin fingir que aquí se aplica.
    model_size = getattr(getattr(model, "model", None), "tts_model_size", "")
    supports_instruct = model_size != "0b6" and "0.6b" not in MODEL_ID.lower()
    if not supports_instruct and any(b.get("instruction") for b in blocks):
        print(
            "[QWEN] Aviso: INSTRUCCION se conserva en el guion, pero "
            "el modelo 0.6B no controla emociones por instrucción."
        )

    pieces: list[np.ndarray] = []
    sample_rate: int | None = None
    pause = np.zeros(int(PAUSE_SECONDS * 24000), dtype=np.float32)

    total_chunks = sum(len(split_text(block["text"])) for block in blocks)
    chunk_index = 0
    for block_index, block in enumerate(blocks):
        block_chunks = split_text(block["text"])
        block_speaker = (block.get("voice") or speaker).strip()
        instruction = block.get("instruction", "").strip()

        for local_index, chunk in enumerate(block_chunks):
            chunk_index += 1
            print(
                f"[QWEN] Generando fragmento {chunk_index}/{total_chunks} "
                f"({block.get('speaker', 'NARRADOR')} / {block_speaker})..."
            )
            kwargs = {}
            if supports_instruct and instruction:
                kwargs["instruct"] = instruction

            wavs, current_sample_rate = model.generate_custom_voice(
                text=chunk,
                language=LANGUAGE,
                speaker=block_speaker,
                **kwargs,
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
                raise RuntimeError(f"Qwen devolvió audio vacío en el fragmento {chunk_index}.")
            pieces.append(audio)
            if local_index < len(block_chunks) - 1:
                pieces.append(pause)

        if block_index < len(blocks) - 1:
            pause_seconds = PAUSE_SECONDS
            if block.get("pause"):
                try:
                    pause_seconds = float(block["pause"])
                except ValueError as exc:
                    raise ValueError(
                        f"PAUSA inválida en el bloque {block_index + 1}: "
                        f"{block['pause']!r}"
                    ) from exc
                if not 0 <= pause_seconds <= 10:
                    raise ValueError("PAUSA debe estar entre 0 y 10 segundos.")
            pieces.append(
                np.zeros(int(pause_seconds * sample_rate), dtype=np.float32)
            )

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
