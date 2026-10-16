from pathlib import Path
from difflib import SequenceMatcher
import re

from ollama_client import OLLAMA_MODEL, ollama_chat

import os
import requests
import base64
import json
import math
import time


# =========================
# CONFIGURACION
# =========================

SD_API_URL = (
    "http://127.0.0.1:7860"
    "/sdapi/v1/txt2img"
)

SD_OPTIONS_URL = (
    "http://127.0.0.1:7860"
    "/sdapi/v1/options"
)

SEGUNDOS_POR_IMAGEN = 7

STEPS = 25
CFG_SCALE = 7
SAMPLER = "DPM++ 2M Karras"



# =========================
# DEFAULTS NEUTROS
# =========================

ESTILO_DEFAULT = """
digital illustration,
cinematic composition,
detailed artwork,
clean lighting,
balanced composition,
atmospheric scene,
high visual clarity,
highly detailed,
illustrated,
not photorealistic
"""

PALETA_DEFAULT = """
neutral cinematic colors
"""

NEGATIVE_PROMPT_DEFAULT = """
blurry,
low quality,
bad anatomy,
bad hands,
extra fingers,
extra limbs,
deformed,
duplicate people,
text,
letters,
watermark,
logo,
photorealistic,
photo,
3d render,
oversaturated,
low detail
"""


# =========================
# LEER GUION
# =========================

def leer_guion(
    ruta_guion: Path
) -> str:

    print(
        f"[IMAGENES] Leyendo guion: "
        f"{ruta_guion}"
    )

    if not ruta_guion.exists():

        raise FileNotFoundError(
            "[IMAGENES] ERROR: "
            "No existe el guion."
        )

    texto = ruta_guion.read_text(
        encoding="utf-8"
    ).strip()

    if not texto:

        raise ValueError(
            "[IMAGENES] ERROR: "
            "El guion está vacío."
        )

    return texto


# =========================
# CONFIG
# =========================

def cargar_config(
    ruta_config
) -> dict:

    config = {
        "estilo_visual": None,
        "paleta": None,
        "seed": None,
        "negative_prompt": None,
        "resolucion": "1080x1920",
        "personajes": {}
    }

    if ruta_config is None:
        return config

    ruta_config = Path(
        ruta_config
    )

    if not ruta_config.exists():
        return config

    datos = json.loads(
        ruta_config.read_text(
            encoding="utf-8"
        )
    )

    for clave in config:
        if clave in datos:
            config[clave] = datos[clave]

    return config


# =========================
# RESOLUCION
# =========================

def calcular_resolucion_sd(
    resolucion: str
) -> tuple[int, int]:

    ancho, alto = map(
        int,
        resolucion.lower().split("x")
    )

    if alto > ancho:
        return (
            576,
            1024
        )

    if ancho > alto:
        return (
            1024,
            576
        )

    return (
        768,
        768
    )


# =========================
# CANTIDAD IMAGENES
# =========================

def calcular_cantidad_imagenes(
    duracion_segundos: float
) -> int:

    return max(
        1,
        math.ceil(
            duracion_segundos
            / SEGUNDOS_POR_IMAGEN
        )
    )


# =========================
# PERSONAJES
# =========================

def construir_personajes(
    personajes: dict
) -> str:

    if not personajes:
        return (
            "No predefined characters."
        )

    resultado = []

    for nombre, descripcion in (
        personajes.items()
    ):
        resultado.append(
            f"{nombre}: {descripcion}"
        )

    return "\n".join(
        resultado
    )


# =========================
# PROMPT STORYBOARD
# =========================

