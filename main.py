import sys
import re
import json
import unicodedata
import subprocess
import inspect
import tempfile
from contextvars import ContextVar
from pathlib import Path

from generar_guion import generar_guion
from generar_audio import generar_audio
from generar_subtitulos import generar_subtitulos
from generar_imagenes import generar_imagenes
from generar_video import generar_video

from stick_engine import generar_stick_scenes
from guion_audio import formatear_guion_audio, limpiar_guion_audio
from clip_logger import ClipRunLogger
from guion_escenas import parse_cast, preparar_guion_visual
from stick_engine.assets import AssetLibrary
from instalar_actualizacion import retirar_archivos_obsoletos


BASE_DIR = Path(__file__).resolve().parent
retirar_archivos_obsoletos(BASE_DIR)
_ACTIVE_CLIP_LOGGER = ContextVar("active_clip_logger", default=None)

CLIPS_DIR = BASE_DIR / "clips"
MUSICA_DIR = BASE_DIR / "musica"
GUIONES_DIR = BASE_DIR / "guiones"
SOUND_EFFECTS_DIR = BASE_DIR / "sound_efects"

SOUND_EFFECT_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".ogg",
    ".m4a",
    ".aac",
    ".flac",
}

MODO_VIDEO_DEFAULT = "image"


def slugify(texto: str) -> str:
    texto = unicodedata.normalize(
        "NFKD",
        texto
    )

    texto = "".join(
        c
        for c in texto
        if not unicodedata.combining(c)
    )

    texto = texto.lower().strip()

    texto = re.sub(
        r"[^a-z0-9]+",
        "-",
        texto
    )

    return texto.strip("-") or "clip"


def listar_efectos_sonido():
    """
    Lee dinámicamente la carpeta sound_efects del proyecto.

    El nombre que recibe la IA es el nombre del archivo sin extensión.
    Ejemplo:
        pasos.mp3 -> pasos
        puerta-golpe.wav -> puerta-golpe
    """

    SOUND_EFFECTS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    efectos = {}

    for ruta in sorted(SOUND_EFFECTS_DIR.iterdir()):
        if (
            ruta.is_file()
            and ruta.suffix.lower() in SOUND_EFFECT_EXTENSIONS
        ):
            nombre = ruta.stem.strip()

            if nombre:
                efectos[nombre] = ruta

    return efectos


def obtener_duracion_audio(
    ruta_audio: Path
) -> float:

    comando = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(ruta_audio),
    ]

    resultado = subprocess.run(
        comando,
        capture_output=True,
        text=True,
        check=True
    )

    data = json.loads(
        resultado.stdout
    )

    return float(
        data["format"]["duration"]
    )


def _valor_simple(
    secciones,
    nombre,
    default=""
):
    valor = secciones.get(
        nombre.upper()
    )

    if valor is None:
        return default

    return valor.strip()


