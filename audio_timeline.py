"""Ensamblado de voz y silencio con tiempos exactos, independiente de Qwen/CUDA."""
from __future__ import annotations
import numpy as np
from guion_escenas import number


def voice_intervals(audio, sample_rate):
    """Actividad de voz por energía, antes de añadir música y efectos."""
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    step = max(1, round(sample_rate * 0.04))
    energy = [float(np.sqrt(np.mean(audio[i:i + step].astype(np.float64) ** 2)))
              for i in range(0, len(audio), step)]
    if not energy:
        return []
    threshold = max(0.003, float(np.percentile(energy, 90)) * 0.12)
    intervals = []
    for i, rms in enumerate(energy):
        if rms < threshold:
            continue
        start = max(0.0, i * step / sample_rate - 0.02)
        end = min(len(audio) / sample_rate, (i + 1) * step / sample_rate + 0.04)
        if intervals and start - intervals[-1][1] <= 0.04 + 1e-8:
            intervals[-1][1] = end
        else:
            intervals.append([start, end])
    return intervals


def assemble_audio(blocks, synthesize, split_text, default_voice, sample_rate=24000, pause_seconds=0.18):
    pieces, speech_timeline, scene_timeline = [], [], []
    samples = 0
    current_scene = None
    scene_start = 0
    minimum = 0.0
    structured = any("scene" in b for b in blocks)

    def silence(seconds):
        nonlocal samples
        size = max(0, round(seconds * sample_rate))
        if size:
            pieces.append(np.zeros(size, dtype=np.float32))
            samples += size

    def close_scene():
        if current_scene is not None:
            if minimum and (samples - scene_start) / sample_rate > minimum + 0.001:
                print(f"[AUDIO] AVISO: escena {current_scene} se alarga para conservar el diálogo completo.")
            silence(max(0, minimum - (samples - scene_start) / sample_rate))
            scene_timeline.append({"id": current_scene, "start": scene_start / sample_rate, "end": samples / sample_rate})

    for index, block in enumerate(blocks):
        sid = str(block.get("scene", index + 1))
        if sid != current_scene:
            close_scene()
            current_scene, scene_start = sid, samples
            minimum = number(block.get("scene_duration") or 0, "DURACION")
        text = block["text"].strip()
        speech_start = samples
        activity = []
        chunks = split_text(text)
        for j, chunk in enumerate(chunks):
            audio, rate = synthesize(chunk, block.get("voice") or default_voice, block.get("instruction", ""))
            if int(rate) != sample_rate:
                raise RuntimeError(f"La voz devolvió {rate} Hz; se esperaban {sample_rate} Hz")
            audio = np.asarray(audio, dtype=np.float32).reshape(-1)
            if not len(audio) or not np.isfinite(audio).all():
                raise RuntimeError("El sintetizador devolvió audio vacío o inválido")
            activity.extend([[samples / sample_rate + start, samples / sample_rate + end]
                             for start, end in voice_intervals(audio, sample_rate)])
            pieces.append(audio)
            samples += len(audio)
            if j + 1 < len(chunks):
                silence(pause_seconds)
        if text:
            speech_timeline.append({"speaker": block["speaker"], "scene": sid, "start": speech_start / sample_rate,
                                    "end": samples / sample_rate, "text": text,
                                    "speech_intervals": activity})
        # PAUSA explícita también se conserva al final de una escena.
        if block.get("pause"):
            seconds = number(block["pause"], "PAUSA")
            if seconds > 10:
                raise ValueError("PAUSA debe estar entre 0 y 10 segundos")
            silence(seconds)
        elif text and index + 1 < len(blocks):
            silence(pause_seconds)
    close_scene()
    if samples <= 0:
        raise ValueError("El guion necesita diálogo o escenas con DURACION positiva")
    return np.concatenate(pieces), {"schema_version": 1, "speech_activity_version": 1, "sample_rate": sample_rate,
        "duration": samples / sample_rate, "scenes": scene_timeline if structured else [], "blocks": speech_timeline}
