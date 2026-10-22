import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .assets import AssetLibrary
from .animation import actor_layout, resolve_facings, sprite_focus_bounds, sprite_sheet_scale
from .utils import parse_color, clamp, smoothstep
from .shots import normalize_shot, prepare_closeup, closeup_sample, portrait_layout, speech_sample


# ============================================================
# RENDER INTERNO
# ============================================================
#
# El video final conserva la resolución pedida por Mini Clip Maker
# (por ejemplo 1080x1920), pero Pillow trabaja internamente al 50%.
# Esto reduce el frame de 2,073,600 píxeles a 518,400 píxeles.
#
# Puedes bajar a 0.40 o 0.35 si quieres todavía más velocidad.
# 0.50 es un buen punto de partida.
# ============================================================

INTERNAL_RENDER_SCALE = 0.35


class StickRenderer:

    def __init__(self):
        self.assets = AssetLibrary()

        self.emoji_font_candidates = [
            Path(r"C:\Windows\Fonts\seguiemj.ttf"),
            Path(r"C:\Windows\Fonts\segoeuiemoji.ttf"),
            Path(r"C:\Windows\Fonts\arial.ttf"),
        ]

        self._emoji_font_cache = {}
        self._tint_cache = {}
        self._encoder_cache = None

    # ============================================================
    # RENDER PRINCIPAL
    # ============================================================

    def render(
        self,
        scene,
        output_path
    ):
        output_width = int(
            scene.get(
                "width",
                1080
            )
        )

        output_height = int(
            scene.get(
                "height",
                1920
            )
        )

        duration = float(
            scene.get(
                "duration",
                5.0
            )
        )

        fps = int(
            scene.get(
                "fps",
                20
            )
        )

        if output_width <= 0:
            raise ValueError(
                "width debe ser mayor a 0"
            )

        if output_height <= 0:
            raise ValueError(
                "height debe ser mayor a 0"
            )

        if duration <= 0:
            raise ValueError(
                "duration debe ser mayor a 0"
            )

        if fps <= 0:
            raise ValueError(
                "fps debe ser mayor a 0"
            )

        # --------------------------------------------------------
        # RESOLUCIÓN INTERNA
        # --------------------------------------------------------

        # En un detalle se conserva resolución nativa para no degradar dos
        # veces los 200 px del sprite antes de ampliar el rostro.
        render_scale = 1.0 if normalize_shot(scene.get("shot"))["target"] != "full_body" else INTERNAL_RENDER_SCALE
        width = self._even(
            max(
                2,
                int(
                    output_width
                    * render_scale
                )
            )
        )

        height = self._even(
            max(
                2,
                int(
                    output_height
                    * render_scale
                )
            )
        )

        # --------------------------------------------------------
        # PERSONAJES
        # --------------------------------------------------------

        characters = list(
            scene.get(
                "characters",
                []
            )
        )

        characters.sort(
            key=lambda c: int(
                c.get(
                    "position",
                    1
                )
            )
        )

        self._validate_positions(
            characters
        )
        characters = resolve_facings(characters)

        # --------------------------------------------------------
        # BACKGROUND
        # --------------------------------------------------------

        background = (
            self.assets
            .background(
                scene["background"]
            )
            .resize(
                (
                    width,
                    height
                ),
                Image.Resampling.LANCZOS
            )
        )

        count = len(
            characters
        )

        scale = self._auto_scale(
            count,
            width,
            height
        )

        slots = self._slot_centers(
            count,
            width
        )

        ground_y = int(
            height * 0.83
        )

        # --------------------------------------------------------
        # PREPARAR PERSONAJES
        # --------------------------------------------------------
        # Cargamos cada action una sola vez por personaje/escena.

        prepared_characters = []

        for index, spec in enumerate(
            characters
        ):
            char_type = spec.get(
                "type",
                "stickman"
            )

            action_name = spec.get(
                "action",
                "idle"
            )

            prepared_characters.append(
                {
                    "index": index,
                    "spec": spec,
                    "char_type": char_type,
                    "action_name": action_name,
                    "action": self.assets.action(
                        char_type,
                        action_name
                    ),
                    "color": parse_color(
                        spec.get(
                            "color",
                            "black"
                        )
                    ),
                }
            )

        shot = normalize_shot(scene.get("shot"))
        shot_character = shot["character"]
        if shot["target"] != "full_body" and not shot_character and prepared_characters:
            shot_character = prepared_characters[0]["spec"].get("id")
        closeup = prepare_closeup(self.assets, prepared_characters, shot, shot_character)

        # --------------------------------------------------------
        # OUTPUT
        # --------------------------------------------------------

        output_path = Path(
            output_path
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        encoder, preset = (
            self._video_encoder()
        )

        command = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",

            "-f",
            "rawvideo",

            "-pix_fmt",
            "rgba",

            "-s",
            f"{width}x{height}",

            "-r",
            str(fps),

            "-i",
            "-",

            "-an",

            # Pillow trabaja pequeño; FFmpeg escala al tamaño final.
            "-vf",
            (
                f"scale={output_width}:{output_height}:"
                "flags=bilinear"
            ),

            "-c:v",
            encoder,

            "-preset",
            preset,

            "-pix_fmt",
            "yuv420p",

            "-movflags",
            "+faststart",

            str(output_path),
        ]

        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )

        assert proc.stdin is not None

        try:
            total_frames = max(
                1,
                round(
                    duration
                    * fps
                )
            )

            # ====================================================
            # LOOP DE FRAMES
            # ====================================================

            for frame_index in range(
                total_frames
            ):
                t = (
                    frame_index
                    / fps
                )

                frame = background.copy()
                camera_focus = None
                portrait = closeup_sample(self.assets, closeup, t)

                # -----------------------------------------------
                # PERSONAJES
                # -----------------------------------------------

                for prepared in prepared_characters:
                    index, spec = prepared["index"], prepared["spec"]
                    char_type, action = prepared["char_type"], prepared["action"]
                    detail_shot = shot["target"] != "full_body" and spec.get("id") == shot_character
                    sample = speech_sample(self.assets, char_type, prepared["action_name"], spec, t)
                    frame_size = sample[0].size
                    x, y, aw, ah, actor_scale = actor_layout(
                        spec, action, t, width, height, duration, slots[index], ground_y, scale, frame_size,
                    )
                    actor, focus_bounds = self._render_character(
                        char_type, prepared["action_name"], prepared["color"], t, actor_scale,
                        action=action, facing=spec["facing"],
                        focus_parts=shot["target"] if detail_shot else None,
                        return_focus_bounds=True,
                        sample=sample,
                    )
                    x, y = round(x), round(y)
                    if detail_shot and focus_bounds:
                        left, top, right, bottom = focus_bounds
                        zoom = clamp(min(width * 0.78 / max(1, right-left), height * 0.58 / max(1, bottom-top)), 1, 5)
                        camera_focus = (x + (left+right)/2, y + (top+bottom)/2, zoom)
                    replaced = portrait is not None and prepared is closeup["target"]
                    if not replaced:
                        frame.alpha_composite(actor, (x, y))
                    if spec.get("emotion") and not replaced:
                        self._draw_emotion(
                            frame=frame, emotion_name=str(spec["emotion"]), actor_x=x, actor_y=y,
                            actor_width=actor.width, actor_scale=actor_scale, frame_width=width,
                        )

                # -----------------------------------------------
                # OBJETOS / EMOJIS
                # -----------------------------------------------

                for obj in scene.get(
                    "objects",
                    []
                ):
                    object_type = (
                        obj.get(
                            "type",
                            ""
                        )
                    ).lower()

                    if object_type == "emoji":
                        self._draw_emoji_object(
                            frame=frame,
                            obj=obj,
                            t=t,
                            width=width,
                            height=height,
                            scene_duration=duration
                        )

                if camera_focus:
                    center_x, center_y, zoom = camera_focus
                    crop_width = width / zoom
                    crop_height = height / zoom
                    center_x = clamp(
                        center_x,
                        crop_width / 2.0,
                        width - crop_width / 2.0,
                    )
                    center_y = clamp(
                        center_y,
                        crop_height / 2.0,
                        height - crop_height / 2.0,
                    )
                    frame = frame.crop((
                        center_x - crop_width / 2.0,
                        center_y - crop_height / 2.0,
                        center_x + crop_width / 2.0,
                        center_y + crop_height / 2.0,
                    )).resize(
                        (width, height),
                        Image.Resampling.LANCZOS,
                    )

                if portrait is not None:
                    image, _ = portrait
                    spec = closeup["target"]["spec"]
                    x, y, w, h = portrait_layout(image, width, height, spec.get("scale", 1))
                    image = image.resize((max(1, round(w)), max(1, round(h))), Image.Resampling.LANCZOS)
                    frame.alpha_composite(image, (round(x), round(y)))
                    if spec.get("emotion"):
                        self._draw_emotion(frame, str(spec["emotion"]), x, y, w, w / 454.0, width)

                proc.stdin.write(
                    frame.tobytes()
                )

            proc.stdin.close()

            stderr = (
                proc.stderr
                .read()
                .decode(
                    "utf-8",
                    errors="replace"
                )
            )

            code = proc.wait()

            if code != 0:
                raise RuntimeError(
                    "FFmpeg falló:\n"
                    + stderr
                )

        except Exception:
            if (
                proc.stdin
                and
                not proc.stdin.closed
            ):
                proc.stdin.close()

            proc.kill()
            proc.wait()
            raise

        return output_path

    # ============================================================
    # ENCODER
    # ============================================================

    def _video_encoder(self):
        if self._encoder_cache is not None:
            return self._encoder_cache

        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-encoders"
                ],
                capture_output=True,
                text=True,
                check=False
            )

            text = (
                result.stdout
                + result.stderr
            )

            if "h264_nvenc" in text:
                self._encoder_cache = (
                    "h264_nvenc",
                    "p1"
                )

                return self._encoder_cache

        except Exception:
            pass

        self._encoder_cache = (
            "libx264",
            "ultrafast"
        )

        return self._encoder_cache

    @staticmethod
    def _even(value):
        value = int(value)
        return value if value % 2 == 0 else value - 1

    # ============================================================
    # EMOJI
    # ============================================================

    def _emoji_font(
        self,
        size
    ):
        size = int(size)

        if size in self._emoji_font_cache:
            return self._emoji_font_cache[size]

        for path in self.emoji_font_candidates:
            if path.exists():
                try:
                    font = ImageFont.truetype(
                        str(path),
                        size
                    )

                    self._emoji_font_cache[size] = font
                    return font

                except Exception:
                    continue

        font = ImageFont.load_default()
        self._emoji_font_cache[size] = font

        return font

    def _draw_emoji_object(
        self,
        frame,
        obj,
        t,
        width,
        height,
        scene_duration
    ):
        value = str(
            obj.get(
                "value",
                "❓"
            )
        )

        x = float(
            obj.get(
                "x",
                0.5
            )
        )

        y = float(
            obj.get(
                "y",
                0.5
            )
        )

        requested_size = int(
            obj.get(
                "size",
                120
            )
        )

        size = max(
            12,
            int(
                requested_size
                * (
                    width
                    / 1080.0
                )
            )
        )

        movement = obj.get(
            "movement"
        )

        offset_x = 0.0
        offset_y = 0.0

        if movement:
            direction = (
                movement.get(
                    "direction",
                    "right"
                )
            ).lower()

            distance = float(
                movement.get(
                    "distance",
                    0.20
                )
            )

            start = float(
                movement.get(
                    "start",
                    0.0
                )
            )

            movement_duration = float(
                movement.get(
                    "duration",
                    scene_duration
                )
            )

            progress = clamp(
                (
                    t
                    - start
                )
                /
                max(
                    0.001,
                    movement_duration
                ),
                0.0,
                1.0
            )

            easing = (
                movement.get(
                    "easing",
                    "smooth"
                )
            ).lower()

            if easing == "smooth":
                progress = smoothstep(
                    progress
                )

            if direction == "right":
                offset_x = (
                    distance
                    * progress
                )

            elif direction == "left":
                offset_x = (
                    -distance
                    * progress
                )

            elif direction == "down":
                offset_y = (
                    distance
                    * progress
                )

            elif direction == "up":
                offset_y = (
                    -distance
                    * progress
                )

        final_x = clamp(
            x + offset_x,
            -0.20,
            1.20
        )

        final_y = clamp(
            y + offset_y,
            -0.20,
            1.20
        )

        px = int(
            final_x
            * width
        )

        py = int(
            final_y
            * height
        )

        font = self._emoji_font(
            size
        )

        draw = ImageDraw.Draw(
            frame
        )

        try:
            bbox = draw.textbbox(
                (
                    0,
                    0
                ),
                value,
                font=font,
                embedded_color=True
            )

            text_width = (
                bbox[2]
                - bbox[0]
            )

            text_height = (
                bbox[3]
                - bbox[1]
            )

            draw.text(
                (
                    px
                    - text_width / 2,
                    py
                    - text_height / 2
                ),
                value,
                font=font,
                embedded_color=True
            )

            return

        except Exception:
            pass

        try:
            bbox = draw.textbbox(
                (
                    0,
                    0
                ),
                value,
                font=font
            )

            text_width = (
                bbox[2]
                - bbox[0]
            )

            text_height = (
                bbox[3]
                - bbox[1]
            )

        except Exception:
            text_width = size
            text_height = size

        draw.text(
            (
                px
                - text_width / 2,
                py
                - text_height / 2
            ),
            value,
            font=font,
            fill=(
                255,
                255,
                255,
                255
            )
        )

    # ============================================================
    # EMOTION BUBBLE
    # ============================================================

    def _draw_emotion(
        self,
        frame,
        emotion_name,
        actor_x,
        actor_y,
        actor_width,
        actor_scale,
        frame_width
    ):
        bubble = self.assets.emotion(
            emotion_name
        )

        bubble_scale = clamp(
            actor_scale * 0.72,
            0.30,
            1.0
        )

        bubble = bubble.resize(
            (
                max(
                    1,
                    int(
                        bubble.width
                        * bubble_scale
                    )
                ),
                max(
                    1,
                    int(
                        bubble.height
                        * bubble_scale
                    )
                )
            ),
            Image.Resampling.LANCZOS
        )

        bubble_x = int(
            actor_x
            + actor_width / 2
            - bubble.width / 2
        )

        bubble_y = int(
            actor_y
            - bubble.height
            - 18 * actor_scale
        )

        bubble_x = int(
            clamp(
                bubble_x,
                8,
                max(
                    8,
                    frame_width
                    - bubble.width
                    - 8
                )
            )
        )

        bubble_y = max(
            8,
            bubble_y
        )

        frame.alpha_composite(
            bubble,
            (
                bubble_x,
                bubble_y
            )
        )

    # ============================================================
    # MOVIMIENTO PERSONAJES
    # ============================================================

    def _movement_x(
        self,
        movement,
        t,
        width,
        scene_duration
    ):
        if not movement:
            return 0.0

        movement_type = movement.get(
            "type",
            "linear"
        )

        if movement_type != "linear":
            raise ValueError(
                "Solo se soporta "
                "movement.type='linear'"
            )

        direction = (
            movement.get(
                "direction",
                "right"
            )
        ).lower()

        distance = float(
            movement.get(
                "distance",
                0.25
            )
        )

        start = float(
            movement.get(
                "start",
                0.0
            )
        )

        movement_duration = float(
            movement.get(
                "duration",
                max(
                    0.001,
                    scene_duration - start
                )
            )
        )

        easing = (
            movement.get(
                "easing",
                "linear"
            )
        ).lower()

        progress = clamp(
            (
                t
                - start
            )
            /
            max(
                0.001,
                movement_duration
            ),
            0.0,
            1.0
        )

        if easing == "smooth":
            progress = smoothstep(
                progress
            )

        elif easing != "linear":
            raise ValueError(
                "easing debe ser "
                "'linear' o 'smooth'"
            )

        pixels = (
            distance
            * width
        )

        if direction == "left":
            pixels *= -1

        elif direction != "right":
            raise ValueError(
                "direction de personajes "
                "debe ser 'left' o 'right'"
            )

        return (
            pixels
            * progress
        )

    # ============================================================
    # POSICIONES
    # ============================================================

    def _validate_positions(
        self,
        characters
    ):
        positions = [
            int(
                c.get(
                    "position",
                    i + 1
                )
            )
            for i, c in enumerate(
                characters
            )
        ]

        if any(
            p < 1
            for p in positions
        ):
            raise ValueError(
                "position debe ser >= 1"
            )

        if (
            len(
                set(
                    positions
                )
            )
            != len(
                positions
            )
        ):
            raise ValueError(
                "position no puede repetirse."
            )

    def _slot_centers(
        self,
        count,
        width
    ):
        if count <= 0:
            return []

        left = (
            width
            * 0.08
        )

        right = (
            width
            * 0.92
        )

        usable = (
            right
            - left
        )

        slot_width = (
            usable
            / count
        )

        return [
            left
            + slot_width
            * (
                i + 0.5
            )
            for i in range(
                count
            )
        ]

    def _auto_scale(self, count, width, height):
        if count <= 0:
            return 1.0
        # Tamaño común para 1, 2, 3 o más personajes; independiente de los slots.
        return min(width * 0.84 / 360.0, height * 0.70 / 620.0)

    # ============================================================
    # PERSONAJE
    # ============================================================


    def _render_character(self, char_type, action_name, color, t, scale, action=None,
                          pose=None, focus_parts=None, return_focus_bounds=False, facing="right", sample=None):
        sprite, effective = sample if sample is not None else self.assets.sprite_sample(char_type, action_name, t, facing=facing)
        factor = sprite_sheet_scale(scale, sprite.height)
        sprite = sprite.resize((max(1, round(sprite.width * factor)), max(1, round(sprite.height * factor))), Image.Resampling.LANCZOS)
        focus = sprite_focus_bounds(focus_parts, sprite.width, sprite.height, image=sprite, view=effective["view"]) if focus_parts else None
        return (sprite, focus) if return_focus_bounds else sprite

    # ============================================================
    # TINT CACHE
    # ============================================================