def parsear_guion_configurado(
    texto: str
) -> dict:

    # Acepta tanto [GUION] en su propia línea como [GUION] seguido de
    # contenido en la misma línea.
    texto = re.sub(
        r"(?mi)^\[GUION\][ \t]+",
        "[GUION]\n",
        texto,
        count=1,
    )

    # Las cabeceras de voz tienen un separador "|" y pertenecen al cuerpo
    # de [GUION], no son secciones de configuración como [TITULO].
    patron = re.compile(
        r"(?ms)^\[([^\]]+)\][ \t]*\n"
        r"(.*?)"
        r"(?=^\[(?![^\]\n]*\|)[^\]]+\][ \t]*$|\Z)"
    )

    guion_match = re.search(r"(?mi)^\[GUION\][ \t]*(?:\r?\n|$)", texto)
    if guion_match is None:
        raise ValueError("El archivo no contiene la sección [GUION].")
    # Solo la cabecera global se interpreta como configuración. ESCENA y
    # [peter] dentro de GUION pertenecen al guion, incluso sin separador '|'.
    cabecera = texto[:guion_match.start()]
    secciones = {"GUION": texto[guion_match.end():].strip()}
    personajes = {}

    for match in patron.finditer(cabecera):

        clave_original = (
            match.group(1).strip()
        )

        contenido = (
            match.group(2).strip()
        )

        if clave_original.upper().startswith(
            "PERSONAJE:"
        ):

            nombre = clave_original.split(
                ":",
                1
            )[1].strip()

            personajes[nombre] = contenido

        else:

            secciones[
                clave_original.upper()
            ] = contenido

    if "GUION" not in secciones:
        raise ValueError(
            "El archivo no contiene "
            "la sección [GUION]."
        )

    titulo = _valor_simple(
        secciones,
        "TITULO",
        "Mini Clip"
    )

    resolucion = _valor_simple(
        secciones,
        "RESOLUCION",
        "1080x1920"
    )

    musica = _valor_simple(
        secciones,
        "MUSICA",
        ""
    )

    volumen_musica = _valor_simple(
        secciones,
        "VOLUMEN_MUSICA",
        "0.10"
    )

    estilo_visual = _valor_simple(
        secciones,
        "ESTILO_VISUAL",
        ""
    )

    paleta = _valor_simple(
        secciones,
        "PALETA",
        ""
    )

    negative_prompt = _valor_simple(
        secciones,
        "NEGATIVE_PROMPT",
        ""
    )

    modo_video = _valor_simple(
        secciones,
        "MODO_VIDEO",
        MODO_VIDEO_DEFAULT
    ).lower()

    voz_qwen = _valor_simple(
        secciones,
        "VOZ_QWEN",
        "Ryan"
    ) or "Ryan"

    if modo_video not in {
        "image",
        "stick",
        "mixed"
    }:
        raise ValueError(
            f"[MODO_VIDEO] inválido: "
            f"{modo_video}. "
            "Usa 'image', 'stick' o 'mixed'."
        )

    porcentaje_minimo_stick_texto = _valor_simple(
        secciones,
        "PORCENTAJE_MINIMO_STICK",
        "70"
    )

    try:
        porcentaje_minimo_stick = float(
            porcentaje_minimo_stick_texto
        )
    except ValueError:
        raise ValueError(
            "[PORCENTAJE_MINIMO_STICK] debe ser numérico."
        )

    if not 0 <= porcentaje_minimo_stick <= 100:
        raise ValueError(
            "[PORCENTAJE_MINIMO_STICK] debe estar entre 0 y 100."
        )

    permitir_fondos_texto = _valor_simple(
        secciones,
        "PERMITIR_FONDOS_AUTOMATICOS",
        "si"
    ).lower()

    permitir_fondos_automaticos = permitir_fondos_texto in {
        "si", "sí", "s", "yes", "y", "true", "1"
    }

    usar_efectos_texto = _valor_simple(
        secciones,
        "USAR_EFECTOS_SONIDO",
        "si"
    ).lower()

    usar_efectos_sonido = usar_efectos_texto in {
        "si", "sí", "s", "yes", "y", "true", "1"
    }

    volumen_efectos_texto = _valor_simple(
        secciones,
        "VOLUMEN_EFECTOS",
        "0.35"
    )

    try:
        volumen_efectos = float(
            volumen_efectos_texto
        )
    except ValueError:
        raise ValueError(
            "[VOLUMEN_EFECTOS] debe ser numérico."
        )

    if volumen_efectos < 0:
        raise ValueError(
            "[VOLUMEN_EFECTOS] no puede ser negativo."
        )

    max_efectos_texto = _valor_simple(
        secciones,
        "MAX_EFECTOS_SONIDO",
        "8"
    )

    try:
        max_efectos_sonido = int(
            max_efectos_texto
        )
    except ValueError:
        raise ValueError(
            "[MAX_EFECTOS_SONIDO] debe ser un entero."
        )

    if max_efectos_sonido < 0:
        raise ValueError(
            "[MAX_EFECTOS_SONIDO] no puede ser negativo."
        )

    imagen_final = _valor_simple(
        secciones,
        "IMAGEN_FINAL",
        ""
    )

    duracion_imagen_final_texto = _valor_simple(
        secciones,
        "DURACION_IMAGEN_FINAL",
        "4"
    )

    try:
        duracion_imagen_final = float(
            duracion_imagen_final_texto
        )
    except ValueError:
        raise ValueError(
            "[DURACION_IMAGEN_FINAL] debe ser numérico."
        )

    if duracion_imagen_final < 0:
        raise ValueError(
            "[DURACION_IMAGEN_FINAL] no puede ser negativa."
        )

    seed_texto = _valor_simple(
        secciones,
        "SEED",
        ""
    )

    seed = None

    if seed_texto:

        try:
            seed = int(
                seed_texto
            )

        except ValueError:
            raise ValueError(
                "[SEED] debe ser "
                "un número entero."
            )

    try:

        volumen_musica = float(
            volumen_musica
        )

    except ValueError:

        raise ValueError(
            "[VOLUMEN_MUSICA] "
            "debe ser numérico."
        )

    return {
        "titulo": titulo,
        "resolucion": resolucion,
        "musica": musica,
        "volumen_musica": volumen_musica,
        "estilo_visual": estilo_visual,
        "paleta": paleta,
        "seed": seed,
        "negative_prompt": negative_prompt,
        "personajes": personajes,
        "cast": _valor_simple(secciones, "CAST", ""),
        "modo_video": modo_video,
        "voz_qwen": voz_qwen,
        "porcentaje_minimo_stick": porcentaje_minimo_stick,
        "permitir_fondos_automaticos": permitir_fondos_automaticos,
        "usar_efectos_sonido": usar_efectos_sonido,
        "volumen_efectos": volumen_efectos,
        "max_efectos_sonido": max_efectos_sonido,
        "imagen_final": imagen_final,
        "duracion_imagen_final": duracion_imagen_final,
        "guion": secciones[
            "GUION"
        ].strip(),
    }


