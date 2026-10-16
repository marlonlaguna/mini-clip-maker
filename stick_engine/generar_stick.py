import json
import re
import unicodedata
from pathlib import Path

from .renderer import StickRenderer
from .storyboard import generar_storyboard_stick
from .visual_generator import VisualGenerator, imagen_a_clip


ASSETS_BACKGROUNDS_DIR = (
    Path(__file__).resolve().parent
    / "assets"
    / "backgrounds"
)


def _crear_renderer():
    """
    Intenta utilizar el renderer GPU.

    Si ModernGL, OpenGL o la GPU fallan por cualquier razón,
    vuelve automáticamente al renderer CPU.
    """

    try:
        from .renderer_gpu import StickRendererGPU

        print("[STICK] Intentando iniciar renderer GPU...")

        renderer = StickRendererGPU()

        gpu_name = renderer.ctx.info.get(
            "GL_RENDERER",
            "GPU desconocida"
        )

        print(
            f"[STICK] Renderer GPU activo: {gpu_name}"
        )

        return renderer, "gpu"

    except Exception as exc:
        print(
            "[STICK] No se pudo iniciar el renderer GPU."
        )
        print(
            f"[STICK] Motivo: {exc}"
        )
        print(
            "[STICK] Usando renderer CPU como fallback."
        )

        return StickRenderer(), "cpu"


def _slug(texto):
    texto = unicodedata.normalize(
        "NFKD",
        str(texto or "")
    )
    texto = "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )
    texto = texto.lower().strip()
    texto = re.sub(r"[^a-z0-9]+", "-", texto)
    return texto.strip("-") or "clip"


