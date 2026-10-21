"""Utilities for keeping speech directions out of the generated narration."""

from __future__ import annotations

import re
from guion_escenas import SCENE, parse_scenes, serialize_scenes


_AUDIO_HEADER = re.compile(r"^\[(?P<header>[^\]\n]*\|[^\]\n]*)\]\s*(?P<inline>.*)$")
_FIELD = re.compile(r"^\s*(VOZ|INSTRUCCION|PAUSA)\s*=\s*(.*?)\s*$", re.IGNORECASE)


def _header_parts(line: str):
    match = _AUDIO_HEADER.match(line.strip())
    if not match:
        return None

    parts = [part.strip() for part in match.group("header").split("|")]
    speaker = parts[0]
    if not speaker or speaker.upper() == "GUION":
        return None

    fields = {}
    for part in parts[1:]:
        field = _FIELD.match(part)
        if field:
            fields[field.group(1).upper()] = field.group(2)

    return {
        "speaker": speaker,
        "voice": fields.get("VOZ", ""),
        "instruction": fields.get("INSTRUCCION", ""),
        "pause": fields.get("PAUSA", ""),
        "inline": match.group("inline").strip(),
    }


def parsear_bloques_audio(texto: str) -> list[dict[str, str]]:
    """Parse tagged speech blocks; plain legacy text is returned as one block."""
    if SCENE.search(texto):
        result = []
        for scene in parse_scenes(texto):
            spoken = [e for e in scene["entries"] if e["text"]]
            for entry in spoken or [{"speaker": "NARRADOR", "fields": {}, "text": ""}]:
                fields = entry["fields"]
                result.append({
                    "speaker": entry["speaker"], "text": entry["text"],
                    "voice": fields.get("VOZ", ""), "instruction": fields.get("INSTRUCCION", ""),
                    "pause": fields.get("PAUSA", ""), "scene": scene["id"],
                    "scene_duration": scene["fields"].get("DURACION", ""),
                })
        return result
    texto = texto.lstrip("\ufeff").strip()
    texto = re.sub(r"^\[GUION\]\s*", "", texto, count=1, flags=re.IGNORECASE)

    bloques: list[dict[str, str]] = []
    actual = None
    lineas = []

    def guardar():
        nonlocal actual, lineas
        if actual is not None:
            cuerpo = "\n".join(lineas).strip()
            if cuerpo:
                actual["text"] = cuerpo
                bloques.append(actual)
        actual = None
        lineas = []

    for linea in texto.splitlines():
        encabezado = _header_parts(linea)
        if encabezado:
            guardar()
            inline = encabezado.pop("inline")
            actual = encabezado
            if inline:
                lineas.append(inline)
        elif actual is None:
            if linea.strip():
                actual = {
                    "speaker": "NARRADOR",
                    "voice": "",
                    "instruction": "",
                    "pause": "",
                }
                lineas.append(linea)
        else:
            lineas.append(linea)

    guardar()

    if not bloques and texto:
        bloques.append({
            "speaker": "NARRADOR",
            "voice": "",
            "instruction": "",
            "pause": "",
            "text": texto,
        })
    return bloques


def limpiar_guion_audio(texto: str) -> str:
    """Return spoken words only, suitable for image/storyboard prompts."""
    return "\n\n".join(
        bloque["text"] for bloque in parsear_bloques_audio(texto)
    ).strip()


def formatear_guion_audio(texto: str, voz_default: str = "Ryan") -> str:
    """Add local TTS metadata after clean script generation; keep old scripts valid."""
    if SCENE.search(texto):
        scenes = parse_scenes(texto)
        for scene in scenes:
            for entry in scene["entries"]:
                if entry["text"]:
                    entry["fields"].setdefault("VOZ", voz_default or "Ryan")
        return "[GUION]\n" + serialize_scenes(scenes)
    bloques = parsear_bloques_audio(texto)
    salida = ["[GUION]"]

    for bloque in bloques:
        voz = (bloque.get("voice") or voz_default or "Ryan").strip()
        partes = [bloque.get("speaker", "NARRADOR").strip() or "NARRADOR"]
        partes.append(f"VOZ={voz}")
        instruccion = bloque.get("instruction", "").strip()
        pausa = bloque.get("pause", "").strip()
        if instruccion:
            partes.append(f"INSTRUCCION={instruccion}")
        if pausa:
            partes.append(f"PAUSA={pausa}")
        salida.append(f"[{ ' | '.join(partes) }]")
        salida.append(bloque["text"].strip())
        salida.append("")

    return "\n".join(salida).rstrip() + "\n"
