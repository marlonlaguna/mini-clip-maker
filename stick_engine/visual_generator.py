import base64
import hashlib
import subprocess
import time
from pathlib import Path

import requests


SD_BASE_URL = "http://127.0.0.1:7860"
SD_OPTIONS_URL = f"{SD_BASE_URL}/sdapi/v1/options"
SD_TXT2IMG_URL = f"{SD_BASE_URL}/sdapi/v1/txt2img"


# ============================================================
# ESTILO PARA ILUSTRACIONES COMPLETAS
# ============================================================

SIMPLE_STYLE = (
    "realistic cinematic illustration, faceless human silhouettes, no facial details, "
    "true crime investigation style, restrained suspense, realistic environments, "
    "documentary-like framing, moody natural lighting, believable anatomy, "
    "simple but dramatic composition, serious and intriguing tone, no gore, no text"
)


# ============================================================
# ESTILO EXCLUSIVO PARA FONDOS DE ESCENAS STICK
# ============================================================

BACKGROUND_STYLE = (
    "simple illustrated background, clean digital illustration, "
    "stylized environment, simple shapes, soft natural colors, "
    "clean readable composition, slightly cinematic, subtle mystery, "
    "environment only, empty scene, no text"
)


# ============================================================
# NEGATIVE PROMPT GENERAL
# ============================================================

DEFAULT_NEGATIVE = (
    "visible face, detailed face, eyes, nose, mouth, facial features, portrait close-up, "
    "cartoon character, anime, chibi, childish character, exaggerated expressions, "
    "horror gore, blood splatter, monster, demon, text, letters, watermark, logo, "
    "blurry, distorted, deformed anatomy"
)


# ============================================================
# NEGATIVE PROMPT EXCLUSIVO PARA FONDOS
# ============================================================

BACKGROUND_NEGATIVE = (
    "people, person, human, humans, man, woman, child, children, baby, crowd, "
    "human silhouette, human figure, person silhouette, character, characters, "
    "stickman, stick figure, face, faces, body, bodies, arms, legs, hands, portrait, "
    "animal character, foreground subject"
)


