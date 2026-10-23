import json
import math
import random
import shutil
import subprocess
import tempfile
from pathlib import Path
from masterizacion_audio import masterizar_video

BASE_DIR = Path(__file__).resolve().parent
MUSICA_DIR = BASE_DIR / "musica"
IMAGENES_FINALES_DIR = BASE_DIR / "imagenes_finales"
SOUND_EFFECTS_DIR = BASE_DIR / "sound_efects"

SOUND_EFFECT_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".ogg",
    ".m4a",
    ".aac",
    ".flac",
}

FPS = 30


def _ejecutar(comando):
    resultado = subprocess.run(
        [str(x) for x in comando],
        capture_output=True,
        text=True
    )

    if resultado.returncode != 0:
        raise RuntimeError(
            "[VIDEO] FFmpeg falló:\n"
            + resultado.stderr
        )

    return resultado


def _duracion_audio(ruta_audio: Path) -> float:
    resultado = _ejecutar([
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        ruta_audio
    ])

    data = json.loads(resultado.stdout)
    return float(data["format"]["duration"])


def _leer_config(ruta_config):
    if not ruta_config:
        return {}

    ruta_config = Path(ruta_config)

    if not ruta_config.exists():
        return {}

    return json.loads(
        ruta_config.read_text(encoding="utf-8")
    )


def _parse_resolucion(valor):
    try:
        ancho, alto = str(valor).lower().split("x", 1)
        return int(ancho), int(alto)
    except Exception:
        return 1080, 1920


def _imagenes(carpeta_imagenes):
    carpeta = Path(carpeta_imagenes)

    extensiones = {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp"
    }

    return sorted(
        p
        for p in carpeta.iterdir()
        if p.is_file()
        and p.suffix.lower() in extensiones
    )


def _escape_ass_path(path: Path) -> str:
    """
    Escape de ruta para el filtro ass de FFmpeg en Windows.
    """
    texto = str(path.resolve())
    texto = texto.replace("\\", "/")
    texto = texto.replace(":", r"\:")
    texto = texto.replace("'", r"\'")
    return texto


def _filtro_imagen(
    efecto,
    ancho,
    alto,
    frames,
    fps
):
    # Primero hacemos una imagen algo más grande para permitir
    # movimiento sin dejar bordes.
    sw = math.ceil(ancho * 1.16)
    sh = math.ceil(alto * 1.16)

    base = (
        f"scale={sw}:{sh}:"
        "force_original_aspect_ratio=increase,"
    )

    if efecto == "zoom_in":
        return (
            base
            + f"zoompan="
              f"z='min(zoom+0.0018,1.16)':"
              f"x='iw/2-(iw/zoom/2)':"
              f"y='ih/2-(ih/zoom/2)':"
              f"d={frames}:"
              f"s={ancho}x{alto}:"
              f"fps={fps},"
              "format=yuv420p"
        )

    if efecto == "zoom_out":
        return (
            base
            + f"zoompan="
              f"z='if(eq(on,1),1.16,max(zoom-0.0018,1.0))':"
              f"x='iw/2-(iw/zoom/2)':"
              f"y='ih/2-(ih/zoom/2)':"
              f"d={frames}:"
              f"s={ancho}x{alto}:"
              f"fps={fps},"
              "format=yuv420p"
        )

    if efecto == "pan_left":
        return (
            base
            + f"crop={ancho}:{alto}:"
              f"x='(iw-ow)*(1-n/{max(1, frames-1)})':"
              f"y='(ih-oh)/2',"
              f"fps={fps},format=yuv420p"
        )

    if efecto == "pan_right":
        return (
            base
            + f"crop={ancho}:{alto}:"
              f"x='(iw-ow)*(n/{max(1, frames-1)})':"
              f"y='(ih-oh)/2',"
              f"fps={fps},format=yuv420p"
        )

    if efecto == "pan_up":
        return (
            base
            + f"crop={ancho}:{alto}:"
              f"x='(iw-ow)/2':"
              f"y='(ih-oh)*(1-n/{max(1, frames-1)})',"
              f"fps={fps},format=yuv420p"
        )

    if efecto == "pan_down":
        return (
            base
            + f"crop={ancho}:{alto}:"
              f"x='(iw-ow)/2':"
              f"y='(ih-oh)*(n/{max(1, frames-1)})',"
              f"fps={fps},format=yuv420p"
        )

    return (
        base
        + f"crop={ancho}:{alto}:"
          "x='(iw-ow)/2':"
          "y='(ih-oh)/2',"
          f"fps={fps},format=yuv420p"
    )


