import json
from pathlib import Path


# =========================
# CONFIGURACION
# =========================

MODELO_WHISPER = "small"
IDIOMA = "es"

FUENTE = "Arial"
TAMANO_FUENTE = 64

MARGIN_V = 180

PLAY_RES_X = 1080
PLAY_RES_Y = 1920


# =========================
# UTILIDADES
# =========================

def formatear_tiempo_ass(segundos: float) -> str:
    """
    Convierte segundos a formato ASS:
    H:MM:SS.cc
    """

    horas = int(segundos // 3600)
    minutos = int((segundos % 3600) // 60)

    segundos_restantes = segundos % 60

    segundos_enteros = int(segundos_restantes)

    centesimas = int(
        (segundos_restantes - segundos_enteros) * 100
    )

    return (
        f"{horas}:"
        f"{minutos:02d}:"
        f"{segundos_enteros:02d}."
        f"{centesimas:02d}"
    )


def limpiar_texto(texto: str) -> str:
    """
    Limpia caracteres problemáticos para ASS.
    """

    texto = texto.strip()

    texto = texto.replace("{", "")
    texto = texto.replace("}", "")
    texto = texto.replace("\n", " ")

    return texto


# =========================
# GENERAR SUBTITULOS
# =========================

def generar_subtitulos(
    ruta_audio: str | Path,
    ruta_subtitulos: str | Path,
    modelo: str = MODELO_WHISPER
) -> Path:

    print("")
    print("========================================")
    print("[SUBTITULOS] INICIANDO GENERACION")
    print("========================================")

    ruta_audio = Path(ruta_audio)
    ruta_subtitulos = Path(ruta_subtitulos)

    print(
        f"[SUBTITULOS] Audio: "
        f"{ruta_audio}"
    )

    print(
        f"[SUBTITULOS] Salida: "
        f"{ruta_subtitulos}"
    )

    print(
        f"[SUBTITULOS] Modelo Whisper: "
        f"{modelo}"
    )

    # =========================
    # VALIDACIONES
    # =========================

    if not ruta_audio.exists():
        raise FileNotFoundError(
            f"[SUBTITULOS] ERROR: "
            f"No existe el audio: {ruta_audio}"
        )

    if ruta_audio.stat().st_size == 0:
        raise ValueError(
            "[SUBTITULOS] ERROR: "
            "El archivo de audio está vacío."
        )

    ruta_subtitulos.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    timeline_path = ruta_audio.with_suffix(".timeline.json")
    timeline = json.loads(timeline_path.read_text(encoding="utf-8")) if timeline_path.is_file() else None
    intentional_silence = timeline is not None and not timeline.get("blocks")
    segmentos = []
    if intentional_silence:
        print("[SUBTITULOS] Guion sin diálogo: ASS vacío; se conservan las escenas y sus silencios.")
    else:
        # =========================
        # CARGAR WHISPER
        # =========================

        print("")
        print(
            "[SUBTITULOS] Cargando Whisper en CPU..."
        )

        try:

            from faster_whisper import WhisperModel

            whisper = WhisperModel(
                modelo,
                device="cpu",
                compute_type="int8"
            )

        except Exception as e:

            print("")
            print(
                "[SUBTITULOS] ERROR cargando Whisper."
            )

            print(
                f"[SUBTITULOS] Detalle: {e}"
            )

            raise

        print(
            "[SUBTITULOS] Modelo cargado correctamente."
        )

        # =========================
        # TRANSCRIBIR
        # =========================

        print("")
        print(
            "[SUBTITULOS] Analizando audio..."
        )

        try:

            segmentos, info = whisper.transcribe(
                str(ruta_audio),
                language=IDIOMA,
                beam_size=5,
                vad_filter=True
            )

            segmentos = list(segmentos)

        except Exception as e:

            print("")
            print(
                "[SUBTITULOS] ERROR transcribiendo audio."
            )

            print(
                f"[SUBTITULOS] Detalle: {e}"
            )

            raise

        if not segmentos:
            raise RuntimeError(
                "[SUBTITULOS] Whisper no detectó texto."
            )

        print(
            f"[SUBTITULOS] Segmentos detectados: "
            f"{len(segmentos)}"
        )


    # =========================
    # CABECERA ASS
    # =========================

    cabecera = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {PLAY_RES_X}
PlayResY: {PLAY_RES_Y}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TikTok,{FUENTE},{TAMANO_FUENTE},&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,5,1,2,70,70,{MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # =========================
    # CREAR EVENTOS
    # =========================

    eventos = []
    segmentos_timeline = []

    print("")
    print(
        "[SUBTITULOS] Generando líneas..."
    )

    for indice, segmento in enumerate(
        segmentos,
        start=1
    ):

        inicio = formatear_tiempo_ass(
            segmento.start
        )

        fin = formatear_tiempo_ass(
            segmento.end
        )

        texto = limpiar_texto(
            segmento.text
        )

        if not texto:
            continue

        segmentos_timeline.append(
            {
                "start": float(segmento.start),
                "end": float(segmento.end),
                "text": texto,
            }
        )

        print(
            f"[SUBTITULOS] "
            f"{indice:03d} | "
            f"{segmento.start:.2f}s -> "
            f"{segmento.end:.2f}s | "
            f"{texto}"
        )

        linea = (
            f"Dialogue: 0,"
            f"{inicio},"
            f"{fin},"
            f"TikTok,,0,0,0,,"
            f"{texto}"
        )

        eventos.append(
            linea
        )

    if not eventos and not intentional_silence:
        raise RuntimeError(
            "[SUBTITULOS] ERROR: "
            "No se generaron eventos de subtítulos."
        )

    # =========================
    # GUARDAR ASS
    # =========================

    print("")
    print(
        "[SUBTITULOS] Guardando archivo ASS..."
    )

    try:

        contenido = (
            cabecera
            + "\n"
            + "\n".join(eventos)
            + "\n"
        )

        ruta_subtitulos.write_text(
            contenido,
            encoding="utf-8"
        )

    except Exception as e:

        print("")
        print(
            "[SUBTITULOS] ERROR guardando archivo."
        )

        print(
            f"[SUBTITULOS] Detalle: {e}"
        )

        raise

    # =========================
    # GUARDAR TIMELINE WHISPER
    # =========================

    ruta_segmentos = (
        ruta_subtitulos.parent
        / "segmentos.json"
    )

    try:

        ruta_segmentos.write_text(
            json.dumps(
                segmentos_timeline,
                indent=2,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )

    except Exception as e:

        print("")
        print(
            "[SUBTITULOS] ERROR guardando "
            "segmentos.json."
        )
        print(
            f"[SUBTITULOS] Detalle: {e}"
        )
        raise

    print(
        f"[SUBTITULOS] Timeline Whisper: "
        f"{ruta_segmentos}"
    )

    # =========================
    # RESULTADO
    # =========================

    print("")
    print("========================================")
    print("[SUBTITULOS] GENERACION COMPLETADA")
    print("========================================")

    print(
        f"[SUBTITULOS] Archivo: "
        f"{ruta_subtitulos}"
    )

    print(
        f"[SUBTITULOS] Líneas generadas: "
        f"{len(eventos)}"
    )

    print("========================================")
    print("")

    return ruta_subtitulos