def guardar_config(
    config: dict,
    ruta_config: Path
):

    data = {

        "titulo": config.get(
            "titulo"
        ),

        "resolucion": config.get(
            "resolucion",
            "1080x1920"
        ),

        "musica": config.get(
            "musica",
            ""
        ),

        "volumen_musica": config.get(
            "volumen_musica",
            0.10
        ),

        "estilo_visual": config.get(
            "estilo_visual",
            ""
        ),

        "paleta": config.get(
            "paleta",
            ""
        ),

        "seed": config.get(
            "seed"
        ),

        "negative_prompt": config.get(
            "negative_prompt",
            ""
        ),

        "cast": config.get("cast", {}),

        "personajes": config.get(
            "personajes",
            {}
        ),

        "modo_video": config.get(
            "modo_video",
            MODO_VIDEO_DEFAULT
        ),

        "voz_qwen": config.get(
            "voz_qwen",
            "Ryan"
        ),

        "porcentaje_minimo_stick": config.get(
            "porcentaje_minimo_stick",
            70.0
        ),

        "permitir_fondos_automaticos": config.get(
            "permitir_fondos_automaticos",
            True
        ),

        "usar_efectos_sonido": config.get(
            "usar_efectos_sonido",
            True
        ),

        "volumen_efectos": config.get(
            "volumen_efectos",
            0.35
        ),

        "max_efectos_sonido": config.get(
            "max_efectos_sonido",
            8
        ),

        "imagen_final": config.get(
            "imagen_final",
            ""
        ),

        "duracion_imagen_final": config.get(
            "duracion_imagen_final",
            4.0
        ),
    }

    ruta_config.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


def _llamar_generar_audio(
    ruta_guion: Path,
    ruta_audio: Path,
    voz_qwen: str = "Ryan",
):
    return generar_audio(
        ruta_guion=ruta_guion,
        ruta_audio=ruta_audio,
        voz=voz_qwen,
    )



def _llamar_generar_subtitulos(
    ruta_audio: Path,
    ruta_subtitulos: Path
):

    try:

        firma = inspect.signature(
            generar_subtitulos
        )

        params = firma.parameters

        if (
            "ruta_audio" in params
            and
            "ruta_subtitulos" in params
        ):

            return generar_subtitulos(
                ruta_audio=ruta_audio,
                ruta_subtitulos=ruta_subtitulos
            )

    except Exception:
        pass

    return generar_subtitulos(
        ruta_audio,
        ruta_subtitulos
    )