def _crear_clips_desde_imagenes(
    imagenes,
    duracion_audio,
    ancho,
    alto,
    carpeta_temp
):
    total_frames = math.ceil(
        duracion_audio * FPS
    )

    cantidad = len(imagenes)

    if cantidad == 0:
        raise RuntimeError(
            "[VIDEO] No hay imágenes para generar el video."
        )

    base = total_frames // cantidad
    resto = total_frames % cantidad

    efectos = [
        "zoom_in",
        "zoom_out",
        "pan_left",
        "pan_right",
        "pan_up",
        "pan_down",
    ]

    clips = []

    for indice, imagen in enumerate(imagenes):
        frames = base + (
            1 if indice < resto else 0
        )

        frames = max(1, frames)

        efecto = random.choice(efectos)

        salida = (
            carpeta_temp
            / f"image_clip_{indice+1:03d}.mp4"
        )

        filtro = _filtro_imagen(
            efecto=efecto,
            ancho=ancho,
            alto=alto,
            frames=frames,
            fps=FPS
        )

        print(
            f"[VIDEO] Imagen {indice+1}/{cantidad} "
            f"efecto={efecto} frames={frames}"
        )

        _ejecutar([
            "ffmpeg",
            "-y",
            "-loop", "1",
            "-i", imagen,
            "-vf", filtro,
            "-frames:v", str(frames),
            "-an",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            salida,
        ])

        clips.append(salida)

    return clips


def _normalizar_clips_stick(
    clips_stick,
    ancho,
    alto,
    carpeta_temp
):
    normalizados = []

    for indice, clip in enumerate(clips_stick):
        clip = Path(clip)

        if not clip.exists():
            raise FileNotFoundError(
                f"[VIDEO] No existe clip stick: {clip}"
            )

        salida = (
            carpeta_temp
            / f"stick_clip_{indice+1:03d}.mp4"
        )

        print(
            f"[VIDEO] Preparando escena stick "
            f"{indice+1}/{len(clips_stick)}"
        )

        _ejecutar([
            "ffmpeg",
            "-y",
            "-i", clip,
            "-vf",
            (
                f"scale={ancho}:{alto}:"
                "force_original_aspect_ratio=increase,"
                f"crop={ancho}:{alto},"
                f"fps={FPS},"
                "format=yuv420p"
            ),
            "-an",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            salida,
        ])

        normalizados.append(salida)

    return normalizados


def _concatenar_clips(
    clips,
    ruta_salida,
    carpeta_temp
):
    if not clips:
        raise RuntimeError(
            "[VIDEO] No hay clips visuales para concatenar."
        )

    lista = carpeta_temp / "concat.txt"

    lineas = []

    for clip in clips:
        # concat demuxer acepta slash normal y comillas simples.
        ruta = str(
            Path(clip).resolve()
        ).replace("\\", "/")

        ruta = ruta.replace(
            "'",
            r"'\''"
        )

        lineas.append(
            f"file '{ruta}'"
        )

    lista.write_text(
        "\n".join(lineas),
        encoding="utf-8"
    )

    _ejecutar([
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", lista,
        "-c", "copy",
        ruta_salida,
    ])


def _resolver_musica(config):
    nombre = str(
        config.get("musica", "")
    ).strip()

    if not nombre:
        return None

    candidata = Path(nombre)

    if candidata.is_absolute():
        return (
            candidata
            if candidata.exists()
            else None
        )

    candidata = MUSICA_DIR / nombre

    if candidata.exists():
        return candidata

    return None


def _resolver_imagen_final(config):
    nombre = str(
        config.get(
            "imagen_final",
            ""
        )
    ).strip()

    if not nombre:
        return None

    candidata = Path(nombre)

    if candidata.is_absolute():
        return (
            candidata
            if candidata.exists()
            else None
        )

    candidata = (
        IMAGENES_FINALES_DIR
        / nombre
    )

    if candidata.exists():
        return candidata

    # Compatibilidad extra: también permite una ruta
    # relativa al directorio raíz de Mini Clip Maker.
    candidata = BASE_DIR / nombre

    if candidata.exists():
        return candidata

    return None


