import json
import math
import re
import unicodedata
from difflib import SequenceMatcher

from ollama_client import OLLAMA_MODEL, ollama_chat
from .assets import AssetLibrary
from .shots import normalize_shot, parts_for_target


SEGUNDOS_POR_ESCENA = 6
MIN_SEGUNDOS_ESCENA = 2.5
OBJETIVO_SEGUNDOS_ESCENA = 5.0
MAX_SEGUNDOS_ESCENA = 7.0
ESCENAS_POR_LOTE = 6


# ============================================================
# UTILIDADES
# ============================================================

def _limpiar_json(texto):
    texto = str(texto or "").strip()

    if texto.startswith("```"):
        texto = (
            texto
            .replace("```json", "")
            .replace("```JSON", "")
            .replace("```", "")
            .strip()
        )

    inicio = texto.find("{")
    fin = texto.rfind("}")

    if inicio == -1 or fin == -1 or fin <= inicio:
        raise ValueError("El modelo no devolvió JSON válido.")

    return json.loads(texto[inicio:fin + 1])


def _slug_personaje(valor):
    valor = unicodedata.normalize(
        "NFKD",
        str(valor or ""),
    )

    valor = "".join(
        c
        for c in valor
        if not unicodedata.combining(c)
    )

    return re.sub(
        r"[^a-z0-9]+",
        "-",
        valor.lower(),
    ).strip("-")


def _texto_normalizado(valor):
    texto = unicodedata.normalize(
        "NFKD",
        str(valor or "").lower(),
    )

    texto = "".join(
        c
        for c in texto
        if not unicodedata.combining(c)
    )

    return " ".join(
        re.findall(
            r"[a-z0-9]+",
            texto,
        )
    )


def _accion_fallback_semantica(
    action,
    acciones_validas,
):
    action = str(
        action or "idle"
    ).strip().lower()

    aliases = {
        "listen": [
            "turn_around",
            "look_back",
            "think",
            "none",
            "idle",
        ],
        "listening": [
            "turn_around",
            "look_back",
            "think",
            "none",
            "idle",
        ],
        "hear": [
            "turn_around",
            "look_back",
            "think",
            "none",
            "idle",
        ],
        "hearing": [
            "turn_around",
            "look_back",
            "think",
            "none",
            "idle",
        ],
        "observe": [
            "turn_around",
            "look_back",
            "think",
            "none",
            "idle",
        ],
        "watch": [
            "turn_around",
            "look_back",
            "none",
            "idle",
        ],
        "look": [
            "turn_around",
            "look_back",
            "none",
            "idle",
        ],
        "look_back": [
            "turn_around",
            "look_back",
            "none",
            "idle",
        ],
        "speak": [
            "speak",
            "talk",
            "none",
            "idle",
        ],
        "talking": [
            "speak",
            "talk",
            "none",
            "idle",
        ],
        "talk": [
            "speak",
            "talk",
            "none",
            "idle",
        ],
        "stand": [
            "none",
            "idle",
        ],
        "standing": [
            "none",
            "idle",
        ],
        "idle": [
            "none",
            "idle",
        ],
        "fear": [
            "afraid",
            "scared",
            "none",
            "idle",
        ],
        "scared": [
            "afraid",
            "scared",
            "none",
            "idle",
        ],
        "hands_up": [
            "afraid",
            "surprised",
            "hands_up",
            "none",
            "idle",
        ],
        "panic": [
            "afraid",
            "scared",
            "surprised",
            "hands_up",
            "none",
            "idle",
        ],
        "open": [
            "open_door",
            "idle",
        ],
        "knocking": [
            "knock",
            "idle",
        ],
        "walking": [
            "walk_front",
            "walk",
            "none",
            "idle",
        ],
        "walk": [
            "walk_front",
            "walk",
            "none",
            "idle",
        ],
        "run": [
            "walk_front",
            "walk",
            "none",
            "idle",
        ],
        "running": [
            "run",
            "walk_front",
            "walk",
            "none",
            "idle",
        ],
        "turn": [
            "turn_around",
            "look_back",
            "none",
            "idle",
        ],
        "turn_around": [
            "turn_around",
            "look_back",
            "none",
            "idle",
        ],
        "surprise": [
            "surprised",
            "none",
            "idle",
        ],
        "surprised": [
            "surprised",
            "none",
            "idle",
        ],
        "crying": [
            "cry",
            "none",
            "idle",
        ],
        "pointing": [
            "point",
            "none",
            "idle",
        ],
        "eating": [
            "eat",
            "none",
            "idle",
        ],
        "sleeping": [
            "sleep",
            "none",
            "idle",
        ],
        "shooting": [
            "shoot",
            "none",
            "idle",
        ],
        "drinking": [
            "drink",
            "none",
            "idle",
        ],
        "smoking": [
            "smoke",
            "none",
            "idle",
        ],
        "falling": [
            "fall",
            "none",
            "idle",
        ],
        "investigate": [
            "think",
            "look_back",
            "idle",
        ],
        "inspect": [
            "think",
            "look_back",
            "idle",
        ],
    }

    if action in acciones_validas:
        return action

    for candidato in aliases.get(
        action,
        [],
    ):
        if candidato in acciones_validas:
            return candidato

    if "idle" in acciones_validas:
        return "idle"

    if "none" in acciones_validas:
        return "none"

    return (
        acciones_validas[0]
        if acciones_validas
        else "idle"
    )


# ============================================================
# TIMELINE
# ============================================================