def _generar_guion_prompt(
    titulo: str,
    prompt: str,
    duracion: int
) -> str:

    # La implementación actual escribe el texto limpio en un archivo.
    # Las etiquetas de voz se agregan localmente después de esa respuesta.
    try:
        parametros = inspect.signature(generar_guion).parameters
    except (TypeError, ValueError):
        parametros = {}

    if "ruta_salida" in parametros:
        with tempfile.TemporaryDirectory(prefix="mini-clip-guion-") as temporal:
            ruta_temporal = Path(temporal) / "guion.txt"
            resultado = generar_guion(
                prompt_video=f"Título: {titulo}\n\n{prompt}",
                duracion_segundos=duracion,
                ruta_salida=ruta_temporal,
            )
            if isinstance(resultado, Path):
                return resultado.read_text(encoding="utf-8").strip()
            if isinstance(resultado, str):
                try:
                    ruta_generada = Path(resultado)
                    if ruta_generada.is_file():
                        return ruta_generada.read_text(encoding="utf-8").strip()
                except OSError:
                    pass
                if ruta_temporal.is_file():
                    return ruta_temporal.read_text(encoding="utf-8").strip()
                return resultado.strip()
            return ruta_temporal.read_text(encoding="utf-8").strip()

    intentos = [

        lambda: generar_guion(
            titulo=titulo,
            prompt=prompt,
            duracion_segundos=duracion
        ),

        lambda: generar_guion(
            prompt=prompt,
            duracion_segundos=duracion
        ),

        lambda: generar_guion(
            prompt,
            duracion
        ),

        lambda: generar_guion(
            titulo,
            prompt,
            duracion
        ),
    ]

    ultimo_error = None

    for intento in intentos:

        try:

            resultado = intento()

            if isinstance(
                resultado,
                str
            ):

                return resultado.strip()

            if isinstance(
                resultado,
                dict
            ):

                for clave in (
                    "guion",
                    "text",
                    "texto",
                    "content"
                ):

                    if clave in resultado:

                        return str(
                            resultado[clave]
                        ).strip()

        except TypeError as exc:

            ultimo_error = exc

            continue

    raise RuntimeError(
        "No pude llamar a "
        "generar_guion() con "
        f"la firma actual: "
        f"{ultimo_error}"
    )


def resolver_archivo_guion(
    contenido: str
) -> Path:

    ruta_fuente = Path(
        contenido
    )

    # 1. Primero intenta exactamente
    # la ruta enviada por consola.
    if ruta_fuente.exists():
        return ruta_fuente

    # 2. Si solo enviamos el nombre,
    # busca automáticamente en guiones\
    ruta_guiones = (
        GUIONES_DIR
        / contenido
    )

    if ruta_guiones.exists():
        return ruta_guiones

    raise FileNotFoundError(
        "No existe el archivo de guion.\n"
        f"Busqué en:\n"
        f"  {ruta_fuente}\n"
        f"  {ruta_guiones}"
    )