def _aplicar_imagen_final(
    ruta_visual,
    ruta_salida,
    config,
    duracion,
    ancho,
    alto
):
    """
    Superpone la imagen final durante los últimos N segundos
    del video SIN alterar la duración ni la sincronización.

    Si [IMAGEN_FINAL] no está definido, copia el visual tal cual.
    """
    imagen_final = _resolver_imagen_final(
        config
    )

    nombre_configurado = str(
        config.get(
            "imagen_final",
            ""
        )
    ).strip()

    if not nombre_configurado:
        shutil.copy2(
            ruta_visual,
            ruta_salida
        )
        return ruta_salida

    if imagen_final is None:
        raise FileNotFoundError(
            "[VIDEO] No encontré la imagen final "
            f"'{nombre_configurado}'. "
            "Busqué una ruta absoluta, "
            f"'{IMAGENES_FINALES_DIR / nombre_configurado}' "
            "y una ruta relativa al proyecto."
        )

    try:
        duracion_final = float(
            config.get(
                "duracion_imagen_final",
                4.0
            )
        )
    except (TypeError, ValueError):
        raise ValueError(
            "[VIDEO] duracion_imagen_final debe ser numérica."
        )

    if duracion_final <= 0:
        shutil.copy2(
            ruta_visual,
            ruta_salida
        )
        return ruta_salida

    duracion_final = min(
        duracion_final,
        duracion
    )

    inicio = max(
        0.0,
        duracion - duracion_final
    )

    print(
        f"[VIDEO] Imagen final: {imagen_final.name}"
    )

    print(
        f"[VIDEO] Imagen final desde "
        f"{inicio:.2f}s hasta {duracion:.2f}s "
        f"({duracion_final:.2f}s)"
    )

    filtro = (
        f"[1:v]"
        f"scale={ancho}:{alto}:"
        "force_original_aspect_ratio=increase,"
        f"crop={ancho}:{alto},"
        "setsar=1,"
        "format=rgba"
        "[endcard];"
        f"[0:v][endcard]"
        f"overlay=0:0:"
        f"enable='gte(t,{inicio:.6f})':"
        "eof_action=repeat:"
        "shortest=1,"
        f"fps={FPS},"
        "format=yuv420p"
        "[vout]"
    )

    _ejecutar([
        "ffmpeg",
        "-y",
        "-i", ruta_visual,
        "-loop", "1",
        "-i", imagen_final,
        "-filter_complex", filtro,
        "-map", "[vout]",
        "-an",
        "-t", f"{duracion:.3f}",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        ruta_salida,
    ])

    return ruta_salida


def _catalogo_efectos_sonido():
    """Devuelve {nombre_sin_extension: Path}."""

    SOUND_EFFECTS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    catalogo = {}

    for ruta in sorted(SOUND_EFFECTS_DIR.iterdir()):
        if (
            ruta.is_file()
            and ruta.suffix.lower() in SOUND_EFFECT_EXTENSIONS
        ):
            nombre = ruta.stem.strip()
            if nombre:
                catalogo[nombre] = ruta

    return catalogo