def _normalizar_segmentos(segmentos):
    if not segmentos:
        return []

    resultado = []

    for item in segmentos:
        if not isinstance(
            item,
            dict,
        ):
            continue

        try:
            start = float(
                item.get(
                    "start",
                    0.0,
                )
            )

            end = float(
                item.get(
                    "end",
                    start,
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            continue

        texto = str(
            item.get(
                "text",
                "",
            )
        ).strip()

        if (
            not texto
            or end <= start
        ):
            continue

        resultado.append({
            "start": max(
                0.0,
                start,
            ),
            "end": max(
                0.0,
                end,
            ),
            "text": texto,
        })

    resultado.sort(
        key=lambda x: (
            x["start"],
            x["end"],
        )
    )

    return resultado


def _agrupar_segmentos(
    segmentos,
    duracion_segundos,
):
    segmentos = _normalizar_segmentos(
        segmentos
    )

    if not segmentos:
        return []

    grupos = []
    actual = None

    for segmento in segmentos:

        if actual is None:

            actual = {
                "source_start": segmento[
                    "start"
                ],
                "source_end": segmento[
                    "end"
                ],
                "texts": [
                    segmento[
                        "text"
                    ]
                ],
            }

            continue

        inicio = actual[
            "source_start"
        ]

        duracion_actual = (
            actual[
                "source_end"
            ]
            - inicio
        )

        duracion_si_agrega = (
            segmento[
                "end"
            ]
            - inicio
        )

        if (
            duracion_si_agrega
            > MAX_SEGUNDOS_ESCENA
            and duracion_actual
            >= MIN_SEGUNDOS_ESCENA
        ):
            grupos.append(
                actual
            )

            actual = {
                "source_start": segmento[
                    "start"
                ],
                "source_end": segmento[
                    "end"
                ],
                "texts": [
                    segmento[
                        "text"
                    ]
                ],
            }

            continue

        actual[
            "source_end"
        ] = segmento[
            "end"
        ]

        actual[
            "texts"
        ].append(
            segmento[
                "text"
            ]
        )

        if (
            actual[
                "source_end"
            ]
            - actual[
                "source_start"
            ]
            >= OBJETIVO_SEGUNDOS_ESCENA
        ):
            grupos.append(
                actual
            )

            actual = None

    if actual is not None:
        grupos.append(
            actual
        )

    if len(grupos) >= 2:

        ultimo = grupos[-1]

        duracion_ultimo = (
            ultimo[
                "source_end"
            ]
            - ultimo[
                "source_start"
            ]
        )

        if (
            duracion_ultimo
            < MIN_SEGUNDOS_ESCENA
        ):
            anterior = grupos[-2]

            combinada = (
                ultimo[
                    "source_end"
                ]
                - anterior[
                    "source_start"
                ]
            )

            if (
                combinada
                <= MAX_SEGUNDOS_ESCENA
                + 2.0
            ):
                anterior[
                    "source_end"
                ] = ultimo[
                    "source_end"
                ]

                anterior[
                    "texts"
                ].extend(
                    ultimo[
                        "texts"
                    ]
                )

                grupos.pop()

    bloques = []
    inicio_visual = 0.0

    for index, grupo in enumerate(
        grupos,
        start=1,
    ):

        fin_visual = min(
            float(
                duracion_segundos
            ),
            float(
                grupo[
                    "source_end"
                ]
            ),
        )

        if index == len(
            grupos
        ):
            fin_visual = float(
                duracion_segundos
            )

        if (
            fin_visual
            <= inicio_visual
        ):
            continue

        bloques.append({
            "scene": len(
                bloques
            ) + 1,

            "start": inicio_visual,

            "end": fin_visual,

            "duration": (
                fin_visual
                - inicio_visual
            ),

            "text": " ".join(
                grupo[
                    "texts"
                ]
            ).strip(),
        })

        inicio_visual = (
            fin_visual
        )

    if bloques:

        bloques[-1][
            "end"
        ] = float(
            duracion_segundos
        )

        bloques[-1][
            "duration"
        ] = (
            bloques[-1][
                "end"
            ]
            - bloques[-1][
                "start"
            ]
        )

    return bloques


def _crear_bloques_fallback(
    guion,
    duracion_segundos,
):
    cantidad = max(
        1,
        math.ceil(
            duracion_segundos
            / SEGUNDOS_POR_ESCENA
        ),
    )

    base = (
        duracion_segundos
        / cantidad
    )

    frases = [
        f.strip()
        for f in re.split(
            r"(?<=[.!?])\s+",
            str(
                guion or ""
            ).strip(),
        )
        if f.strip()
    ]

    bloques = []

    for index in range(
        cantidad
    ):

        start = (
            index
            * base
        )

        end = (
            duracion_segundos
            if index
            == cantidad - 1
            else (
                index + 1
            ) * base
        )

        texto = (
            frases[index]
            if index
            < len(frases)
            else ""
        )

        bloques.append({
            "scene": (
                index + 1
            ),
            "start": start,
            "end": end,
            "duration": (
                end - start
            ),
            "text": texto,
        })

    return bloques


# ============================================================
# CAST PERSISTENTE
# ============================================================

def _personajes_predefinidos(
    personajes_config,
    catalogo,
):
    """
    Construye identidades predefinidas.

    La apariencia visual está en el asset.
    No se utilizan colores.
    """

    resultado = {}

    tipos = catalogo.get(
        "characters",
        {},
    )

    for nombre, descripcion in (
        personajes_config
        or {}
    ).items():

        pid = _slug_personaje(
            nombre
        )

        texto = str(
            descripcion or ""
        )

        lower = texto.lower()

        char_type = next(
            (
                tipo
                for tipo in sorted(
                    tipos.keys(),
                    key=len,
                    reverse=True,
                )
                if re.search(
                    rf"(?<![a-z0-9])"
                    rf"{re.escape(tipo.lower())}"
                    rf"(?![a-z0-9])",
                    lower,
                )
            ),
            None,
        )

        if pid:

            resultado[
                pid
            ] = {
                "id": pid,
                "name": str(
                    nombre
                ),
                "description": texto,
                "type": char_type,
            }

    return resultado


def _normalizar_cast(
    raw_cast,
    catalogo,
    personajes_config,
):
    disponibles = catalogo.get(
        "characters",
        {},
    )

    tipos = list(
        disponibles.keys()
    )

    cast = _personajes_predefinidos(
        personajes_config,
        catalogo,
    )

    if not isinstance(
        raw_cast,
        list,
    ):
        raw_cast = []

    for item in raw_cast:

        if not isinstance(
            item,
            dict,
        ):
            continue

        pid = _slug_personaje(
            item.get(
                "id"
            )
            or item.get(
                "name"
            )
        )

        if not pid:
            continue

        anterior = cast.get(
            pid,
            {},
        )

        char_type = (
            anterior.get(
                "type"
            )
            or str(
                item.get(
                    "type",
                    "",
                )
            ).strip()
        )

        if (
            char_type
            not in disponibles
        ):

            char_type = (
                "stickman"
                if "stickman"
                in disponibles
                else (
                    tipos[0]
                    if tipos
                    else "stickman"
                )
            )

        cast[
            pid
        ] = {
            "id": pid,

            "name": str(
                anterior.get(
                    "name"
                )
                or item.get(
                    "name"
                )
                or pid
            ),

            "description": str(
                anterior.get(
                    "description"
                )
                or item.get(
                    "description",
                    "",
                )
            ),

            "type": char_type,
        }

    return cast


def _extraer_cast_ollama(
    guion,
    catalogo,
    personajes_config,
):
    characters_json = json.dumps(
        catalogo.get(
            "characters",
            {},
        ),
        ensure_ascii=False,
    )

    predef = json.dumps(
        personajes_config
        or {},
        ensure_ascii=False,
        indent=2,
    )

    prompt = f"""
You are the continuity casting director for Mini Clip Maker.

Analyze the COMPLETE narration and create a persistent cast for
recurring people or recurring animal characters.

AVAILABLE CHARACTER TYPES AND ACTIONS:

{characters_json}

PREDEFINED CHARACTERS:

{predef}

COMPLETE NARRATION:

{guion}

STRICT RULES:

- Return ONLY JSON.
- A real person must have ONE stable id for the entire video.
- Do not create multiple ids for the same person.
- Pronouns later in the story must refer to the same existing identity.
- type must exist in AVAILABLE CHARACTER TYPES.
- The character type is the visual identity.
- Never assign a color.
- Never include a "color" field.
- Do not create cast entries for abstract concepts.
- Do not assign actions here.
- If PREDEFINED CHARACTERS specifies a valid type, obey it.

IMPORTANT:

"narrator" is a reserved character id.

If the available character types contain "narrator",
do not use the narrator asset for ordinary people in the story.

RETURN:

{{
  "cast": [
    {{
      "id": "julian",
      "name": "Julian",
      "type": "young_man",
      "description": "main recurring adult man"
    }}
  ]
}}
"""

    print(
        "[CAST] Analizando "
        "personajes recurrentes "
        f"con {OLLAMA_MODEL}..."
    )

    texto = ollama_chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "Return strict JSON only. "
                    "Your job is character "
                    "continuity. "
                    "Never create or return "
                    "character colors."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        json_mode=True,
        temperature=0.05,
        num_predict=1800,
    )

    data = _limpiar_json(
        texto
    )

    cast = _normalizar_cast(
        data.get(
            "cast",
            [],
        ),
        catalogo,
        personajes_config,
    )

    print(
        "[CAST] Reparto persistente: "
        f"{len(cast)} personajes."
    )

    for personaje in cast.values():

        print(
            f"[CAST] "
            f"{personaje['id']} -> "
            f"{personaje['type']}"
        )

    return cast


def _aplicar_cast_global(
    escenas,
    cast,
    catalogo,
):
    disponibles = catalogo.get(
        "characters",
        {},
    )

    tipos = list(
        disponibles.keys()
    )

    for escena in escenas:

        chars = escena.get(
            "characters",
            [],
        )

        if not isinstance(
            chars,
            list,
        ):
            escena[
                "characters"
            ] = []

            continue

        for personaje in chars:

            if not isinstance(
                personaje,
                dict,
            ):
                continue

            personaje.pop(
                "color",
                None,
            )

            pid = _slug_personaje(
                personaje.get(
                    "id"
                )
                or personaje.get(
                    "name"
                )
                or personaje.get(
                    "type"
                )
            )

            if not pid:

                pid = (
                    f"extra-"
                    f"{len(cast) + 1}"
                )

            personaje[
                "id"
            ] = pid

            if pid not in cast:

                char_type = str(
                    personaje.get(
                        "type",
                        "",
                    )
                ).strip()

                if (
                    char_type
                    not in disponibles
                ):

                    char_type = (
                        "stickman"
                        if "stickman"
                        in disponibles
                        else (
                            tipos[0]
                            if tipos
                            else "stickman"
                        )
                    )

                cast[
                    pid
                ] = {
                    "id": pid,
                    "name": pid,
                    "description": (
                        "Character introduced "
                        "during storyboard "
                        "generation."
                    ),
                    "type": char_type,
                }

                print(
                    "[CAST] Nueva identidad: "
                    f"{pid} -> "
                    f"{cast[pid]['type']}"
                )

            fijo = cast[
                pid
            ]

            personaje[
                "type"
            ] = fijo[
                "type"
            ]

            acciones = disponibles.get(
                fijo[
                    "type"
                ],
                [],
            )

            personaje[
                "action"
            ] = _accion_fallback_semantica(
                personaje.get(
                    "action",
                    "idle",
                ),
                acciones,
            )


# ============================================================
# SFX
# ============================================================

def _normalizar_sfx(
    escena,
    efectos_disponibles,
):
    permitidos = {
        str(
            x
        ).strip()
        for x in (
            efectos_disponibles
            or []
        )
        if str(
            x
        ).strip()
    }

    raw = escena.get(
        "sound_effects",
        [],
    )

    if not isinstance(
        raw,
        list,
    ):
        raw = []

    resultado = []

    for item in raw[:2]:

        if not isinstance(
            item,
            dict,
        ):
            continue

        nombre = str(
            item.get(
                "name",
                "",
            )
        ).strip()

        if (
            not nombre
            or nombre
            not in permitidos
        ):
            continue

        try:

            tiempo = float(
                item.get(
                    "time",
                    0.0,
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            tiempo = 0.0

        try:

            volumen = float(
                item.get(
                    "volume",
                    0.7,
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            volumen = 0.7

        resultado.append({
            "name": nombre,

            "time": max(
                0.0,
                tiempo,
            ),

            "volume": max(
                0.0,
                min(
                    1.5,
                    volumen,
                ),
            ),
        })

    escena[
        "sound_effects"
    ] = resultado


# ============================================================
# VALIDACIÓN STORYBOARD
# ============================================================

def _validar_storyboard(
    data,
    catalogo,
    cantidad_escenas,
    modo_video="stick",
    permitir_fondos_automaticos=True,
    efectos_disponibles=None,
):
    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "Storyboard inválido."
        )

    escenas = data.get(
        "storyboard"
    )

    if not isinstance(
        escenas,
        list,
    ):
        raise ValueError(
            "'storyboard' debe ser "
            "una lista."
        )

    if len(
        escenas
    ) != cantidad_escenas:

        raise ValueError(
            f"El modelo generó "
            f"{len(escenas)} escenas "
            f"pero se esperaban "
            f"{cantidad_escenas}."
        )

    backgrounds = set(
        catalogo.get(
            "backgrounds",
            [],
        )
    )

    emotions = set(
        catalogo.get(
            "emotions",
            [],
        )
    )

    characters_catalog = (
        catalogo.get(
            "characters",
            {},
        )
    )

    fondo_default = (
        sorted(
            backgrounds
        )[0]
        if backgrounds
        else ""
    )

    for index, escena in enumerate(
        escenas,
        start=1,
    ):

        if not isinstance(
            escena,
            dict,
        ):
            raise ValueError(
                f"Escena {index}: "
                "debe ser objeto JSON."
            )

        _normalizar_sfx(
            escena,
            efectos_disponibles,
        )

        if (
            efectos_disponibles
            and not escena.get(
                "sound_effects"
            )
        ):
            raise ValueError(
                f"Escena {index}: "
                "debe incluir al menos "
                "un efecto de sonido "
                "válido."
            )

        scene_type = str(
            escena.get(
                "scene_type",
                "stick",
            )
        ).lower()

        if (
            modo_video
            != "mixed"
        ):
            scene_type = (
                "stick"
            )

        if scene_type not in {
            "stick",
            "illustration",
        }:
            scene_type = (
                "stick"
            )

        escena[
            "scene_type"
        ] = scene_type

        # ====================================================
        # ILUSTRACIÓN
        # ====================================================

        if (
            scene_type
            == "illustration"
        ):
            prompt = str(
                escena.get(
                    "illustration_prompt",
                    "",
                )
            ).strip()

            if not prompt:

                raise ValueError(
                    f"Escena {index}: "
                    "illustration_prompt "
                    "vacío."
                )

            escena[
                "illustration_prompt"
            ] = prompt

            try:

                prioridad = int(
                    escena.get(
                        "illustration_priority",
                        50,
                    )
                )

            except (
                TypeError,
                ValueError,
            ):
                prioridad = 50

            escena[
                "illustration_priority"
            ] = max(
                0,
                min(
                    100,
                    prioridad,
                ),
            )

            fallback = str(
                escena.get(
                    "fallback_background",
                    "",
                )
            ).strip()

            if (
                fallback
                not in backgrounds
            ):
                fallback = (
                    fondo_default
                )

            escena[
                "fallback_background"
            ] = fallback

            escena[
                "characters"
            ] = []

            escena[
                "objects"
            ] = []

            escena["shot"] = normalize_shot("full_body")

            continue

        # ====================================================
        # STICK
        # ====================================================

        background_mode = str(
            escena.get(
                "background_mode",
                "asset",
            )
        ).lower()

        if background_mode not in {
            "asset",
            "generated",
        }:
            background_mode = (
                "asset"
            )

        if (
            background_mode
            == "generated"
            and not
            permitir_fondos_automaticos
        ):
            background_mode = (
                "asset"
            )

        escena[
            "background_mode"
        ] = background_mode

        if (
            background_mode
            == "generated"
        ):

            prompt = str(
                escena.get(
                    "background_prompt",
                    "",
                )
            ).strip()

            if not prompt:

                raise ValueError(
                    f"Escena {index}: "
                    "background_prompt "
                    "vacío."
                )

            escena[
                "background_prompt"
            ] = prompt

            fallback = str(
                escena.get(
                    "fallback_background",
                    "",
                )
            ).strip()

            if (
                fallback
                not in backgrounds
            ):
                fallback = (
                    fondo_default
                )

            escena[
                "fallback_background"
            ] = fallback

            escena[
                "background"
            ] = fallback

        else:

            fondo = str(
                escena.get(
                    "background",
                    "",
                )
            ).strip()

            if (
                fondo
                not in backgrounds
            ):

                if fondo_default:

                    escena[
                        "background"
                    ] = fondo_default

                else:

                    raise ValueError(
                        f"Escena {index}: "
                        "background inválido "
                        f"'{fondo}'."
                    )

        personajes = escena.get(
            "characters",
            [],
        )

        if not isinstance(
            personajes,
            list,
        ):

            personajes = []

            escena[
                "characters"
            ] = personajes

        posiciones = set()

        for personaje in personajes[
            :5
        ]:

            tipo = personaje.get(
                "type"
            )

            if (
                tipo
                not in characters_catalog
            ):
                raise ValueError(
                    f"Escena {index}: "
                    "personaje inválido "
                    f"'{tipo}'."
                )

            acciones = (
                characters_catalog[
                    tipo
                ]
            )

            personaje[
                "action"
            ] = _accion_fallback_semantica(
                personaje.get(
                    "action",
                    "idle",
                ),
                acciones,
            )

            emotion = personaje.get(
                "emotion"
            )

            if (
                emotion is not None
                and emotion
                not in emotions
            ):
                personaje.pop(
                    "emotion",
                    None,
                )

            try:

                position = int(
                    personaje.get(
                        "position",
                        len(
                            posiciones
                        ) + 1,
                    )
                )

            except (
                TypeError,
                ValueError,
            ):

                position = (
                    len(
                        posiciones
                    ) + 1
                )

            position = max(
                1,
                min(
                    5,
                    position,
                ),
            )

            while (
                position
                in posiciones
                and position < 5
            ):
                position += 1

            if (
                position
                in posiciones
            ):

                for candidato in range(
                    1,
                    6,
                ):

                    if (
                        candidato
                        not in posiciones
                    ):
                        position = (
                            candidato
                        )

                        break

            personaje[
                "position"
            ] = position

            posiciones.add(
                position
            )

        escena[
            "characters"
        ] = personajes[
            :5
        ]

        shot = normalize_shot(escena.get("shot"))
        if shot["target"] != "full_body":
            character_ids = {
                str(personaje.get("id", "")).strip()
                for personaje in escena["characters"]
                if isinstance(personaje, dict)
            }
            if not character_ids:
                shot = normalize_shot("full_body")
            elif shot["character"] not in character_ids:
                shot["character"] = next(
                    personaje["id"]
                    for personaje in escena["characters"]
                    if isinstance(personaje, dict)
                    and personaje.get("id")
                )
            selected_character = next(
                (
                    personaje
                    for personaje in escena["characters"]
                    if isinstance(personaje, dict)
                    and str(personaje.get("id", "")).strip() == shot["character"]
                ),
                None,
            )
            if selected_character:
                parts_by_type = catalogo.get("character_parts", {})
                character_type = selected_character.get("type")
                available_parts = parts_by_type.get(character_type)
                if (
                    available_parts is not None
                    and parts_for_target(shot["target"], available_parts) is None
                ):
                    shot = normalize_shot("full_body")
        escena["shot"] = shot

        objects = escena.get(
            "objects",
            [],
        )

        if not isinstance(
            objects,
            list,
        ):
            objects = []

        objetos_validos = []

        for obj in objects[
            :3
        ]:

            if not isinstance(
                obj,
                dict,
            ):
                continue

            if (
                str(
                    obj.get(
                        "type",
                        "",
                    )
                ).lower()
                != "emoji"
            ):
                continue

            value = str(
                obj.get(
                    "value",
                    "",
                )
            ).strip()

            if not value:
                continue

            try:

                x = float(
                    obj.get(
                        "x",
                        0.5,
                    )
                )

            except (
                TypeError,
                ValueError,
            ):
                x = 0.5

            try:

                y = float(
                    obj.get(
                        "y",
                        0.5,
                    )
                )

            except (
                TypeError,
                ValueError,
            ):
                y = 0.5

            try:

                size = int(
                    obj.get(
                        "size",
                        120,
                    )
                )

            except (
                TypeError,
                ValueError,
            ):
                size = 120

            obj[
                "x"
            ] = max(
                0.0,
                min(
                    1.0,
                    x,
                ),
            )

            obj[
                "y"
            ] = max(
                0.0,
                min(
                    1.0,
                    y,
                ),
            )

            obj[
                "size"
            ] = max(
                20,
                min(
                    500,
                    size,
                ),
            )

            objetos_validos.append(
                obj
            )

        escena[
            "objects"
        ] = objetos_validos

        if not objetos_validos:

            raise ValueError(
                f"Escena {index}: "
                "toda escena stick "
                "debe incluir al menos "
                "un emoji válido."
            )

    return escenas


# ============================================================
# REPETICIÓN VISUAL
# ============================================================

def _escena_signature(
    escena,
):
    scene_type = str(
        escena.get(
            "scene_type",
            "stick",
        )
    ).lower()

    if (
        scene_type
        == "illustration"
    ):
        return (
            "illustration",
            _texto_normalizado(
                escena.get(
                    "illustration_prompt",
                    "",
                )
            ),
        )

    background = (
        escena.get(
            "background_prompt",
            "",
        )
        if escena.get(
            "background_mode"
        ) == "generated"
        else escena.get(
            "background",
            "",
        )
    )

    characters = tuple(
        sorted(
            (
                _slug_personaje(
                    c.get(
                        "id"
                    )
                ),

                str(
                    c.get(
                        "type",
                        "",
                    )
                ),

                str(
                    c.get(
                        "action",
                        "idle",
                    )
                ),

                str(
                    c.get(
                        "position",
                        "",
                    )
                ),

                str(
                    c.get(
                        "emotion",
                        "",
                    )
                ),
            )
            for c in escena.get(
                "characters",
                [],
            )
        )
    )

    objects = tuple(
        sorted(
            str(
                obj.get(
                    "value",
                    "",
                )
            )
            for obj in escena.get(
                "objects",
                [],
            )
        )
    )

    return (
        scene_type,
        _texto_normalizado(
            background
        ),
        (
            normalize_shot(escena.get("shot"))["target"],
            normalize_shot(escena.get("shot"))["character"],
        ),
        characters,
        objects,
    )


def _escenas_repetidas(
    escenas,
):
    firmas = [
        _escena_signature(
            e
        )
        for e in escenas
    ]

    repetidas = []

    for i in range(
        len(
            firmas
        )
    ):

        for j in range(
            i + 1,
            len(
                firmas
            ),
        ):

            a = firmas[i]
            b = firmas[j]

            if a == b:

                repetidas.append(
                    (
                        i + 1,
                        j + 1,
                    )
                )

                continue

            if (
                len(a) > 1
                and len(b) > 1
                and a[0] == b[0]
            ):

                ta = str(
                    a[1]
                )

                tb = str(
                    b[1]
                )

                if (
                    ta
                    and tb
                    and SequenceMatcher(
                        None,
                        ta,
                        tb,
                    ).ratio()
                    >= 0.95
                    and a[2:]
                    == b[2:]
                ):
                    repetidas.append(
                        (
                            i + 1,
                            j + 1,
                        )
                    )

    return repetidas


def _rotar_posiciones_escena(
    escena,
):
    personajes = escena.get(
        "characters",
        [],
    )

    if not personajes:
        return False

    if len(
        personajes
    ) == 1:

        actual = personajes[
            0
        ].get(
            "position",
            2,
        )

        ciclo = [
            2,
            1,
            3,
            4,
            5,
        ]

        try:

            idx = ciclo.index(
                int(
                    actual
                )
            )

        except (
            ValueError,
            TypeError,
        ):

            idx = -1

        personajes[
            0
        ][
            "position"
        ] = ciclo[
            (
                idx + 1
            )
            % len(
                ciclo
            )
        ]

        return True

    posiciones = [
        int(
            p.get(
                "position",
                i + 1,
            )
        )
        for i, p in enumerate(
            personajes
        )
    ]

    nuevas = (
        posiciones[1:]
        + posiciones[:1]
    )

    for personaje, pos in zip(
        personajes,
        nuevas,
    ):

        personaje[
            "position"
        ] = pos

    return True


def _reparar_repeticiones(
    escenas,
):
    for _ in range(
        4
    ):

        repetidas = (
            _escenas_repetidas(
                escenas
            )
        )

        if not repetidas:
            return []

        modifico = False
        tocadas = set()

        for _, segundo in repetidas:

            idx = (
                segundo - 1
            )

            if idx in tocadas:
                continue

            if not (
                0
                <= idx
                < len(
                    escenas
                )
            ):
                continue

            escena = escenas[
                idx
            ]

            if (
                str(
                    escena.get(
                        "scene_type",
                        "stick",
                    )
                ).lower()
                != "stick"
            ):
                continue

            if (
                _rotar_posiciones_escena(
                    escena
                )
            ):
                tocadas.add(
                    idx
                )

                modifico = (
                    True
                )

        if not modifico:
            break

    return _escenas_repetidas(
        escenas
    )


# ============================================================
# MIXED
# ============================================================

def _forzar_limite_mixed(
    escenas,
    catalogo,
    porcentaje_minimo_stick,
    permitir_fondos_automaticos,
):
    total = len(
        escenas
    )

    if total == 0:
        return escenas

    minimo = max(
        0.0,
        min(
            100.0,
            float(
                porcentaje_minimo_stick
            ),
        ),
    )

    max_ilustraciones = (
        math.floor(
            total
            * (
                100.0
                - minimo
            )
            / 100.0
        )
    )

    ilustraciones = [
        (
            i,
            e,
        )
        for i, e in enumerate(
            escenas
        )
        if str(
            e.get(
                "scene_type",
                "stick",
            )
        ).lower()
        == "illustration"
    ]

    if (
        len(
            ilustraciones
        )
        <= max_ilustraciones
    ):
        return escenas

    ordenadas = sorted(
        ilustraciones,
        key=lambda item: int(
            item[1].get(
                "illustration_priority",
                50,
            )
        ),
        reverse=True,
    )

    conservar = {
        i
        for i, _ in ordenadas[
            :max_ilustraciones
        ]
    }

    backgrounds = list(
        catalogo.get(
            "backgrounds",
            [],
        )
    )

    fallback_default = (
        backgrounds[0]
        if backgrounds
        else ""
    )

    for index, escena in (
        ilustraciones
    ):

        if index in conservar:
            continue

        print(
            "[MIXED] Escena "
            f"{index + 1}: "
            "ilustración convertida "
            "a STICK."
        )

        escena[
            "scene_type"
        ] = "stick"

        escena[
            "characters"
        ] = []

        escena[
            "objects"
        ] = []

        fallback = str(
            escena.get(
                "fallback_background",
                "",
            )
        ).strip()

        if (
            fallback
            not in backgrounds
        ):
            fallback = (
                fallback_default
            )

        if (
            permitir_fondos_automaticos
        ):

            escena[
                "background_mode"
            ] = "generated"

            escena[
                "background"
            ] = fallback

            escena[
                "fallback_background"
            ] = fallback

            escena[
                "background_prompt"
            ] = (
                str(
                    escena.get(
                        "illustration_prompt",
                        "",
                    )
                ).strip()
                or (
                    "dark atmospheric "
                    "environment only, "
                    "no people, "
                    "no humans, "
                    "empty foreground"
                )
            )

        else:

            escena[
                "background_mode"
            ] = "asset"

            escena[
                "background"
            ] = fallback

    return escenas


def _forzar_limite_efectos(
    escenas,
    max_efectos_sonido,
):
    try:

        limite = max(
            0,
            int(
                max_efectos_sonido
            ),
        )

    except (
        TypeError,
        ValueError,
    ):
        limite = 8

    usados = 0

    for escena in escenas:

        efectos = list(
            escena.get(
                "sound_effects",
                [],
            )
        )

        restantes = max(
            0,
            limite - usados,
        )

        escena[
            "sound_effects"
        ] = efectos[
            :restantes
        ]

        usados += len(
            escena[
                "sound_effects"
            ]
        )

    return escenas


# ============================================================
# CONTEXTO DE ESCENAS PREVIAS
# ============================================================

def _resumen_previas(
    escenas,
    limite=3,
):
    resultado = []

    for escena in escenas[
        -limite:
    ]:

        resultado.append({
            "scene": escena.get(
                "scene"
            ),

            "scene_type": escena.get(
                "scene_type",
                "stick",
            ),

            "shot": normalize_shot(
                escena.get("shot")
            ),

            "background": escena.get(
                "background"
            ),

            "background_mode": escena.get(
                "background_mode"
            ),

            "characters": [
                {
                    "id": p.get(
                        "id"
                    ),

                    "type": p.get(
                        "type"
                    ),

                    "action": p.get(
                        "action"
                    ),

                    "position": p.get(
                        "position"
                    ),
                }
                for p in escena.get(
                    "characters",
                    [],
                )
            ],

            "objects": [
                {
                    "type": obj.get(
                        "type"
                    ),

                    "value": obj.get(
                        "value"
                    ),
                }
                for obj in escena.get(
                    "objects",
                    [],
                )
            ],
        })

    return resultado


# ============================================================
# PROMPT
# ============================================================

def _crear_prompt_lote(
    lote,
    catalogo,
    cast,
    previas,
    modo_video,
    porcentaje_minimo_stick,
    permitir_fondos_automaticos,
    estilo_visual,
    efectos_disponibles,
    efectos_restantes,
):
    bloques_json = json.dumps(
        lote,
        ensure_ascii=False,
        indent=2,
    )

    cast_json = json.dumps(
        list(
            cast.values()
        ),
        ensure_ascii=False,
        indent=2,
    )

    chars_json = json.dumps(
        catalogo.get(
            "characters",
            {},
        ),
        ensure_ascii=False,
        indent=2,
    )

    backgrounds_json = json.dumps(
        catalogo.get(
            "backgrounds",
            [],
        ),
        ensure_ascii=False,
        indent=2,
    )

    emotions_json = json.dumps(
        catalogo.get(
            "emotions",
            [],
        ),
        ensure_ascii=False,
        indent=2,
    )

    previas_json = json.dumps(
        _resumen_previas(
            previas
        ),
        ensure_ascii=False,
        indent=2,
    )

    efectos_json = json.dumps(
        efectos_disponibles,
        ensure_ascii=False,
        indent=2,
    )

    # ========================================================
    # SFX
    # ========================================================

    if (
        efectos_disponibles
        and efectos_restantes > 0
    ):

        reglas_sfx = f"""
==================================================
SOUND EFFECTS — REQUIRED
==================================================

AVAILABLE SOUND EFFECTS:

{efectos_json}

Remaining global budget:

{efectos_restantes}

Sound effects are an IMPORTANT part of Mini Clip Maker.

EVERY scene MUST contain at least ONE valid sound effect
while there is remaining sound-effect budget.

Rules:

- sound_effects MUST NOT be empty when effects are available.
- Use ONLY exact names from AVAILABLE SOUND EFFECTS.
- Prefer a sound that literally matches the narration.
- If no exact event sound exists, choose the closest believable ambient sound.
- Normally use exactly 1 sound effect per scene.
- Maximum 2 sound effects when clearly useful.
- time is relative to the start of the scene.
- volume should normally be between 0.45 and 0.85.
- Never invent an effect name.
"""

    else:

        reglas_sfx = """
==================================================
SOUND EFFECTS
==================================================

No usable sound effects are available.

Return:

"sound_effects": []

for every scene.
"""

    # ========================================================
    # MIXED
    # ========================================================

    if modo_video == "mixed":

        reglas_mixed = f"""
==================================================
MIXED VISUAL MODE
==================================================

scene_type can be:

"stick"
or
"illustration"

Across the complete video at least
{porcentaje_minimo_stick:.0f}%
must remain stick.

Do NOT make everything stick merely because that is safe.

For a normal batch of six scenes:

- normally use 4 or 5 stick scenes
- normally use 1 or 2 illustrations

Use illustration when useful for:

- dramatic reveals
- establishing shots
- visually complex events
- supernatural events
- important locations
- historical context
- major clues
- events difficult to express with stick assets

Illustration scenes:

- characters = []
- objects = []
- illustration_prompt required
- illustration_priority = 0 to 100
- fallback_background must be valid

STYLE:

{estilo_visual or "cinematic illustrated scene"}
"""

    else:

        reglas_mixed = """
==================================================
STICK MODE
==================================================

Every scene MUST use:

"scene_type": "stick"
"""

    # ========================================================
    # BACKGROUND
    # ========================================================

    if permitir_fondos_automaticos:

        reglas_fondo = """
==================================================
STICK BACKGROUNDS
==================================================

background_mode can be:

"asset"
or
"generated"

Use an existing background when it fits.

Use a generated background when the available assets
do not properly represent the required location.

Generated backgrounds MUST contain environment only.

NO:
- people
- humans
- human silhouettes
- stick figures
- characters
- faces
- bodies

Leave free foreground space for stick characters.

Always include a valid fallback_background.
"""

    else:

        reglas_fondo = """
==================================================
STICK BACKGROUNDS
==================================================

background_mode MUST be:

"asset"

Use ONLY AVAILABLE BACKGROUNDS.
"""

    # ========================================================
    # OPTIONAL VISUAL NARRATOR
    # ========================================================

    regla_narrator = """
==================================================
OPTIONAL VISUAL NARRATOR
==================================================

The narration may be voice-over without showing a narrator character.
The visual narrator is optional in every scene, including scene 1.
Choose whether showing the narrator improves the scene.
If used, keep id="narrator" and type="narrator".
"""

    return f"""
You are the professional visual director and storyboard artist
for Mini Clip Maker.

Your job is NOT merely to produce technically valid JSON.

Your job is to make every scene visually interesting,
clear, dynamic and different while faithfully representing
the narration.

RETURN ONLY VALID JSON.

NO markdown.
NO explanations.
NO comments.
NO text outside JSON.

==================================================
PRIMARY OBJECTIVE
==================================================

For every narration block decide:

1. What should the viewer see?
2. Which characters should appear?
3. What should they be doing?
4. Which emoji helps communicate the narration?
5. Which sound should be heard?
6. Which background best represents the place?
7. Would a generated background be better?
8. Would an illustration communicate the moment better?

Actively create visual variety.

==================================================
TIMELINE
==================================================

Generate EXACTLY {len(lote)} scenes.

One scene for every timeline block.

Never:
- split a block
- merge blocks
- remove blocks
- invent extra scenes

TIMELINE:

{bloques_json}

==================================================
PERSISTENT CAST
==================================================

{cast_json}

{regla_narrator}

CHARACTER CONTINUITY IS ABSOLUTE.

- Same id = same person.
- NEVER change the type of an existing id.
- type is the character's visual identity.
- NEVER add a color field.
- Reuse existing ids for pronouns when appropriate.
- Never duplicate the identity of the same person.

==================================================
AVAILABLE CHARACTER TYPES AND ACTIONS
==================================================

{chars_json}

ONLY use character types and actions listed above.

Never invent unsupported actions.

Semantic examples:

listening -> look_back or think
hearing -> look_back
watching -> look_back
investigating -> think / look_back / walk
speaking -> talk
walking -> walk
running -> run
panic -> scared / hands_up
opening door -> open_door
knocking -> knock

Avoid idle when another valid action represents the narration better.

Do not use scared automatically merely because
the story is mysterious or dark.

==================================================
AVAILABLE EMOTIONS
==================================================

{emotions_json}

Use only available emotions.

==================================================
AVAILABLE BACKGROUNDS
==================================================

{backgrounds_json}

{reglas_fondo}

==================================================
EMOJI OBJECTS — REQUIRED
==================================================

EVERY STICK SCENE MUST contain at least ONE meaningful emoji.

"objects": [] IS NOT ALLOWED in a stick scene.

Normally use one or two emoji objects.

Examples:

door -> 🚪
key -> 🔑
phone -> 📱
house -> 🏠
building -> 🏢
car -> 🚗
bus -> 🚌
forest -> 🌲
night -> 🌙
sun -> ☀️
rain -> 🌧️
storm -> ⛈️
fire -> 🔥
money -> 💵
camera -> 📷
box -> 📦
medicine -> 💊
time -> 🕐
footprints -> 👣
flashlight -> 🔦
window -> 🪟
letter -> ✉️
book -> 📖
computer -> 💻
television -> 📺
danger -> ⚠️
death -> 💀
police -> 🚓
hospital -> 🏥
airplane -> ✈️
boat -> 🚤
dog -> 🐕
cat -> 🐈

Characters are NOT emojis.

==================================================
VISUAL VARIETY
==================================================

Every new scene should differ from the previous scene
in at least TWO visual dimensions whenever possible:

- action
- character position
- background
- background mode
- emoji
- number of characters
- movement
- emotion
- scene type
- object position
- camera shot

Do not randomly change physical location merely for variety.

==================================================
CAMERA SHOTS
==================================================

Every stick scene must include a "shot" object.
Choose a target that supports the narration and varies the framing.
Use close detail shots selectively, about one in every three scenes at most.

Allowed shot targets:
- full_body: show the full character(s)
- face, head: close-up framed around the character's head/face
- torso: close-up framed around the torso/body
- left_arm, right_arm, arms: close-up framed around the selected arm(s)
- left_leg, right_leg, legs: close-up framed around the selected leg(s)

For a detail shot, set "character" to the id of one character in that scene.
For a full_body shot, set "character" to null.
The close-up keeps the character assembled and zooms toward the requested area.
Do not request body parts absent from the selected character rig. If unsure, use full_body.

If the story remains in one place, vary:
- staging
- actions
- positions
- props
- framing
- character presence

==================================================
RECENT PREVIOUS SCENES
==================================================

{previas_json}

Use these scenes to preserve continuity
and avoid repetition.

{reglas_mixed}

{reglas_sfx}

==================================================
OUTPUT FORMAT
==================================================

Return:

{{
  "storyboard": [
    {{
      "scene": 1,
      "scene_type": "stick",
      "shot": {{"target": "full_body", "character": null}},
      "background_mode": "asset",
      "background": "street",
      "fallback_background": "street",
      "background_prompt": null,
      "illustration_prompt": null,
      "illustration_priority": 0,
      "characters": [],
      "objects": [
        {{
          "type": "emoji",
          "value": "📺",
          "x": 0.78,
          "y": 0.46,
          "size": 130
        }}
      ],
      "sound_effects": [
        {{
          "name": "EXACT_AVAILABLE_EFFECT_NAME",
          "time": 1.2,
          "volume": 0.7
        }}
      ]
    }}
  ]
}}

FINAL CHECK:

1. EXACTLY {len(lote)} scenes.
2. One output scene per timeline block.
3. Every stick scene has at least one emoji.
4. Every scene has a valid SFX when SFX are available.
5. Only valid character assets are used.
6. Only valid actions are used.
7. Character ids/types remain consistent.
8. No color fields.
9. The visual narrator is optional in every scene.
10. Generated stick backgrounds contain no humans.
11. Illustration scenes have characters=[] and objects=[].
12. JSON only.

Return JSON only.
"""


# ============================================================
# PRINCIPAL
# ============================================================

def generar_storyboard_stick(
    guion,
    duracion_segundos,
    width=1080,
    height=1920,
    fps=30,
    segmentos=None,
    modo_video="stick",
    porcentaje_minimo_stick=70.0,
    permitir_fondos_automaticos=True,
    estilo_visual="",
    efectos_disponibles=None,
    max_efectos_sonido=8,
    personajes_config=None,
):
    personajes_config = (
        personajes_config
        or {}
    )

    modo_video = str(
        modo_video
        or "stick"
    ).lower()

    if modo_video not in {
        "stick",
        "mixed",
    }:

        raise ValueError(
            "[STICK] modo_video "
            f"inválido: {modo_video}"
        )

    porcentaje_minimo_stick = max(
        0.0,
        min(
            100.0,
            float(
                porcentaje_minimo_stick
            ),
        ),
    )

    efectos_disponibles = [
        str(
            x
        ).strip()
        for x in (
            efectos_disponibles
            or []
        )
        if str(
            x
        ).strip()
    ]

    try:

        max_efectos_sonido = max(
            0,
            int(
                max_efectos_sonido
            ),
        )

    except (
        TypeError,
        ValueError,
    ):

        max_efectos_sonido = (
            8
        )

    assets = (
        AssetLibrary()
    )

    catalogo = (
        assets.catalog()
    )

    print(
        "[STICK] Backgrounds disponibles:"
    )

    print(
        "[STICK]",
        catalogo.get(
            "backgrounds",
            [],
        ),
    )

    print(
        "[STICK] Personajes y acciones:"
    )

    for tipo, acciones in (
        catalogo.get(
            "characters",
            {},
        ).items()
    ):

        print(
            "[STICK] "
            f"{tipo}: "
            f"{acciones}"
        )

    # El personaje visual narrator es opcional; el audio puede seguir usando
    # narración en off aunque no exista este asset.
    characters_catalog = (
        catalogo.get(
            "characters",
            {},
        )
    )

    if "narrator" in characters_catalog:
        print(
            "[CAST] narrator disponible como personaje opcional: "
            f"{characters_catalog['narrator']}"
        )
    else:
        print(
            "[CAST] No hay asset visual narrator; "
            "se mantiene la narración en off."
        )

    print(
        "[STICK] Emociones disponibles:"
    )

    print(
        "[STICK]",
        catalogo.get(
            "emotions",
            [],
        ),
    )

    print(
        "[OPENAI] Modelo:",
        OLLAMA_MODEL,
    )

    bloques = _agrupar_segmentos(
        segmentos=segmentos,
        duracion_segundos=(
            duracion_segundos
        ),
    )

    usando_whisper = bool(
        bloques
    )

    if usando_whisper:

        print(
            "[STICK] Sincronización: "
            "timestamps reales de Whisper."
        )

    else:

        print(
            "[STICK] Sincronización: "
            "modo compatible por duración."
        )

        bloques = _crear_bloques_fallback(
            guion=guion,
            duracion_segundos=(
                duracion_segundos
            ),
        )

    cantidad = len(
        bloques
    )

    if efectos_disponibles:

        max_efectos_sonido = max(
            max_efectos_sonido,
            cantidad,
        )

    print(
        "[STICK] Bloques visuales: "
        f"{cantidad}"
    )

    for bloque in bloques:

        print(
            "[STICK] "
            f"{bloque['scene']:03d} | "
            f"{bloque['start']:.2f}s -> "
            f"{bloque['end']:.2f}s | "
            f"{str(bloque.get('text', ''))[:90]}"
        )

    if not bloques:

        return {
            "storyboard": [],
            "cast": [],
            "sync_mode": (
                "whisper"
                if usando_whisper
                else "duration"
            ),
            "audio_duration": float(
                duracion_segundos
            ),
            "llm_provider": "openai",
            "llm_model": OLLAMA_MODEL,
        }

    cast = _extraer_cast_ollama(
        guion=guion,
        catalogo=catalogo,
        personajes_config=(
            personajes_config
        ),
    )

    # Se ofrece como personaje visual, pero no se fuerza en ninguna escena.
    if "narrator" in characters_catalog:
        cast["narrator"] = {
            "id": "narrator",
            "name": "Narrator",
            "description": (
                "optional visual presenter; narration may stay off-screen"
            ),
            "type": "narrator",
        }

    escenas_totales = []
    efectos_usados = 0

    total_lotes = math.ceil(
        cantidad
        / ESCENAS_POR_LOTE
    )

    for lote_num, inicio in enumerate(
        range(
            0,
            cantidad,
            ESCENAS_POR_LOTE,
        ),
        start=1,
    ):

        lote = bloques[
            inicio:
            inicio
            + ESCENAS_POR_LOTE
        ]

        ultimo_error = None

        for intento in range(
            1,
            4,
        ):

            try:

                prompt = _crear_prompt_lote(
                    lote=lote,
                    catalogo=catalogo,
                    cast=cast,
                    previas=(
                        escenas_totales
                    ),
                    modo_video=(
                        modo_video
                    ),
                    porcentaje_minimo_stick=(
                        porcentaje_minimo_stick
                    ),
                    permitir_fondos_automaticos=(
                        permitir_fondos_automaticos
                    ),
                    estilo_visual=(
                        estilo_visual
                    ),
                    efectos_disponibles=(
                        efectos_disponibles
                    ),
                    efectos_restantes=max(
                        0,
                        max_efectos_sonido
                        - efectos_usados,
                    ),
                )

                if (
                    intento > 1
                    and ultimo_error
                    is not None
                ):

                    prompt += f"""

CORRECTION:

Previous attempt failed because:

{ultimo_error}

Return corrected strict JSON.

Return EXACTLY {len(lote)} scenes.

Do not explain anything.
"""

                print(
                    "[OPENAI] Lote "
                    f"{lote_num}/"
                    f"{total_lotes}: "
                    f"{len(lote)} escenas "
                    f"con {OLLAMA_MODEL}, "
                    f"intento {intento}/3..."
                )

                texto = ollama_chat(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are the visual "
                                "director for Mini "
                                "Clip Maker. "
                                "Create varied and "
                                "narratively accurate "
                                "storyboards. "
                                "Maintain character "
                                "identity by id and "
                                "asset type. "
                                "The visual narrator is optional "
                                "in every scene; narration may "
                                "remain voice-over. "
                                "Never assign colors. "
                                "Every stick scene must "
                                "contain a meaningful "
                                "emoji. "
                                "When sound effects are "
                                "available every scene "
                                "must contain a valid "
                                "sound effect. "
                                "Return strict JSON only."
                            ),
                        },
                        {
                            "role": "user",
                            "content": prompt,
                        },
                    ],
                    json_mode=True,
                    temperature=(
                        0.12
                        if intento == 1
                        else 0.05
                    ),
                    num_predict=3800,
                )

                data_lote = (
                    _limpiar_json(
                        texto
                    )
                )

                escenas_lote = (
                    data_lote.get(
                        "storyboard"
                    )
                    if isinstance(
                        data_lote,
                        dict,
                    )
                    else None
                )

                if not isinstance(
                    escenas_lote,
                    list,
                ):

                    raise ValueError(
                        "El modelo no devolvió "
                        "una lista storyboard."
                    )

                # Primero aplicamos continuidad
                _aplicar_cast_global(
                    escenas_lote,
                    cast,
                    catalogo,
                )

                data_lote[
                    "storyboard"
                ] = escenas_lote

                escenas_lote = (
                    _validar_storyboard(
                        data=data_lote,
                        catalogo=catalogo,
                        cantidad_escenas=(
                            len(
                                lote
                            )
                        ),
                        modo_video=(
                            modo_video
                        ),
                        permitir_fondos_automaticos=(
                            permitir_fondos_automaticos
                        ),
                        efectos_disponibles=(
                            efectos_disponibles
                        ),
                    )
                )

                for offset, escena in enumerate(
                    escenas_lote
                ):

                    escena[
                        "scene"
                    ] = (
                        inicio
                        + offset
                        + 1
                    )

                candidato = (
                    escenas_totales
                    + escenas_lote
                )

                repetidas = (
                    _reparar_repeticiones(
                        candidato
                    )
                )

                primera_actual = (
                    len(
                        escenas_totales
                    )
                    + 1
                )

                repetidas_actuales = [
                    (
                        a,
                        b,
                    )
                    for a, b
                    in repetidas
                    if (
                        a
                        >= primera_actual
                        or b
                        >= primera_actual
                    )
                ]

                if repetidas_actuales:

                    pares = ", ".join(
                        f"{a} y {b}"
                        for a, b
                        in repetidas_actuales[
                            :8
                        ]
                    )

                    print(
                        "[STICK] AVISO: "
                        "quedaron composiciones "
                        "parecidas "
                        f"({pares}), "
                        "pero se acepta el lote."
                    )

                escenas_lote = (
                    candidato[
                        len(
                            escenas_totales
                        ):
                    ]
                )

                escenas_totales.extend(
                    escenas_lote
                )

                efectos_usados += sum(
                    len(
                        e.get(
                            "sound_effects",
                            [],
                        )
                    )
                    for e
                    in escenas_lote
                )

                print(
                    "[OPENAI] Lote "
                    f"{lote_num}/"
                    f"{total_lotes} OK."
                )

                break

            except Exception as exc:

                ultimo_error = (
                    exc
                )

                print(
                    "[OPENAI] Lote "
                    f"{lote_num}/"
                    f"{total_lotes}, "
                    f"intento {intento}/3 "
                    f"falló: {exc}"
                )

        else:

            raise RuntimeError(
                "[STICK] OpenAI no "
                "pudo generar el lote "
                f"{lote_num}/"
                f"{total_lotes}. "
                "Último error: "
                f"{ultimo_error}"
            )

    escenas = escenas_totales

    # ========================================================
    # MIXED GLOBAL
    # ========================================================

    if (
        modo_video
        == "mixed"
    ):

        escenas = _forzar_limite_mixed(
            escenas=escenas,
            catalogo=catalogo,
            porcentaje_minimo_stick=(
                porcentaje_minimo_stick
            ),
            permitir_fondos_automaticos=(
                permitir_fondos_automaticos
            ),
        )

        # Asegurar de nuevo que la escena 1
        # nunca se convierta en illustration.
        if escenas:

            escenas[0][
                "scene_type"
            ] = "stick"

        total_stick = sum(
            1
            for e in escenas
            if str(
                e.get(
                    "scene_type",
                    "stick",
                )
            ).lower()
            == "stick"
        )

        print(
            "[MIXED] Plan visual: "
            f"{total_stick} stick / "
            f"{len(escenas) - total_stick} "
            "ilustración."
        )

    # ========================================================
    # SFX GLOBAL
    # ========================================================

    escenas = _forzar_limite_efectos(
        escenas,
        max_efectos_sonido,
    )

    # ========================================================
    # TIMING FINAL
    # ========================================================

    for index, escena in enumerate(
        escenas,
        start=1,
    ):

        bloque = bloques[
            index - 1
        ]

        start_real = float(
            bloque[
                "start"
            ]
        )

        end_real = float(
            bloque[
                "end"
            ]
        )

        start_frame = round(
            start_real
            * fps
        )

        end_frame = round(
            end_real
            * fps
        )

        if (
            end_frame
            <= start_frame
        ):

            end_frame = (
                start_frame
                + 1
            )

        duracion_render = (
            end_frame
            - start_frame
        ) / float(
            fps
        )

        escena[
            "scene"
        ] = index

        escena[
            "start"
        ] = start_real

        escena[
            "end"
        ] = end_real

        escena[
            "timeline_duration"
        ] = (
            end_real
            - start_real
        )

        escena[
            "duration"
        ] = duracion_render

        escena[
            "width"
        ] = width

        escena[
            "height"
        ] = height

        escena[
            "fps"
        ] = fps

        escena[
            "narration"
        ] = bloque[
            "text"
        ]

        for efecto in escena.get(
            "sound_effects",
            [],
        ):

            limite = max(
                0.0,
                duracion_render
                - 0.05,
            )

            try:

                tiempo = float(
                    efecto.get(
                        "time",
                        0.0,
                    )
                )

            except (
                TypeError,
                ValueError,
            ):

                tiempo = 0.0

            efecto[
                "time"
            ] = max(
                0.0,
                min(
                    tiempo,
                    limite,
                ),
            )

        for personaje in escena.get(
            "characters",
            [],
        ):

            movement = (
                personaje.get(
                    "movement"
                )
            )

            if isinstance(
                movement,
                dict,
            ):

                movement[
                    "type"
                ] = "linear"

                try:

                    movement[
                        "start"
                    ] = float(
                        movement.get(
                            "start",
                            0,
                        )
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    movement[
                        "start"
                    ] = 0.0

                movement[
                    "duration"
                ] = (
                    duracion_render
                )

                movement[
                    "easing"
                ] = movement.get(
                    "easing",
                    "smooth",
                )

        for obj in escena.get(
            "objects",
            [],
        ):

            movement = obj.get(
                "movement"
            )

            if isinstance(
                movement,
                dict,
            ):

                try:

                    movement[
                        "start"
                    ] = float(
                        movement.get(
                            "start",
                            0,
                        )
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    movement[
                        "start"
                    ] = 0.0

                movement[
                    "duration"
                ] = (
                    duracion_render
                )

                movement[
                    "easing"
                ] = movement.get(
                    "easing",
                    "smooth",
                )

    data = {
        "storyboard": escenas,

        "cast": list(
            cast.values()
        ),

        "sync_mode": (
            "whisper"
            if usando_whisper
            else "duration"
        ),

        "audio_duration": float(
            duracion_segundos
        ),

        "llm_provider": (
            "openai"
        ),

        "llm_model": (
            OLLAMA_MODEL
        ),

        "batch_size": (
            ESCENAS_POR_LOTE
        ),
    }

    print(
        "[STICK] Storyboard generado "
        "correctamente: "
        f"{len(escenas)} escenas."
    )

    print(
        "[STICK] Emojis/objetos: "
        f"{sum(len(e.get('objects', [])) for e in escenas)}"
    )

    print(
        "[SFX] Efectos seleccionados: "
        f"{sum(len(e.get('sound_effects', [])) for e in escenas)}"
    )

    print(
        "[CAST] Identidades persistentes: "
        f"{len(cast)}"
    )

    return data
