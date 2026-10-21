"""Storyboard de sprites: el guion fija el cast, las acciones y los encuadres."""
from guion_escenas import (
    SCENE, explicit_script, parse_cast, preparar_guion_visual, storyboard_from_script,
)
from .assets import AssetLibrary


def generar_storyboard_stick(
    guion, duracion_segundos, width=1080, height=1920, fps=30,
    segmentos=None, modo_video="stick", porcentaje_minimo_stick=70.0,
    permitir_fondos_automaticos=True, estilo_visual="", efectos_disponibles=None,
    max_efectos_sonido=8, personajes_config=None, audio_timeline=None,
):
    """Conserva el punto de entrada; main ya revisó los recursos antes del TTS.

    Los tiempos del worker incluyen silencios y pausas. Los segmentos de Whisper
    siguen disponibles para subtítulos; no alteran el cast ni parten una escena.
    """
    if modo_video not in {"stick", "mixed"}:
        raise ValueError(f"Modo de video inválido: {modo_video}")
    assets = AssetLibrary()
    cast = parse_cast(personajes_config or {}, assets)
    if not cast:
        raise ValueError("Los modos stick/mixed requieren [CAST]: peter = jhon")
    if not SCENE.search(guion):
        # Compatibilidad con consumidores anteriores del punto de entrada.
        guion, _ = preparar_guion_visual(guion, cast, assets, efectos_disponibles or [], max_efectos_sonido)
    result = storyboard_from_script(
        guion, cast, assets, duracion_segundos, width, height, fps,
        timeline=audio_timeline, sounds=efectos_disponibles or [], max_sfx=max_efectos_sonido,
        modo_video=modo_video, minimum_stick=porcentaje_minimo_stick,
    )
    print(f"[STICK] {len(result['storyboard'])} escenas; sincronización: {result['sync_mode']}")
    for name, asset in cast.items():
        print(f"[CAST] {name} -> {asset}")
    return result