def construir_prompt_storyboard(
    guion: str,
    cantidad: int,
    config: dict
) -> str:

    estilo = (
        config["estilo_visual"]
        or ESTILO_DEFAULT
    )

    paleta = (
        config["paleta"]
        or PALETA_DEFAULT
    )

    personajes = construir_personajes(
        config["personajes"]
    )

    return f"""
You are a professional storyboard artist
and visual director.

Analyze the ENTIRE narration before creating
the scenes.

Create exactly {cantidad} consecutive scenes.

All scenes must form one coherent visual story.
Every scene must depict a distinct moment, action, or camera composition. Never repeat a scene.

Generate ALL scenes in this single response.

==================================================
GLOBAL VISUAL STYLE
==================================================

{estilo}

COLOR PALETTE:

{paleta}

Maintain the same visual language throughout
the entire storyboard.

==================================================
CHARACTERS
==================================================

{personajes}

If a predefined character appears,
preserve exactly:

- approximate age
- gender
- hair
- clothing
- accessories
- face characteristics
- overall visual design

IMPORTANT:

A character does NOT need to appear
in every scene. If a character returns, preserve the same identity and visual design exactly; do not create a second version of that character.

For each predefined character, use the configured name consistently in the
description and prompt. Whenever that character appears, repeat the same
distinctive visual traits from its definition; never change its clothing,
colors, age, hair, face, or accessories.

Do NOT force characters into scenes
where they are not narratively necessary.

==================================================
ENVIRONMENT-FIRST RULE
==================================================

Do NOT create mostly portraits.

If the narration describes:

- a building
- a room
- a landscape
- an object
- a painting
- a machine
- a vehicle
- architecture
- a city
- a technological device
- an environmental event

then the image should primarily show THAT subject.

Do not automatically add a person.

At least 60 percent of the storyboard should
primarily focus on non-character subjects such as:

- environments
- architecture
- objects
- landscapes
- rooms
- paintings
- machines
- important details

Character-focused scenes should be used only
when they are necessary to tell the story.

==================================================
PORTRAIT RESTRICTION
==================================================

Avoid portrait compositions unless:

- the narration focuses on a face
- an emotional reaction is important
- the identity of the character is narratively important

Do NOT make a close-up portrait simply because
a character is mentioned.

Do NOT repeatedly place a character in the center
looking toward the camera.

==================================================
CONTINUITY
==================================================

Maintain continuity between scenes.

Keep consistent:

- architecture
- locations
- character appearance
- clothing
- technology
- vehicles
- recurring objects
- time of day
- atmosphere

If consecutive scenes occur in the same location,
the location should remain recognizable.

==================================================
ANTI-REPETITION
==================================================

Every scene must provide NEW visual information.

Do not create multiple images with:

- the same person in the same pose
- the same centered composition
- the same camera distance
- the same background
- the same facial expression
- the same visual focus

==================================================
HARD ANTI-REPETITION RULES
==================================================

Do NOT repeat the same main subject in consecutive scenes.

Do NOT show the same woman, man, character, face,
portrait, or person as the primary subject in more
than 2 consecutive scenes.

If a character has already been the main subject
of 2 consecutive scenes, the next scene MUST focus
on something different, such as:

- environment
- architecture
- object
- room
- landscape
- painting
- hands
- tools
- lighting
- symbolic detail
- vehicle
- machine
- exterior location

Do NOT generate filler portraits.

Do NOT turn descriptive narration into portraits.

If the narration describes a location or object,
the character should NOT appear unless absolutely
necessary.

Avoid centered portraits.

Avoid repeated close-ups of the same face.

Avoid repeated images of a woman simply posing,
looking at the camera, sitting, or standing.

Every new scene must introduce at least one clearly
different visual element compared with the previous scene.

For every block of 5 scenes, no more than 2 scenes
may have a human face as the main visual subject.

Before returning the JSON, compare every scene with
the previous 2 scenes.

If the same main subject appears too often,
rewrite that scene using another visual subject
that is supported by the narration.

==================================================
STRICT SOURCE FIDELITY
==================================================

Do not invent locations, objects, events or situations
that are not supported by the narration.

Do not create generic filler scenes just to reach
the required number of images.

When several consecutive passages focus on the same
character, vary the visual subject by showing relevant
objects, environment, hands, tools, architecture,
lighting, or the consequences of the action.

Avoid showing the same character as the primary subject
in more than two consecutive scenes.

All Stable Diffusion prompts must be written entirely
in English. Never use Spanish words inside the prompts.

==================================================
CAMERA VARIETY
==================================================

Use different camera approaches when appropriate:

- wide establishing shot
- very wide shot
- medium shot
- close-up
- extreme close-up
- object detail
- environmental detail
- overhead shot
- low-angle shot
- high-angle shot
- over-the-shoulder shot
- silhouette composition

Do not follow a fixed repeating pattern.

Choose the camera based on what the narration
is describing.

==================================================
VISUAL STORYTELLING
==================================================

Prefer visual storytelling over portraits.

Example:

Narration mentions an abandoned mansion.

GOOD:
wide exterior view of the mansion.

BAD:
portrait of a woman standing in front
of the mansion.

Narration mentions an old painting.

GOOD:
detailed composition centered on the painting.

BAD:
random portrait of the woman depicted
in the painting.

Narration mentions a mysterious machine.

GOOD:
close detailed view of the machine.

BAD:
portrait of a character standing next to it.

==================================================
SCENE DISTRIBUTION
==================================================

Cover the complete narration.

Do not spend too many scenes on the beginning.

Do not rush the ending.

Important narrative reveals should receive
distinct visual scenes.

==================================================
STABLE DIFFUSION PROMPTS
==================================================

Every prompt must be written in English.

Each prompt must describe ONE still image.

Clearly describe:

- primary visual subject
- environment
- action if relevant
- camera shot
- camera angle if useful
- lighting
- atmosphere
- important objects

Do not include:

- subtitles
- text
- logos
- watermarks
- animation instructions

==================================================
OUTPUT
==================================================

Return ONLY valid JSON.

Do not use Markdown.

Do not use code fences.

Format:

{{
  "storyboard": [
    {{
      "scene": 1,
      "shot": "wide establishing shot",
      "description": "brief description",
      "prompt": "Stable Diffusion prompt in English"
    }},
    {{
      "scene": 2,
      "shot": "object detail",
      "description": "brief description",
      "prompt": "Stable Diffusion prompt in English"
    }}
  ]
}}

The storyboard array MUST contain exactly
{cantidad} scenes.

==================================================
FULL NARRATION
==================================================

{guion}
"""


