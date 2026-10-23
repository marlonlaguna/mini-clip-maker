"""Biblioteca local de voces de personajes; no requiere Qwen para resolver rutas."""
from pathlib import Path
import json

PROJECT = Path(__file__).resolve().parent
CHARACTERS = PROJECT / "stick_engine" / "assets" / "characters"


def voice_for_character(character):
    """Devuelve token clone:<ruta> o nombre CustomVoice, o None."""
    key = str(character).replace("\\", "/").strip("/")
    path = (CHARACTERS / key).resolve()
    if not path.is_relative_to(CHARACTERS.resolve()):
        raise ValueError(f"Character fuera de assets: {character}")
    config_file = path / "voice.json"
    if not config_file.is_file():
        return None
    data = json.loads(config_file.read_text(encoding="utf-8-sig"))
    engine = data.get("engine")
    if engine == "qwen_custom":
        speaker = data.get("speaker")
        if not isinstance(speaker, str) or not speaker.strip():
            raise ValueError(f"Falta speaker en {config_file}")
        return speaker.strip()
    if engine != "qwen_clone":
        raise ValueError(f"Engine desconocido en {config_file}: {engine!r}")
    prompt = data.get("prompt", "voice.pt")
    if not isinstance(prompt, str) or not prompt or Path(prompt).is_absolute():
        raise ValueError(f"Prompt inválido en {config_file}")
    target = (path / prompt).resolve()
    if not target.is_relative_to(path) or not target.is_file() or target.suffix.lower() != '.pt':
        raise ValueError(f"No existe voice.pt válido en {path}: {prompt}")
    return "clone:" + str(target)


def cast_voices(cast):
    return {alias: voice for alias, character in (cast or {}).items()
            if (voice := voice_for_character(character)) is not None}