def _crear_clip_sin_log(
    modo: str,
    titulo: str,
    contenido: str,
    duracion_prompt=None
):

    CLIPS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    GUIONES_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    if modo == "guion":

        ruta_fuente = (
            resolver_archivo_guion(
                contenido
            )
        )

        print(
            f"[MAIN] Guion encontrado: "
            f"{ruta_fuente}"
        )

        texto = (
            ruta_fuente.read_text(
                encoding="utf-8"
            )
        )

        config = (
            parsear_guion_configurado(
                texto
            )
        )

        # El título enviado por consola
        # tiene prioridad.
        if titulo.strip():

            config["titulo"] = (
                titulo.strip()
            )

        guion = (
            config["guion"]
        )

    elif modo == "prompt":

        if duracion_prompt is None:

            raise ValueError(
                "El modo --prompt "
                "requiere duración."
            )

        guion = (
            _generar_guion_prompt(
                titulo=titulo,
                prompt=contenido,
                duracion=int(
                    duracion_prompt
                )
            )
        )

        config = {

            "titulo": titulo,

            "resolucion":
                "1080x1920",

            "musica": "",

            "volumen_musica":
                0.10,

            "estilo_visual":
                "",

            "paleta":
                "",

            "seed":
                None,

            "negative_prompt":
                "",

            "personajes":
                {},

            "modo_video":
                MODO_VIDEO_DEFAULT,

            "voz_qwen":
                "Ryan",

            "porcentaje_minimo_stick":
                70.0,

            "permitir_fondos_automaticos":
                True,

            "usar_efectos_sonido":
                True,

            "volumen_efectos":
                0.35,

            "max_efectos_sonido":
                8,

            "imagen_final":
                "",

            "duracion_imagen_final":
                4.0,

            "guion":
                guion,
        }

    else:

        raise ValueError(
            f"Modo desconocido: "
            f"{modo}"
        )

    slug = slugify(
        config["titulo"]
    )

    ruta_clip = (
        CLIPS_DIR
        / slug
    )

    ruta_clip.mkdir(
        parents=True,
        exist_ok=True
    )

    bitacora = _ACTIVE_CLIP_LOGGER.get()
    try:
        if (
            bitacora is None
            or bitacora.clip_dir.resolve() != ruta_clip.resolve()
        ):
            if bitacora is not None:
                bitacora.finish("relocated")
            bitacora = ClipRunLogger(
                ruta_clip,
                title=config.get("titulo", slug),
                mode=modo,
                input_value=contenido,
                duration_target=(
                    int(duracion_prompt)
                    if duracion_prompt is not None
                    else None
                ),
            )
            _ACTIVE_CLIP_LOGGER.set(bitacora)
        print(f"[LOG] Registro de generación: {bitacora.path.resolve()}")
    except Exception as log_exc:
        bitacora = None
        _ACTIVE_CLIP_LOGGER.set(None)
        print(f"[LOG] ERROR: no pude iniciar log.json: {log_exc}")

    ruta_guion = (
        ruta_clip
        / "guion.txt"
    )

    ruta_guion_limpio = (
        ruta_clip
        / "guion_limpio.txt"
    )

    ruta_config = (
        ruta_clip
        / "config.json"
    )

    ruta_audio = (
        ruta_clip
        / "audio.wav"
    )

    ruta_subtitulos = (
        ruta_clip
        / "subtitulos.ass"
    )

    ruta_segmentos = (
        ruta_clip
        / "segmentos.json"
    )

    carpeta_imagenes = (
        ruta_clip
        / "images"
    )

    ruta_video = (
        ruta_clip
        / "video.mp4"
    )

    efectos_sonido = listar_efectos_sonido()
    if config["modo_video"] in {"stick", "mixed"}:
        assets = AssetLibrary()
        cast = parse_cast(config.get("cast") or config.get("personajes", {}), assets)
        if not cast:
            raise ValueError("Los modos stick/mixed requieren [CAST], por ejemplo: peter = jhon")
        config["personajes"] = cast
        config["cast"] = cast
        original = guion
        guion, cambios = preparar_guion_visual(
            guion, cast, assets,
            list(efectos_sonido) if config.get("usar_efectos_sonido", True) else [],
            config.get("max_efectos_sonido", 8),
            modo_video=config["modo_video"],
            porcentaje_minimo_stick=config.get("porcentaje_minimo_stick", 70),
        )
        ruta_clip.joinpath("guion_original.txt").write_text(original, encoding="utf-8")
        if modo == "guion":
            prefijo = re.split(r"(?mi)^\[GUION\]", texto, maxsplit=1)[0]
        else:
            prefijo = f"[TITULO]\n{config['titulo']}\n\n[MODO_VIDEO]\n{config['modo_video']}\n\n"
        ruta_clip.joinpath("guion_adaptado.txt").write_text(prefijo + "[GUION]\n" + guion, encoding="utf-8")
        ruta_clip.joinpath("cambios_recursos.json").write_text(json.dumps(cambios, ensure_ascii=False, indent=2), encoding="utf-8")

    guion_limpio = limpiar_guion_audio(guion)
    guion_audio = formatear_guion_audio(
        guion,
        voz_default=config.get("voz_qwen", "Ryan"),
    )
    config["guion"] = guion_limpio

    # El archivo editable para locución lleva las etiquetas; las herramientas
    # visuales reciben un archivo limpio para no ver instrucciones de audio.
    ruta_guion.write_text(
        guion_audio,
        encoding="utf-8"
    )
    ruta_guion_limpio.write_text(
        guion_limpio,
        encoding="utf-8"
    )

    guardar_config(
        config,
        ruta_config
    )

    print(
        f"[MAIN] Clip: "
        f"{ruta_clip}"
    )

    print(
        f"[MAIN] Modo de video: "
        f"{config['modo_video'].upper()}"
    )

    print(
        "[MAIN] Generando audio..."
    )

    ruta_audio.with_suffix(".timeline.json").unlink(missing_ok=True)
    _llamar_generar_audio(
        ruta_guion=ruta_guion,
        ruta_audio=ruta_audio,
        voz_qwen=config.get("voz_qwen", "Ryan"),
    )

    timeline_path = ruta_audio.with_suffix(".timeline.json")
    audio_timeline = json.loads(timeline_path.read_text(encoding="utf-8")) if timeline_path.is_file() else None

    duracion_real = (
        obtener_duracion_audio(
            ruta_audio
        )
    )

    print(
        f"[MAIN] Duración real "
        f"del audio: "
        f"{duracion_real:.2f} "
        "segundos"
    )

    print(
        "[MAIN] Generando "
        "subtítulos..."
    )

    _llamar_generar_subtitulos(
        ruta_audio=ruta_audio,
        ruta_subtitulos=(
            ruta_subtitulos
        )
    )

    segmentos_whisper = None

    if ruta_segmentos.exists():

        try:

            segmentos_whisper = json.loads(
                ruta_segmentos.read_text(
                    encoding="utf-8"
                )
            )

            print(
                f"[MAIN] Segmentos Whisper: "
                f"{len(segmentos_whisper)}"
            )

        except Exception as exc:

            print(
                "[MAIN] ADVERTENCIA: "
                "No pude leer segmentos.json. "
                "Se usará el modo de duración "
                f"anterior. Detalle: {exc}"
            )

            segmentos_whisper = None

    efectos_sonido = listar_efectos_sonido()

    if config.get("usar_efectos_sonido", True):
        if efectos_sonido:
            print(
                "[SFX] Efectos disponibles: "
                + ", ".join(efectos_sonido.keys())
            )
        else:
            print(
                "[SFX] No hay efectos en sound_efects. "
                "El video se generará sin efectos."
            )
    else:
        print("[SFX] Efectos de sonido desactivados por configuración.")

    clips_stick = None

    if config["modo_video"] in {
        "stick",
        "mixed"
    }:

        print(
            "[MAIN] Generando "
            "escenas STICK..."
        )

        clips_stick = (
            generar_stick_scenes(

                guion=guion,

                duracion_segundos=(
                    duracion_real
                ),

                segmentos=(
                    segmentos_whisper
                ),

                ruta_clip=(
                    ruta_clip
                ),

                resolucion=(
                    config.get(
                        "resolucion",
                        "1080x1920"
                    )
                ),

                fps=30,

                modo_video=(
                    config.get(
                        "modo_video",
                        "stick"
                    )
                ),

                porcentaje_minimo_stick=(
                    config.get(
                        "porcentaje_minimo_stick",
                        70.0
                    )
                ),

                permitir_fondos_automaticos=(
                    config.get(
                        "permitir_fondos_automaticos",
                        True
                    )
                ),

                estilo_visual=(
                    config.get(
                        "estilo_visual",
                        ""
                    )
                ),

                negative_prompt=(
                    config.get(
                        "negative_prompt",
                        ""
                    )
                ),

                seed=(
                    config.get(
                        "seed"
                    )
                ),

                efectos_disponibles=(
                    list(efectos_sonido.keys())
                    if config.get("usar_efectos_sonido", True)
                    else []
                ),

                max_efectos_sonido=(
                    config.get(
                        "max_efectos_sonido",
                        8
                    )
                ),

                personajes_config=(
                    config.get("personajes", {})
                ),
                audio_timeline=audio_timeline,
            )
        )

    else:

        print(
            "[MAIN] Generando "
            "imágenes..."
        )

        carpeta_imagenes.mkdir(
            parents=True,
            exist_ok=True
        )

        generar_imagenes(
            ruta_guion=(
                ruta_guion_limpio
            ),

            duracion_segundos=(
                duracion_real
            ),

            carpeta_imagenes=(
                carpeta_imagenes
            ),

            ruta_config=(
                ruta_config
            )
        )

    print(
        "[MAIN] Generando "
        "video final..."
    )

    generar_video(

        ruta_audio=(
            ruta_audio
        ),

        carpeta_imagenes=(
            carpeta_imagenes
        ),

        ruta_subtitulos=(
            ruta_subtitulos
        ),

        ruta_video=(
            ruta_video
        ),

        ruta_config=(
            ruta_config
        ),

        modo_video=(
            config[
                "modo_video"
            ]
        ),

        clips_stick=(
            clips_stick
        )
    )

    print("")
    print(
        "[MAIN] LISTO"
    )

    print(
        f"[MAIN] Video: "
        f"{ruta_video}"
    )

    return ruta_video