def generar_stick_scenes(
    guion,
    duracion_segundos,
    ruta_clip,
    resolucion="1080x1920",
    fps=20,
    segmentos=None,
    modo_video="stick",
    porcentaje_minimo_stick=70.0,
    permitir_fondos_automaticos=True,
    estilo_visual="",
    negative_prompt="",
    seed=None,
    efectos_disponibles=None,
    max_efectos_sonido=8,
    personajes_config=None,
):
    """
    Genera escenas STICK o MIXED.

    STICK:
    - Mantiene el comportamiento tradicional.

    MIXED:
    - Ollama local decide por escena entre stick e ilustración completa.
    - El porcentaje mínimo de stick se fuerza por código.
    - Si una escena stick necesita un fondo inexistente, puede generarse.
    - Nunca se superponen ilustraciones completas sobre personajes stick.
      Si hay stick + imagen generada, esa imagen es únicamente el fondo.

    Sincronización:
    - Si 'segmentos' viene informado, usa timestamps reales de Whisper.
    - Si 'segmentos' es None, conserva el comportamiento por duración.
    """

    modo_video = str(modo_video or "stick").lower()

    if modo_video not in {"stick", "mixed"}:
        raise ValueError(
            f"[STICK] modo_video inválido: {modo_video}"
        )

    print("[STICK] Generando storyboard...")

    width, height = [
        int(x)
        for x in resolucion.lower().split("x", 1)
    ]

    ruta_clip = Path(ruta_clip)
    ruta_stick = ruta_clip / "stick"
    ruta_mixed_images = ruta_clip / "mixed_images"

    ruta_stick.mkdir(
        parents=True,
        exist_ok=True
    )

    if modo_video == "mixed":
        ruta_mixed_images.mkdir(
            parents=True,
            exist_ok=True
        )

    storyboard = generar_storyboard_stick(
        guion=guion,
        duracion_segundos=duracion_segundos,
        width=width,
        height=height,
        fps=fps,
        segmentos=segmentos,
        modo_video=modo_video,
        porcentaje_minimo_stick=porcentaje_minimo_stick,
        permitir_fondos_automaticos=permitir_fondos_automaticos,
        estilo_visual=estilo_visual,
        efectos_disponibles=(
            efectos_disponibles or []
        ),
        max_efectos_sonido=max_efectos_sonido,
        personajes_config=personajes_config or {},
    )

    ruta_storyboard = (
        ruta_clip
        / "stick_storyboard.json"
    )

    ruta_storyboard.write_text(
        json.dumps(
            storyboard,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    escenas = storyboard["storyboard"]
    total_escenas = len(escenas)

    hay_stick = any(
        str(escena.get("scene_type", "stick")).lower()
        == "stick"
        for escena in escenas
    )

    hay_generacion_visual = any(
        str(escena.get("scene_type", "stick")).lower()
        == "illustration"
        or str(escena.get("background_mode", "asset")).lower()
        == "generated"
        for escena in escenas
    )

    renderer = None
    renderer_tipo = "none"

    if hay_stick:
        renderer, renderer_tipo = _crear_renderer()
        print(
            f"[STICK] Motor seleccionado: "
            f"{renderer_tipo.upper()}"
        )

    visual_generator = None

    if hay_generacion_visual:
        visual_generator = VisualGenerator(
            estilo_visual=estilo_visual,
            negative_prompt=negative_prompt,
            seed=seed,
        )
        visual_generator.comprobar()

    clips = []
    clip_slug = _slug(ruta_clip.name)

    try:
        for index, escena in enumerate(
            escenas,
            start=1
        ):
            salida = (
                ruta_stick
                / f"scene_{index:03d}.mp4"
            )

            inicio = escena.get("start")
            fin = escena.get("end")

            if inicio is not None and fin is not None:
                rango = (
                    f"{float(inicio):.2f}s"
                    f" -> "
                    f"{float(fin):.2f}s"
                )
            else:
                rango = (
                    f"{float(escena.get('duration', 0)):.2f}s"
                )

            scene_type = str(
                escena.get("scene_type", "stick")
            ).lower()

            print(
                f"[STICK] Escena "
                f"{index}/{total_escenas} "
                f"[{rango}] "
                f"type={scene_type.upper()} "
                f"background={escena.get('background')} "
                f"characters={len(escena.get('characters', []))} "
                f"objects={len(escena.get('objects', []))}"
            )

            if scene_type == "illustration":
                if visual_generator is None:
                    raise RuntimeError(
                        "[MIXED] Se necesita Stable Diffusion "
                        "para una escena illustration."
                    )

                prompt = (
                    escena.get("illustration_prompt")
                    or escena.get("visual_prompt")
                    or escena.get("narration")
                    or "simple story illustration"
                )

                ruta_imagen = (
                    ruta_mixed_images
                    / f"scene_{index:03d}.png"
                )

                visual_generator.generar_ilustracion(
                    prompt=prompt,
                    ruta_salida=ruta_imagen,
                    width=width,
                    height=height,
                    scene_number=index,
                )

                imagen_a_clip(
                    ruta_imagen=ruta_imagen,
                    ruta_salida=salida,
                    duration=float(
                        escena.get("duration", 1.0)
                    ),
                    width=width,
                    height=height,
                    fps=fps,
                )

                clips.append(salida)
                continue

            background_mode = str(
                escena.get("background_mode", "asset")
            ).lower()

            if background_mode == "generated":
                if not permitir_fondos_automaticos:
                    raise RuntimeError(
                        "[MIXED] El storyboard pidió un fondo generado "
                        "pero [PERMITIR_FONDOS_AUTOMATICOS] está desactivado."
                    )

                if visual_generator is None:
                    raise RuntimeError(
                        "[MIXED] Se necesita Stable Diffusion "
                        "para generar el fondo."
                    )

                background_name = (
                    f"auto_{clip_slug}_{index:03d}"
                )

                ruta_background = (
                    ASSETS_BACKGROUNDS_DIR
                    / f"{background_name}.png"
                )

                prompt_fondo = (
                    escena.get("background_prompt")
                    or escena.get("narration")
                    or "simple cartoon background"
                )

                visual_generator.generar_fondo(
                    prompt=prompt_fondo,
                    ruta_salida=ruta_background,
                    width=width,
                    height=height,
                    scene_number=index,
                )

                escena["background"] = background_name

            if renderer is None:
                renderer, renderer_tipo = _crear_renderer()

            try:
                renderer.render(
                    scene=escena,
                    output_path=salida
                )

            except Exception as exc:
                if renderer_tipo == "gpu":
                    print(
                        f"[STICK] AVISO: GPU falló en escena {index}."
                    )
                    print(
                        f"[STICK] Error GPU: {exc}"
                    )
                    print(
                        "[STICK] Cambiando a CPU..."
                    )

                    try:
                        if hasattr(renderer, "close"):
                            renderer.close()
                    except Exception:
                        pass

                    renderer = StickRenderer()
                    renderer_tipo = "cpu"

                    print(
                        "[STICK] Renderer CPU activo."
                    )

                    renderer.render(
                        scene=escena,
                        output_path=salida
                    )
                else:
                    raise

            clips.append(salida)

    finally:
        try:
            if renderer is not None and hasattr(
                renderer,
                "close"
            ):
                renderer.close()
        except Exception as exc:
            print(
                f"[STICK] Aviso al cerrar renderer: {exc}"
            )

    # Guardamos de nuevo porque los fondos generados reciben
    # su nombre final durante el render.
    ruta_storyboard.write_text(
        json.dumps(
            storyboard,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    cantidad_stick = sum(
        1
        for escena in escenas
        if str(
            escena.get("scene_type", "stick")
        ).lower() == "stick"
    )

    cantidad_illustration = (
        total_escenas - cantidad_stick
    )

    print(
        f"[STICK] {len(clips)} escenas generadas."
    )

    if modo_video == "mixed":
        print(
            f"[MIXED] Stick: {cantidad_stick} | "
            f"Ilustraciones completas: {cantidad_illustration}"
        )

    if renderer_tipo != "none":
        print(
            f"[STICK] Renderer final: "
            f"{renderer_tipo.upper()}"
        )

    return clips
