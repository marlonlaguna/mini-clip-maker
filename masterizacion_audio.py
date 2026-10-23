"""Masterizacion automatica del MP4 final para Mini Clip Maker.

Requiere FFmpeg/ffprobe disponibles en PATH. No modifica el video original
hasta que la nueva pista se haya codificado correctamente.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


def _ejecutar(args):
    resultado = subprocess.run([str(a) for a in args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if resultado.returncode:
        raise RuntimeError("[MASTER] Fallo FFmpeg:\n" + resultado.stderr[-4000:])
    return resultado


def _mediciones(texto):
    # FFmpeg imprime informacion adicional alrededor del objeto JSON de loudnorm.
    candidatos = re.findall(r"\{[^{}]*\}", texto, re.DOTALL)
    for candidato in reversed(candidatos):
        try:
            datos = json.loads(candidato)
        except json.JSONDecodeError:
            continue
        if all(k in datos for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")):
            return datos
    raise RuntimeError("[MASTER] FFmpeg no devolvio mediciones loudnorm validas.")


def masterizar_video(ruta_video, *, objetivo_lufs=-16.0, pico_dbtp=-1.5, lra=9.0):
    """Mide y normaliza la mezcla final, conservando el video sin recodificar.

    Reemplaza el MP4 original solo si se completa correctamente el proceso.
    """
    ruta = Path(ruta_video).resolve()
    if not ruta.is_file():
        raise FileNotFoundError(ruta)
    objetivo_lufs = float(objetivo_lufs)
    pico_dbtp = float(pico_dbtp)
    lra = float(lra)
    if not -70 <= objetivo_lufs <= -5 or not -9 <= pico_dbtp <= 0 or not 1 <= lra <= 20:
        raise ValueError("[MASTER] Parametros de sonoridad fuera de rango")

    filtro = f"loudnorm=I={objetivo_lufs}:TP={pico_dbtp}:LRA={lra}"
    print(f"[MASTER] Analizando sonoridad: {ruta.name}")
    analisis = _ejecutar([
        "ffmpeg", "-hide_banner", "-nostdin", "-i", ruta,
        "-map", "0:a:0", "-vn", "-af", filtro + ":print_format=json",
        "-f", "null", os.devnull,
    ])
    valores = _mediciones(analisis.stderr)
    segundo_filtro = (
        filtro
        + f":measured_I={valores['input_i']}"
        + f":measured_TP={valores['input_tp']}"
        + f":measured_LRA={valores['input_lra']}"
        + f":measured_thresh={valores['input_thresh']}"
        + f":offset={valores['target_offset']}"
        + ":linear=true:print_format=summary"
    )

    # Temporal en la misma carpeta para que os.replace sea atomico en Windows.
    descriptor, temporal = tempfile.mkstemp(prefix="_master_", suffix=".mp4", dir=ruta.parent)
    os.close(descriptor)
    tmp = Path(temporal)
    try:
        print(f"[MASTER] Aplicando objetivo {objetivo_lufs:g} LUFS / {pico_dbtp:g} dBTP")
        _ejecutar([
            "ffmpeg", "-hide_banner", "-nostdin", "-y", "-i", ruta,
            "-map", "0:v:0", "-map", "0:a:0",
            "-c:v", "copy", "-af", segundo_filtro,
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", tmp,
        ])
        if tmp.stat().st_size == 0:
            raise RuntimeError("[MASTER] La salida generada esta vacia")
        os.replace(tmp, ruta)
    finally:
        if tmp.exists():
            tmp.unlink()
    print(f"[MASTER] Video masterizado: {ruta}")
    return ruta
