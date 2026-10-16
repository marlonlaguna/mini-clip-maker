from pathlib import Path
from kokoro import KPipeline
import soundfile as sf
import numpy as np


IDIOMA_KOKORO = "e"
VOZ_KOKORO = "em_santa"
VELOCIDAD = 0.88
SAMPLE_RATE = 24000


def generar_audio(
    ruta_guion: str | Path,
    ruta_audio: str | Path,
    voz: str = VOZ_KOKORO,
    velocidad: float = VELOCIDAD
) -> Path:

    print("\n========================================")
    print("[AUDIO] INICIANDO GENERACION")
    print("========================================")

    ruta_guion = Path(ruta_guion)
    ruta_audio = Path(ruta_audio)

    print(f"[AUDIO] Guion recibido: {ruta_guion}")
    print(f"[AUDIO] Archivo de salida: {ruta_audio}")
    print(f"[AUDIO] Voz: {voz}")
    print(f"[AUDIO] Velocidad: {velocidad}")

    # -------------------------
    # VALIDACIONES
    # -------------------------

    if not ruta_guion.exists():
        raise FileNotFoundError(
            f"[AUDIO] ERROR: No existe el guion: {ruta_guion}"
        )

    if ruta_guion.stat().st_size == 0:
        raise ValueError(
            "[AUDIO] ERROR: El archivo del guion está vacío."
        )

    if velocidad <= 0:
        raise ValueError(
            "[AUDIO] ERROR: La velocidad debe ser mayor que 0."
        )

    ruta_audio.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # -------------------------
    # LEER GUION
    # -------------------------

    print("[AUDIO] Leyendo guion...")

    try:
        guion = ruta_guion.read_text(
            encoding="utf-8"
        ).strip()

    except Exception as e:
        print("[AUDIO] ERROR leyendo el guion.")
        print(f"[AUDIO] Detalle: {e}")
        raise

    if not guion:
        raise ValueError(
            "[AUDIO] ERROR: El guion no contiene texto."
        )

    print(
        f"[AUDIO] Caracteres encontrados: {len(guion)}"
    )

    # -------------------------
    # INICIALIZAR KOKORO
    # -------------------------

    print("[AUDIO] Inicializando Kokoro...")

    try:
        pipeline = KPipeline(
            lang_code=IDIOMA_KOKORO
        )

    except Exception as e:
        print("[AUDIO] ERROR inicializando Kokoro.")
        print(f"[AUDIO] Detalle: {e}")
        raise

    # -------------------------
    # GENERAR AUDIO
    # -------------------------

    print("[AUDIO] Generando segmentos de voz...")

    audios = []
    segmentos = 0

    try:

        generator = pipeline(
            guion,
            voice=voz,
            speed=velocidad
        )

        for _, _, audio in generator:

            if hasattr(audio, "cpu"):
                audio = audio.cpu().numpy()

            audios.append(audio)

            segmentos += 1

            print(
                f"[AUDIO] Segmento {segmentos} generado."
            )

    except Exception as e:
        print("[AUDIO] ERROR durante la síntesis.")
        print(f"[AUDIO] Detalle: {e}")
        raise

    if not audios:
        raise RuntimeError(
            "[AUDIO] ERROR: Kokoro no generó ningún segmento."
        )

    # -------------------------
    # UNIR SEGMENTOS
    # -------------------------

    print(
        f"[AUDIO] Uniendo {segmentos} segmentos..."
    )

    try:
        audio_final = np.concatenate(audios)

    except Exception as e:
        print("[AUDIO] ERROR uniendo segmentos.")
        print(f"[AUDIO] Detalle: {e}")
        raise

    # -------------------------
    # GUARDAR WAV
    # -------------------------

    print("[AUDIO] Guardando archivo WAV...")

    try:
        sf.write(
            ruta_audio,
            audio_final,
            SAMPLE_RATE
        )

    except Exception as e:
        print("[AUDIO] ERROR guardando el audio.")
        print(f"[AUDIO] Detalle: {e}")
        raise

    # -------------------------
    # RESULTADO
    # -------------------------

    duracion = len(audio_final) / SAMPLE_RATE

    print("")
    print("========================================")
    print("[AUDIO] GENERACION COMPLETADA")
    print("========================================")
    print(f"[AUDIO] Archivo: {ruta_audio}")
    print(
        f"[AUDIO] Duración aproximada: "
        f"{duracion:.2f} segundos"
    )
    print(
        f"[AUDIO] Segmentos generados: "
        f"{segmentos}"
    )
    print("========================================\n")

    return ruta_audio