# =========================
# LIMPIAR RESPUESTA JSON
# =========================

def limpiar_json_respuesta(
    contenido: str
) -> str:

    contenido = contenido.strip()

    if contenido.startswith("```json"):
        contenido = contenido[len("```json"):]

    contenido = contenido.replace(
        "```",
        ""
    ).strip()

    inicio = contenido.find("{")
    fin = contenido.rfind("}")

    if inicio == -1 or fin == -1:
        return contenido

    return contenido[
        inicio:fin + 1
    ]


# =========================
# OLLAMA Y ESCENAS UNICAS
# =========================

def _texto_visual_escena(escena: dict) -> str:
    partes = [
        escena.get("description", ""),
        escena.get("shot", ""),
        escena.get("prompt", ""),
    ]
    return " ".join(str(parte or "") for parte in partes).lower()


def _escenas_repetidas(escenas: list[dict]) -> list[tuple[int, int]]:
    stopwords = {
        "the", "and", "with", "from", "into", "over", "under", "scene",
        "cinematic", "illustration", "illustrated", "detailed", "lighting",
        "composition", "professional", "digital", "artwork", "consistent",
        "style", "of", "a", "an", "in", "on", "at", "to", "for",
    }
    tokens = []
    for escena in escenas:
        words = set(re.findall(r"[a-z0-9áéíóúñ]+", _texto_visual_escena(escena)))
        tokens.append(words - stopwords)

    repetidas = []
    for i in range(len(escenas)):
        for j in range(i + 1, len(escenas)):
            a, b = tokens[i], tokens[j]
            union = a | b
            similitud_tokens = len(a & b) / len(union) if union else 1.0
            texto_a = " ".join(sorted(a))
            texto_b = " ".join(sorted(b))
            similitud_texto = SequenceMatcher(None, texto_a, texto_b).ratio()
            if similitud_tokens >= 0.82 or similitud_texto >= 0.90:
                repetidas.append((i + 1, j + 1))
    return repetidas