def crear_clip(
    modo: str,
    titulo: str,
    contenido: str,
    duracion_prompt=None,
):
    """Run clip generation and retain a per-folder snapshot for analysis."""
    token = _ACTIVE_CLIP_LOGGER.set(None)
    bitacora = None

    # Abrir la bitácora desde el punto de entrada. Así queda registrada
    # incluso una falla al generar el guion antes de preparar el clip.
    titulo_log = titulo.strip() or Path(str(contenido)).stem or "clip"
    ruta_log = CLIPS_DIR / slugify(titulo_log)

    try:
        bitacora = ClipRunLogger(
            ruta_log,
            title=titulo_log,
            mode=modo,
            input_value=contenido,
            duration_target=(
                int(duracion_prompt)
                if duracion_prompt is not None
                else None
            ),
        )
        _ACTIVE_CLIP_LOGGER.set(bitacora)
        print(f"[LOG] Registro de generación: {bitacora.path.resolve()}")

        resultado = _crear_clip_sin_log(
            modo=modo,
            titulo=titulo,
            contenido=contenido,
            duracion_prompt=duracion_prompt,
        )
    except BaseException as exc:
        bitacora = _ACTIVE_CLIP_LOGGER.get()
        try:
            if bitacora is not None:
                bitacora.finish("failed", error=exc)
                print(f"[LOG] Artefactos del fallo guardados en: {bitacora.path.resolve()}")
        except Exception as log_exc:
            print(f"[LOG] No pude completar log.json: {log_exc}")
        raise
    else:
        bitacora = _ACTIVE_CLIP_LOGGER.get()
        try:
            if bitacora is not None:
                bitacora.finish("completed")
        except Exception as log_exc:
            print(f"[LOG] No pude completar log.json: {log_exc}")
        else:
            if bitacora is not None:
                print(f"[LOG] Artefactos guardados en: {bitacora.path.resolve()}")
        return resultado
    finally:
        _ACTIVE_CLIP_LOGGER.reset(token)