def _leer_efectos_storyboard(
    ruta_video,
    config,
):
    """
    Lee sound_effects desde stick_storyboard.json.

    Cada efecto usa tiempo relativo a la escena. Aquí se convierte
    a tiempo absoluto del video para FFmpeg.
    """

    if not config.get(
        "usar_efectos_sonido",
        True
    ):
        return []

    try:
        max_efectos = max(
            0,
            int(config.get("max_efectos_sonido", 8))
        )
    except (TypeError, ValueError):
        max_efectos = 8

    if max_efectos == 0:
        return []

    ruta_storyboard = (
        Path(ruta_video).parent
        / "stick_storyboard.json"
    )

    if not ruta_storyboard.exists():
        return []

    try:
        data = json.loads(
            ruta_storyboard.read_text(
                encoding="utf-8"
            )
        )
    except Exception as exc:
        print(
            f"[SFX] No pude leer stick_storyboard.json: {exc}"
        )
        return []

    catalogo = _catalogo_efectos_sonido()

    if not catalogo:
        return []

    efectos = []

    for escena in data.get("storyboard", []):
        try:
            inicio_escena = float(
                escena.get("start", 0.0)
            )
        except (TypeError, ValueError):
            inicio_escena = 0.0

        for efecto in escena.get("sound_effects", []):
            if len(efectos) >= max_efectos:
                break

            if not isinstance(efecto, dict):
                continue

            nombre = str(
                efecto.get("name", "")
            ).strip()

            ruta = catalogo.get(nombre)

            if ruta is None:
                print(
                    f"[SFX] Efecto no encontrado: {nombre}"
                )
                continue

            try:
                relativo = max(
                    0.0,
                    float(efecto.get("time", 0.0))
                )
            except (TypeError, ValueError):
                relativo = 0.0

            try:
                volumen = float(
                    efecto.get("volume", 1.0)
                )
            except (TypeError, ValueError):
                volumen = 1.0

            volumen = max(
                0.0,
                min(1.5, volumen)
            )

            efectos.append({
                "name": nombre,
                "path": ruta,
                "time": inicio_escena + relativo,
                "volume": volumen,
            })

        if len(efectos) >= max_efectos:
            break

    return efectos


def _render_final(
    ruta_visual,
    ruta_audio,
    ruta_subtitulos,
    ruta_video,
    duracion,
    config
):
    musica = _resolver_musica(config)

    volumen_musica = float(
        config.get(
            "volumen_musica",
            0.10
        )
    )

    volumen_efectos = float(
        config.get(
            "volumen_efectos",
            0.35
        )
    )

    efectos = _leer_efectos_storyboard(
        ruta_video=ruta_video,
        config=config,
    )

    comando = [
        "ffmpeg",
        "-y",
        "-i", ruta_visual,
        "-i", ruta_audio,
    ]

    indice_siguiente = 2
    indice_musica = None

    if musica:
        indice_musica = indice_siguiente
        indice_siguiente += 1

        comando += [
            "-stream_loop", "-1",
            "-i", musica,
        ]

    indices_efectos = []

    for efecto in efectos:
        indice = indice_siguiente
        indice_siguiente += 1

        comando += [
            "-i",
            efecto["path"],
        ]

        indices_efectos.append(
            (indice, efecto)
        )

    filtros = []
    video_label = "[0:v]"

    ruta_subtitulos = Path(
        ruta_subtitulos
    )

    if ruta_subtitulos.exists():
        ass_path = _escape_ass_path(
            ruta_subtitulos
        )

        filtros.append(
            f"{video_label}"
            f"ass='{ass_path}'"
            "[vout]"
        )

        salida_video = "[vout]"

    else:
        salida_video = "0:v"

    pistas_audio = ["[1:a]"]

    if musica:
        fade_inicio = max(
            0.0,
            duracion - 2.0
        )

        filtros.append(
            f"[{indice_musica}:a]"
            f"volume={volumen_musica},"
            f"afade=t=out:"
            f"st={fade_inicio:.3f}:"
            "d=2"
            "[music]"
        )

        pistas_audio.append(
            "[music]"
        )

    for numero, (
        indice,
        efecto
    ) in enumerate(
        indices_efectos,
        start=1
    ):
        tiempo = max(
            0.0,
            float(efecto["time"])
        )

        delay_ms = max(
            0,
            round(tiempo * 1000.0)
        )

        volumen_individual = (
            volumen_efectos
            * float(efecto["volume"])
        )

        label = f"sfx{numero}"

        filtros.append(
            f"[{indice}:a]"
            f"volume={volumen_individual:.4f},"
            f"adelay={delay_ms}:all=1"
            f"[{label}]"
        )

        pistas_audio.append(
            f"[{label}]"
        )

        print(
            f"[SFX] {efecto['name']} "
            f"@ {tiempo:.2f}s "
            f"vol={volumen_individual:.2f}"
        )

    if len(pistas_audio) > 1:
        filtros.append(
            "".join(pistas_audio)
            + f"amix=inputs={len(pistas_audio)}:"
              "duration=first:"
              "dropout_transition=2:"
              "normalize=0,"
              "alimiter=limit=0.95"
              "[aout]"
        )

        salida_audio = "[aout]"

    else:
        salida_audio = "1:a"

    if filtros:
        comando += [
            "-filter_complex",
            ";".join(filtros)
        ]

    comando += [
        "-map", salida_video,
        "-map", salida_audio,
        "-t", f"{duracion:.3f}",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        ruta_video,
    ]

    _ejecutar(comando)