def generar_storyboard(
    guion: str,
    cantidad: int,
    config: dict
) -> list[dict]:
    print("\n========================================")
    print("[IMAGENES] GENERANDO STORYBOARD CON OLLAMA")
    print("========================================")
    print(f"[IMAGENES] Escenas solicitadas: {cantidad}")
    print(f"[IMAGENES] Modelo local: {OLLAMA_MODEL}")

    prompt_base = construir_prompt_storyboard(
        guion=guion,
        cantidad=cantidad,
        config=config
    )
    prompt_actual = prompt_base
    ultimo_error = None

    for intento in range(1, 4):
        try:
            print(f"[IMAGENES] Intento {intento}/3...")
            contenido = ollama_chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "Eres director visual. Devuelve solo el JSON solicitado. "
                            "Cada escena debe mostrar un momento visual distinto."
                        ),
                    },
                    {"role": "user", "content": prompt_actual},
                ],
                json_mode=True,
                temperature=0.25,
                num_predict=8000,
            )
            datos = json.loads(limpiar_json_respuesta(contenido))
            storyboard = datos.get("storyboard", [])
            if not isinstance(storyboard, list):
                raise RuntimeError("storyboard no es una lista.")
            if len(storyboard) != cantidad:
                raise RuntimeError(
                    f"Esperados {cantidad} escenas, recibidas {len(storyboard)}."
                )

            resultado = []
            for indice, escena in enumerate(storyboard, start=1):
                if not isinstance(escena, dict):
                    raise RuntimeError(f"Escena {indice} inválida.")
                prompt = str(escena.get("prompt", "")).strip()
                if not prompt:
                    raise RuntimeError(f"Escena {indice} sin prompt.")
                resultado.append({
                    "scene": indice,
                    "shot": str(escena.get("shot", "cinematic shot")).strip(),
                    "description": str(escena.get("description", "")).strip(),
                    "prompt": prompt,
                })

            duplicadas = _escenas_repetidas(resultado)
            if duplicadas:
                pares = ", ".join(f"{a} y {b}" for a, b in duplicadas)
                print(f"[IMAGENES] Escenas repetidas: {pares}; se regenerará el storyboard.")
                prompt_actual = (
                    prompt_base
                    + "\n\nREVISIÓN OBLIGATORIA: la respuesta anterior repitió las escenas "
                    + pares
                    + ". Cambia cada escena repetida por un momento, encuadre y acción "
                    "visualmente distintos. No reutilices la misma composición ni descripción."
                )
                ultimo_error = RuntimeError(f"Escenas repetidas: {pares}")
                continue

            print(f"[IMAGENES] Storyboard validado: {len(resultado)} escenas únicas.")
            return resultado
        except Exception as exc:
            ultimo_error = exc
            print(f"[IMAGENES] Error en intento {intento}: {exc}")

    raise RuntimeError(
        f"[IMAGENES] Ollama no generó un storyboard válido y sin repeticiones: {ultimo_error}"
    )

# =========================
# PROMPT FINAL
# =========================

def construir_prompt_final(
    escena: dict,
    config: dict
) -> str:

    estilo = (
        config["estilo_visual"]
        or ESTILO_DEFAULT
    )

    paleta = (
        config["paleta"]
        or PALETA_DEFAULT
    )

    partes = [
        escena["prompt"],
        estilo,
        f"color palette: {paleta}",
        "consistent visual style",
        "consistent environment design",
        "professional digital illustration",
        "highly detailed illustration"
    ]

    return ", ".join(
        parte.strip()
        for parte in partes
        if parte
    )


# =========================
# NEGATIVE PROMPT
# =========================

def construir_negative_prompt(
    config: dict
) -> str:

    partes = [
        NEGATIVE_PROMPT_DEFAULT
    ]

    if config["negative_prompt"]:
        partes.append(
            config["negative_prompt"]
        )

    return ", ".join(
        partes
    )


# =========================
# STABLE DIFFUSION
# =========================

def comprobar_stable_diffusion():

    print(
        "[IMAGENES] Comprobando "
        "Stable Diffusion..."
    )

    try:
        response = requests.get(
            SD_OPTIONS_URL,
            timeout=10
        )
        response.raise_for_status()

    except Exception as e:
        raise RuntimeError(
            "[IMAGENES] AUTOMATIC1111 "
            f"no disponible: {e}"
        )

    print(
        "[IMAGENES] Stable Diffusion disponible."
    )


# =========================
# GENERAR IMAGEN
# =========================