class VisualGenerator:
    """
    Genera fondos e ilustraciones usando AUTOMATIC1111.

    Reglas:
    - Fondo para escena stick:
      solo escenario ilustrado, SIN humanos ni personajes.
    - Ilustración completa:
      puede representar personas como siluetas sin rostro.
    """

    def __init__(
        self,
        estilo_visual="",
        negative_prompt="",
        seed=None,
    ):
        self.estilo_visual = str(
            estilo_visual or ""
        ).strip()

        self.negative_prompt = str(
            negative_prompt or ""
        ).strip()

        self.seed = seed
        self._comprobado = False

    # ============================================================
    # COMPROBAR STABLE DIFFUSION
    # ============================================================

    def comprobar(self):
        if self._comprobado:
            return

        print("[MIXED] Comprobando Stable Diffusion...")

        try:
            response = requests.get(
                SD_OPTIONS_URL,
                timeout=10,
            )
            response.raise_for_status()

        except Exception as exc:
            raise RuntimeError(
                "[MIXED] AUTOMATIC1111 no disponible: "
                f"{exc}"
            ) from exc

        self._comprobado = True

        print("[MIXED] Stable Diffusion disponible.")

    # ============================================================
    # RESOLUCIÓN
    # ============================================================

    @staticmethod
    def _sd_resolution(
        width,
        height,
    ):
        if height > width:
            return 576, 1024

        if width > height:
            return 1024, 576

        return 768, 768

    # ============================================================
    # SEED
    # ============================================================

    def _seed_for(
        self,
        key,
    ):
        if self.seed is None:
            return -1

        digest = hashlib.sha1(
            str(key).encode("utf-8")
        ).hexdigest()

        offset = int(
            digest[:8],
            16,
        ) % 100000

        return int(self.seed) + offset

    # ============================================================
    # PROMPT
    # ============================================================

    def _prompt(
        self,
        prompt,
        background=False,
    ):
        partes = []

        if background:
            # Para fondos stick NO usamos el estilo del guion si ese estilo
            # puede inducir a dibujar personas.
            partes.append(BACKGROUND_STYLE)

            partes.append(
                "BACKGROUND ONLY, ENVIRONMENT ONLY, EMPTY LOCATION, "
                "NO PEOPLE, NO HUMANS, NO HUMAN SILHOUETTES, NO CHARACTERS, "
                "NO HUMAN FIGURES, NO FACES, NO BODIES, "
                "no foreground person, no subject standing in the scene, "
                "leave clear open space in the lower and middle area "
                "for animated stick characters"
            )

        else:
            # Para ilustraciones completas sí respetamos el estilo configurado
            # en el guion, además del estilo base.
            if self.estilo_visual:
                partes.append(
                    self.estilo_visual
                )

            partes.append(
                SIMPLE_STYLE
            )

        partes.append(
            str(
                prompt or ""
            ).strip()
        )

        return ", ".join(
            parte
            for parte in partes
            if parte
        )

    # ============================================================
    # NEGATIVE PROMPT
    # ============================================================

    def _negative(
        self,
        background=False,
    ):
        partes = [
            DEFAULT_NEGATIVE
        ]

        if background:
            partes.append(
                BACKGROUND_NEGATIVE
            )

        if self.negative_prompt:
            partes.append(
                self.negative_prompt
            )

        return ", ".join(
            parte
            for parte in partes
            if parte
        )

    # ============================================================
    # GENERAR PNG
    # ============================================================

    def _generar_png(
        self,
        prompt,
        ruta_salida,
        width,
        height,
        key,
        background=False,
    ):
        self.comprobar()

        ruta_salida = Path(
            ruta_salida
        )

        ruta_salida.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        sd_width, sd_height = (
            self._sd_resolution(
                width,
                height,
            )
        )

        prompt_final = self._prompt(
            prompt,
            background=background,
        )

        negative_final = self._negative(
            background=background,
        )

        if background:
            print("[MIXED] Tipo visual: FONDO ILUSTRADO SIN HUMANOS")
        else:
            print("[MIXED] Tipo visual: ILUSTRACIÓN COMPLETA")

        print(
            "[MIXED] Prompt visual:"
        )
        print(
            prompt_final
        )

        payload = {
            "prompt": prompt_final,
            "negative_prompt": negative_final,
            "steps": 26,
            "cfg_scale": 6.5,
            "width": sd_width,
            "height": sd_height,
            "sampler_name": "DPM++ 2M Karras",
            "seed": self._seed_for(
                key
            ),
            "batch_size": 1,
            "n_iter": 1,
        }

        inicio = time.time()

        response = requests.post(
            SD_TXT2IMG_URL,
            json=payload,
            timeout=600,
        )

        response.raise_for_status()

        data = response.json()

        imagenes = (
            data.get(
                "images"
            )
            or
            []
        )

        if not imagenes:
            raise RuntimeError(
                "[MIXED] Stable Diffusion no devolvió imagen."
            )

        raw = imagenes[0]

        if "," in raw:
            raw = raw.split(
                ",",
                1,
            )[1]

        ruta_salida.write_bytes(
            base64.b64decode(
                raw
            )
        )

        print(
            f"[MIXED] Imagen generada: "
            f"{ruta_salida.name} "
            f"({time.time() - inicio:.1f}s)"
        )

        return ruta_salida

    # ============================================================
    # FONDO PARA STICK
    # ============================================================

    def generar_fondo(
        self,
        prompt,
        ruta_salida,
        width,
        height,
        scene_number,
    ):
        print(
            f"[MIXED] Generando fondo automático "
            f"para escena {scene_number}..."
        )

        return self._generar_png(
            prompt=prompt,
            ruta_salida=ruta_salida,
            width=width,
            height=height,
            key=(
                f"background-"
                f"{scene_number}-"
                f"{prompt}"
            ),
            background=True,
        )

    # ============================================================
    # ILUSTRACIÓN COMPLETA
    # ============================================================

    def generar_ilustracion(
        self,
        prompt,
        ruta_salida,
        width,
        height,
        scene_number,
    ):
        print(
            f"[MIXED] Generando ilustración completa "
            f"para escena {scene_number}..."
        )

        return self._generar_png(
            prompt=prompt,
            ruta_salida=ruta_salida,
            width=width,
            height=height,
            key=(
                f"illustration-"
                f"{scene_number}-"
                f"{prompt}"
            ),
            background=False,
        )


# ============================================================
# FFMPEG
# ============================================================

def _run_ffmpeg(
    command,
):
    result = subprocess.run(
        [
            str(x)
            for x in command
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr
        )


# ============================================================
# CONVERTIR IMAGEN A CLIP
# ============================================================

def imagen_a_clip(
    ruta_imagen,
    ruta_salida,
    duration,
    width,
    height,
    fps,
):
    """
    Convierte una ilustración completa en un clip
    con un zoom cinematográfico suave.
    """

    ruta_imagen = Path(
        ruta_imagen
    )

    ruta_salida = Path(
        ruta_salida
    )

    ruta_salida.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    frames = max(
        1,
        round(
            float(duration)
            *
            int(fps)
        ),
    )

    filtro = (
        f"scale={int(width)}:{int(height)}:"
        f"force_original_aspect_ratio=increase,"
        f"crop={int(width)}:{int(height)},"
        f"zoompan="
        f"z='min(zoom+0.0007,1.04)':"
        f"x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':"
        f"d={frames}:"
        f"s={int(width)}x{int(height)}:"
        f"fps={int(fps)},"
        "format=yuv420p"
    )

    base = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        ruta_imagen,
        "-vf",
        filtro,
        "-frames:v",
        str(frames),
        "-an",
    ]

    nvenc = (
        base
        +
        [
            "-c:v",
            "h264_nvenc",
            "-preset",
            "p1",
            "-pix_fmt",
            "yuv420p",
            ruta_salida,
        ]
    )

    try:
        _run_ffmpeg(
            nvenc
        )

    except Exception:
        print(
            "[MIXED] NVENC falló. "
            "Usando libx264."
        )

        cpu = (
            base
            +
            [
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                ruta_salida,
            ]
        )

        _run_ffmpeg(
            cpu
        )

    return ruta_salida
