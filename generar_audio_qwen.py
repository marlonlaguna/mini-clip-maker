"""Worker Qwen: CustomVoice + voces clonadas por personaje.
Compatible con Mini Clip Maker main actual; no cambia main.py.
"""
from __future__ import annotations
import gc
import io
import json
import re
import sys
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from guion_audio import parsear_bloques_audio
from guion_escenas import parse_scenes
from audio_timeline import assemble_audio
from character_voices import cast_voices

MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
BASE_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
LANGUAGE = "Spanish"
MAX_CHARS_PER_CHUNK = 140
MAX_NEW_TOKENS = 768
MAX_RETRIES = 3
REPETITION_PENALTY = 1.15
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
    chunks = []
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
                piece = ""
                for word in sentence.split():
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


def asignar_voces_personajes(blocks, script_path: Path):
    """Config actual y guion original permiten preservar VOZ explícita.

    main.py añade VOZ global incluso si el diálogo no la tenía. Por eso
    consultamos guion_adaptado.txt, guardado por main antes del worker.
    """
    clip = script_path.parent
    config_path = clip / "config.json"
    source_path = clip / "guion_adaptado.txt"
    if not config_path.exists() or not source_path.exists():
        return blocks
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    if config.get("modo_video") not in ("stick", "mixed"):
        return blocks
    voices = {k.casefold(): v for k, v in cast_voices(config.get("cast") or config.get("personajes") or {}).items()}
    if not voices:
        return blocks
    original = source_path.read_text(encoding="utf-8-sig")
    parts = re.split(r"(?mi)^\[GUION\]\s*", original, maxsplit=1)
    if len(parts) != 2:
        raise ValueError("No se encontró [GUION] en guion_adaptado.txt")
    scenes = parse_scenes(parts[1])
    originals = [e for s in scenes for e in s["entries"] if e["text"]]
    speaking_blocks = [b for b in blocks if b["text"]]
    if len(originals) != len(speaking_blocks):
        raise ValueError("El guion adaptado y el audio no tienen la misma cantidad de diálogos")
    for orig, block in zip(originals, speaking_blocks):
        if orig["speaker"].casefold() != block["speaker"].casefold() or orig["text"].strip() != block["text"].strip():
            raise ValueError("No coinciden los diálogos al asignar voces por personaje")
        if orig["fields"].get("VOZ", "").strip():
            continue   # VOZ explícita gana, incluso si dice Ryan.
        voice = voices.get(block["speaker"].casefold())
        if voice:
            block["voice"] = voice
            print(f"[QWEN] Voz del personaje {block['speaker']}: {Path(voice).name if voice.startswith('clone:') else voice}")
    return blocks


def main() -> int:
    if len(sys.argv) != 4:
        print("Uso: generar_audio_qwen.py <guion.txt> <salida.wav> <voz>", file=sys.stderr)
        return 2
    script_path, output_path = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    speaker = sys.argv[3].strip()
    blocks = parsear_bloques_audio(script_path.read_text(encoding="utf-8-sig"))
    blocks = asignar_voces_personajes(blocks, script_path)
    model = None
    active_model = None
    prompt_cache = {}

    def synthesize(text, voice, instruction):
        nonlocal model, active_model
        import torch
        from qwen_tts import Qwen3TTSModel, VoiceClonePromptItem
        if not torch.cuda.is_available():
            raise RuntimeError("Qwen requiere CUDA. Comprueba PyTorch dentro de .venv-qwen.")
        cloned = str(voice).startswith("clone:")
        required_model = BASE_MODEL_ID if cloned else MODEL_ID
        if active_model != required_model:
            if model is not None:
                del model
                model = None
                gc.collect()
                torch.cuda.empty_cache()
            print(f"[QWEN] Cargando {required_model} en GPU, float32...")
            model = Qwen3TTSModel.from_pretrained(
                required_model, device_map="cuda:0", dtype=torch.float32,
                attn_implementation="sdpa")
            active_model = required_model
        print(f"[QWEN] Voz {voice}: {text[:70]}", flush=True)
        if cloned:
            prompt_path = Path(voice[len("clone:"):]).resolve()
            if prompt_path not in prompt_cache:
                saved = torch.load(prompt_path, map_location="cpu", weights_only=True)
                prompt_cache[prompt_path] = [VoiceClonePromptItem(**item) for item in saved["items"]]

        # Cada diálogo se genera con un límite para prevenir bucles de balbuceo.
        # La API Qwen3-TTS admite parámetros de generación del modelo.
        last_error = None
        for intento in range(1, MAX_RETRIES + 1):
            try:
                print(f"[QWEN] Generando fragmento (intento {intento}/{MAX_RETRIES})...", flush=True)
                kwargs = dict(
                    text=text,
                    language=LANGUAGE,
                    max_new_tokens=MAX_NEW_TOKENS,
                    repetition_penalty=REPETITION_PENALTY,
                )
                with torch.inference_mode():
                    if cloned:
                        wavs, rate = model.generate_voice_clone(
                            **kwargs, voice_clone_prompt=prompt_cache[prompt_path])
                    else:
                        wavs, rate = model.generate_custom_voice(
                            **kwargs, speaker=voice)

                import numpy as np
                wav = np.asarray(wavs[0], dtype=np.float32).reshape(-1)
                if rate <= 0 or wav.size == 0 or not np.all(np.isfinite(wav)):
                    raise ValueError("Qwen produjo audio vacío o no finito")
                duracion = len(wav) / rate
                palabras = max(1, len(text.split()))
                max_duracion = max(10.0, palabras * 1.2 + 5.0)
                if duracion > max_duracion:
                    raise ValueError(
                        f"Audio anormal: {duracion:.1f}s para {palabras} palabras "
                        f"(máximo permitido {max_duracion:.1f}s)")
                print(f"[QWEN] Fragmento OK: {duracion:.1f}s", flush=True)
                return acelerar_voz(wav, rate)
            except (ValueError, RuntimeError) as exc:
                last_error = exc
                print(f"[QWEN] Fragmento fallido: {exc}", flush=True)
                if intento < MAX_RETRIES:
                    # Semilla nueva en cada intento para evitar repetir el mismo fallo.
                    torch.seed()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()

        raise RuntimeError(
            f"[QWEN] No se pudo generar correctamente el fragmento "
            f"tras {MAX_RETRIES} intentos: {text[:90]!r}. Último error: {last_error}")

    audio, timeline = assemble_audio(
        blocks, synthesize, split_text, speaker, pause_seconds=PAUSE_SECONDS)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_path, audio, timeline["sample_rate"])
    output_path.with_suffix(".timeline.json").write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[QWEN] Audio y tiempos guardados: {output_path} ({timeline['duration']:.2f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