def generar_imagen(
    escena: dict,
    ruta_salida: Path,
    numero: int,
    total: int,
    config: dict,
    width: int,
    height: int
):

    print("")
    print(
        f"[IMAGENES] Imagen "
        f"{numero}/{total}"
    )
    print(
        f"[IMAGENES] Plano: "
        f"{escena.get('shot')}"
    )
    print(
        f"[IMAGENES] Escena: "
        f"{escena.get('description')}"
    )

    prompt_final = (
        construir_prompt_final(
            escena,
            config
        )
    )

    negative_prompt = (
        construir_negative_prompt(
            config
        )
    )

    seed_base = config["seed"]

    if seed_base is not None:
        seed = seed_base + numero
    else:
        seed = -1

    print(
        f"[IMAGENES] Seed: "
        f"{seed}"
    )

    payload = {
        "prompt":
            prompt_final,

        "negative_prompt":
            negative_prompt,

        "steps":
            STEPS,

        "cfg_scale":
            CFG_SCALE,

        "width":
            width,

        "height":
            height,

        "sampler_name":
            SAMPLER,

        "seed":
            seed,

        "batch_size":
            1,

        "n_iter":
            1
    }

    inicio = time.time()

    response = requests.post(
        SD_API_URL,
        json=payload,
        timeout=600
    )

    response.raise_for_status()

    resultado = response.json()

    imagenes = resultado.get(
        "images"
    )

    if not imagenes:
        raise RuntimeError(
            "[IMAGENES] Stable Diffusion "
            "no devolvió imagen."
        )

    imagen_base64 = imagenes[0]

    if "," in imagen_base64:
        imagen_base64 = imagen_base64.split(
            ",",
            1
        )[1]

    ruta_salida.write_bytes(
        base64.b64decode(
            imagen_base64
        )
    )

    print(
        f"[IMAGENES] Guardada: "
        f"{ruta_salida.name}"
    )
    print(
        f"[IMAGENES] Tiempo: "
        f"{time.time() - inicio:.1f}s"
    )


# =========================
# PRINCIPAL
# =========================

def generar_imagenes(
    ruta_guion,
    duracion_segundos,
    carpeta_imagenes,
    ruta_config=None
):

    print("")
    print("========================================")
    print("[IMAGENES] INICIANDO")
    print("========================================")

    ruta_guion = Path(
        ruta_guion
    )

    carpeta_imagenes = Path(
        carpeta_imagenes
    )

    carpeta_imagenes.mkdir(
        parents=True,
        exist_ok=True
    )

    if duracion_segundos <= 0:
        raise ValueError(
            "[IMAGENES] Duración inválida."
        )

    guion = leer_guion(
        ruta_guion
    )

    config = cargar_config(
        ruta_config
    )

    width, height = (
        calcular_resolucion_sd(
            config["resolucion"]
        )
    )

    cantidad = (
        calcular_cantidad_imagenes(
            duracion_segundos
        )
    )

    print(
        f"[IMAGENES] Duración: "
        f"{duracion_segundos:.2f}s"
    )
    print(
        f"[IMAGENES] Imágenes: "
        f"{cantidad}"
    )
    print(
        f"[IMAGENES] Resolución SD: "
        f"{width}x{height}"
    )

    storyboard = generar_storyboard(
        guion=guion,
        cantidad=cantidad,
        config=config
    )

    storyboard_guardado = []

    for escena in storyboard:

        seed_base = config["seed"]

        if seed_base is not None:
            seed_escena = (
                seed_base
                + escena["scene"]
            )
        else:
            seed_escena = -1

        storyboard_guardado.append({
            "scene":
                escena["scene"],

            "shot":
                escena["shot"],

            "description":
                escena["description"],

            "prompt":
                escena["prompt"],

            "prompt_final":
                construir_prompt_final(
                    escena,
                    config
                ),

            "seed":
                seed_escena
        })

    ruta_storyboard = (
        carpeta_imagenes.parent
        / "storyboard.json"
    )

    ruta_storyboard.write_text(
        json.dumps(
            storyboard_guardado,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    ruta_prompts = (
        carpeta_imagenes.parent
        / "prompts_imagenes.json"
    )

    ruta_prompts.write_text(
        json.dumps(
            storyboard_guardado,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        f"[IMAGENES] Storyboard: "
        f"{ruta_storyboard}"
    )

    comprobar_stable_diffusion()

    inicio = time.time()

    for escena in storyboard:

        numero = escena["scene"]

        ruta_salida = (
            carpeta_imagenes
            / f"{numero:03d}.png"
        )

        generar_imagen(
            escena=escena,
            ruta_salida=ruta_salida,
            numero=numero,
            total=cantidad,
            config=config,
            width=width,
            height=height
        )

    print("")
    print("========================================")
    print("[IMAGENES] COMPLETADO")
    print("========================================")
    print(
        f"[IMAGENES] Total: "
        f"{cantidad}"
    )
    print(
        f"[IMAGENES] Tiempo: "
        f"{(time.time() - inicio) / 60:.2f} min"
    )

    return carpeta_imagenes