def generar_video(
    ruta_audio,
    carpeta_imagenes,
    ruta_subtitulos,
    ruta_video,
    ruta_config=None,
    modo_video="image",
    clips_stick=None
):
    """
    Genera el video final.

    Compatibilidad:
    - modo image: usa carpeta_imagenes como antes.
    - modo stick: usa clips_stick pre-renderizados.
    - modo mixed: usa clips pre-renderizados mixtos (stick + ilustración).

    Narración, música y subtítulos siguen siendo responsabilidad
    de Mini Clip Maker.
    """
    ruta_audio = Path(ruta_audio)
    carpeta_imagenes = Path(
        carpeta_imagenes
    )
    ruta_subtitulos = Path(
        ruta_subtitulos
    )
    ruta_video = Path(
        ruta_video
    )

    config = _leer_config(
        ruta_config
    )

    # config manda si existe.
    modo_video = str(
        config.get(
            "modo_video",
            modo_video
        )
    ).lower()

    ancho, alto = _parse_resolucion(
        config.get(
            "resolucion",
            "1080x1920"
        )
    )

    duracion = _duracion_audio(
        ruta_audio
    )

    print(
        f"[VIDEO] Modo: "
        f"{modo_video.upper()}"
    )

    print(
        f"[VIDEO] Resolución: "
        f"{ancho}x{alto}"
    )

    print(
        f"[VIDEO] Duración objetivo: "
        f"{duracion:.2f}s"
    )

    ruta_video.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with tempfile.TemporaryDirectory(
        prefix="miniclip_video_"
    ) as temp_dir:
        temp = Path(temp_dir)

        if modo_video in {"stick", "mixed"}:
            if not clips_stick:
                carpeta_stick = (
                    ruta_video.parent
                    / "stick"
                )

                if carpeta_stick.exists():
                    clips_stick = sorted(
                        carpeta_stick.glob(
                            "scene_*.mp4"
                        )
                    )

            if not clips_stick:
                raise RuntimeError(
                    f"[VIDEO] Modo {modo_video.upper()} seleccionado "
                    "pero no hay escenas visuales pre-renderizadas."
                )

            clips_visuales = (
                _normalizar_clips_stick(
                    clips_stick=list(
                        clips_stick
                    ),
                    ancho=ancho,
                    alto=alto,
                    carpeta_temp=temp
                )
            )

        elif modo_video == "image":
            imagenes = _imagenes(
                carpeta_imagenes
            )

            clips_visuales = (
                _crear_clips_desde_imagenes(
                    imagenes=imagenes,
                    duracion_audio=duracion,
                    ancho=ancho,
                    alto=alto,
                    carpeta_temp=temp
                )
            )

        else:
            raise ValueError(
                f"[VIDEO] modo_video inválido: "
                f"{modo_video}"
            )

        ruta_visual = (
            temp
            / "visual_concat.mp4"
        )

        print(
            "[VIDEO] Concatenando "
            "escenas visuales..."
        )

        _concatenar_clips(
            clips=clips_visuales,
            ruta_salida=ruta_visual,
            carpeta_temp=temp
        )

        ruta_visual_final = (
            temp
            / "visual_con_imagen_final.mp4"
        )

        _aplicar_imagen_final(
            ruta_visual=ruta_visual,
            ruta_salida=ruta_visual_final,
            config=config,
            duracion=duracion,
            ancho=ancho,
            alto=alto
        )

        print(
            "[VIDEO] Agregando narración, "
            "música y subtítulos..."
        )

        _render_final(
            ruta_visual=ruta_visual_final,
            ruta_audio=ruta_audio,
            ruta_subtitulos=ruta_subtitulos,
            ruta_video=ruta_video,
            duracion=duracion,
            config=config
        )

    print(
        f"[VIDEO] Video generado: "
        f"{ruta_video}"
    )
    masterizar_video(ruta_video)
    return ruta_video
