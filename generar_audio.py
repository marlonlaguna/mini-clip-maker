from pathlib import Path
import os
import subprocess
import json
import wave
from guion_audio import parsear_bloques_audio
from guion_escenas import number


BASE_DIR = Path(__file__).resolve().parent
VOZ_QWEN_DEFAULT = "Ryan"


def _python_qwen() -> Path:
    """Busca el intérprete del entorno aislado que contiene Qwen3-TTS."""
    configurado = os.environ.get("QWEN_PYTHON")
    if configurado:
        return Path(configurado).expanduser().resolve()

    if os.name == "nt":
        return BASE_DIR / ".venv-qwen" / "Scripts" / "python.exe"

    return BASE_DIR / ".venv-qwen" / "bin" / "python"


def generar_audio(
    ruta_guion: str | Path,
    ruta_audio: str | Path,
    voz: str = VOZ_QWEN_DEFAULT,
) -> Path:
    """Genera siempre con Qwen3-TTS usando el entorno .venv-qwen."""
    ruta_guion = Path(ruta_guion).resolve()
    ruta_audio = Path(ruta_audio).resolve()
    voz = str(voz or VOZ_QWEN_DEFAULT).strip()
    python_qwen = _python_qwen()
    worker = BASE_DIR / "generar_audio_qwen.py"

    if not ruta_guion.is_file():
        raise FileNotFoundError(f"No existe el guion: {ruta_guion}")
    if ruta_guion.stat().st_size == 0:
        raise ValueError("El archivo del guion está vacío.")
    blocks = parsear_bloques_audio(ruta_guion.read_text(encoding="utf-8-sig"))
    if blocks and not any(b["text"].strip() for b in blocks):
        # Las acciones mudas conservan audio de silencio para música/SFX y montaje,
        # pero no requieren iniciar Qwen ni disponer de CUDA.
        rate, cursor, scenes = 24000, 0, []
        for block in blocks:
            length = round(number(block.get("scene_duration"), "DURACION", 0.01) * rate)
            scenes.append({"id": block["scene"], "start": cursor / rate, "end": (cursor + length) / rate})
            cursor += length
        ruta_audio.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(ruta_audio), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(rate)
            output.writeframes(bytes(cursor * 2))
        timeline = {"schema_version": 1, "speech_activity_version": 1, "sample_rate": rate, "duration": cursor / rate, "scenes": scenes, "blocks": []}
        ruta_audio.with_suffix(".timeline.json").write_text(json.dumps(timeline, indent=2), encoding="utf-8")
        print(f"[AUDIO] Escenas sin diálogo: {cursor / rate:.2f}s; no se carga el motor de voz.")
        return ruta_audio
    if not python_qwen.is_file():
        raise FileNotFoundError(
            f"No encuentro el Python de Qwen: {python_qwen}. "
            "Instala qwen-tts y PyTorch CUDA en .venv-qwen, "
            "o configura la variable QWEN_PYTHON."
        )
    if not worker.is_file():
        raise FileNotFoundError(f"No encuentro el worker Qwen: {worker}")

    ruta_audio.parent.mkdir(parents=True, exist_ok=True)
    print("[AUDIO] Motor: Qwen3-TTS")
    print(f"[AUDIO] Voz: {voz}")
    print(f"[AUDIO] Guion: {ruta_guion}")
    print(f"[AUDIO] Salida: {ruta_audio}")

    subprocess.run(
        [
            str(python_qwen),
            str(worker),
            str(ruta_guion),
            str(ruta_audio),
            voz,
        ],
        check=True,
    )

    if not ruta_audio.is_file() or ruta_audio.stat().st_size == 0:
        raise RuntimeError("Qwen terminó sin crear un archivo de audio válido.")

    return ruta_audio