def mostrar_uso():

    print("")

    print(
        "Mini Clip Maker"
    )

    print("")

    print(
        "Usar archivo configurado:"
    )

    print(
        '  py -3.12 main.py '
        '--guion '
        '"Titulo" '
        '"archivo.txt"'
    )

    print("")

    print(
        "El archivo se busca "
        "automáticamente en:"
    )

    print(
        f"  {GUIONES_DIR}"
    )

    print("")

    print(
        "Generar guion "
        "desde prompt:"
    )

    print(
        '  py -3.12 main.py '
        '--prompt '
        '"Titulo" '
        '"Prompt..." '
        '60'
    )

    print("")


def main():

    if len(
        sys.argv
    ) < 2:

        mostrar_uso()

        sys.exit(1)

    comando = (
        sys.argv[1]
        .lower()
    )

    try:

        if comando == "--guion":

            if len(
                sys.argv
            ) != 4:

                mostrar_uso()

                sys.exit(1)

            titulo = (
                sys.argv[2]
            )

            archivo = (
                sys.argv[3]
            )

            crear_clip(
                modo="guion",
                titulo=titulo,
                contenido=archivo
            )

        elif comando == "--prompt":

            if len(
                sys.argv
            ) != 5:

                mostrar_uso()

                sys.exit(1)

            titulo = (
                sys.argv[2]
            )

            prompt = (
                sys.argv[3]
            )

            duracion = int(
                sys.argv[4]
            )

            crear_clip(
                modo="prompt",
                titulo=titulo,
                contenido=prompt,
                duracion_prompt=(
                    duracion
                )
            )

        else:

            mostrar_uso()

            sys.exit(1)

    except Exception as exc:

        print(
            f"[MAIN] ERROR: "
            f"{exc}"
        )

        raise


if __name__ == "__main__":
    main()
