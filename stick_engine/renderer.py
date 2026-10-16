import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .assets import AssetLibrary
from .animation import sample_action
from .utils import parse_color, clamp, smoothstep


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
        self._rig_structure_cache = {}
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

        width = self._even(
            max(
                2,
                int(
                    output_width
                    * INTERNAL_RENDER_SCALE
                )
            )
        )

        height = self._even(
            max(
                2,
                int(
                    output_height
                    * INTERNAL_RENDER_SCALE
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
        # Cargamos action/rig una sola vez por personaje/escena.

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

                # -----------------------------------------------
                # PERSONAJES
                # -----------------------------------------------

                for prepared in prepared_characters:
                    index = prepared[
                        "index"
                    ]

                    spec = prepared[
                        "spec"
                    ]

                    char_type = prepared[
                        "char_type"
                    ]

                    action_name = prepared[
                        "action_name"
                    ]

                    action = prepared[
                        "action"
                    ]

                    color = prepared[
                        "color"
                    ]

                    # Se calcula una sola vez y se reutiliza para
                    # root_x/root_y y para el render del personaje.
                    pose = sample_action(
                        action,
                        t
                    )

                    actor = self._render_character(
                        char_type=char_type,
                        action_name=action_name,
                        color=color,
                        t=t,
                        scale=scale,
                        action=action,
                        pose=pose
                    )

                    movement_x = self._movement_x(
                        movement=spec.get(
                            "movement"
                        ),
                        t=t,
                        width=width,
                        scene_duration=duration
                    )

                    root_x = (
                        float(
                            pose.get(
                                "root_x",
                                0.0
                            )
                        )
                        * scale
                    )

                    root_y = (
                        float(
                            pose.get(
                                "root_y",
                                0.0
                            )
                        )
                        * scale
                    )

                    x = int(
                        slots[index]
                        + movement_x
                        + root_x
                        - actor.width / 2
                    )

                    y = int(
                        ground_y
                        + root_y
                        - actor.height
                    )

                    frame.alpha_composite(
                        actor,
                        (
                            x,
                            y
                        )
                    )

                    # -------------------------------------------
                    # EMOTION BUBBLE
                    # -------------------------------------------

                    emotion = spec.get(
                        "emotion"
                    )

                    if emotion:
                        self._draw_emotion(
                            frame=frame,
                            emotion_name=str(
                                emotion
                            ),
                            actor_x=x,
                            actor_y=y,
                            actor_width=actor.width,
                            actor_scale=scale,
                            frame_width=width
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

    def _auto_scale(
        self,
        count,
        width,
        height
    ):
        if count <= 0:
            return 1.0

        slot_width = (
            width
            * 0.84
            / count
        )

        # El rig base era pensado para 360x620. Como ahora el frame
        # interno es menor, este cálculo reduce el personaje también.
        return clamp(
            min(
                slot_width
                / 360.0,
                (
                    height
                    * 0.56
                )
                / 620.0
            ),
            0.18,
            1.5
        )

    # ============================================================
    # PERSONAJE
    # ============================================================

    def _rig_structure(
        self,
        char_type
    ):
        if char_type in self._rig_structure_cache:
            return self._rig_structure_cache[
                char_type
            ]

        rig = self.assets.rig(
            char_type
        )

        parts = {
            part["name"]: part
            for part in rig["parts"]
        }

        children = {}

        for part in rig["parts"]:
            children.setdefault(
                part.get(
                    "parent"
                ),
                []
            ).append(
                part["name"]
            )

        result = (
            rig,
            parts,
            children
        )

        self._rig_structure_cache[
            char_type
        ] = result

        return result

    def _render_character(
        self,
        char_type,
        action_name,
        color,
        t,
        scale,
        action=None,
        pose=None
    ):
        rig, parts, children = (
            self._rig_structure(
                char_type
            )
        )

        if action is None:
            action = self.assets.action(
                char_type,
                action_name
            )

        if pose is None:
            pose = sample_action(
                action,
                t
            )

        canvas_width, canvas_height = rig.get(
            "canvas",
            [
                360,
                620
            ]
        )

        canvas = Image.new(
            "RGBA",
            (
                canvas_width,
                canvas_height
            ),
            (
                0,
                0,
                0,
                0
            )
        )

        def render_node(
            name,
            parent_world=None
        ):
            part = parts[
                name
            ]

            local_angle = (
                float(
                    part.get(
                        "angle",
                        0
                    )
                )
                +
                float(
                    pose.get(
                        name,
                        0
                    )
                )
            )

            local_x = (
                float(
                    part.get(
                        "x",
                        0
                    )
                )
                +
                float(
                    pose.get(
                        f"{name}_x",
                        0
                    )
                )
            )

            local_y = (
                float(
                    part.get(
                        "y",
                        0
                    )
                )
                +
                float(
                    pose.get(
                        f"{name}_y",
                        0
                    )
                )
            )

            if parent_world is None:
                world_x = local_x
                world_y = local_y
                world_angle = local_angle

            else:
                (
                    parent_x,
                    parent_y,
                    parent_angle
                ) = parent_world

                radians = math.radians(
                    parent_angle
                )

                rotated_x = (
                    local_x
                    * math.cos(
                        radians
                    )
                    -
                    local_y
                    * math.sin(
                        radians
                    )
                )

                rotated_y = (
                    local_x
                    * math.sin(
                        radians
                    )
                    +
                    local_y
                    * math.cos(
                        radians
                    )
                )

                world_x = (
                    parent_x
                    + rotated_x
                )

                world_y = (
                    parent_y
                    + rotated_y
                )

                world_angle = (
                    parent_angle
                    + local_angle
                )

            sprite = self.assets.sprite(
                char_type,
                part["sprite"]
            )

            if not part.get("embedded_color", False):
                sprite = self._tint(
                    sprite,
                    color
                )

            pivot = part.get(
                "pivot",
                [
                    sprite.width / 2,
                    sprite.height / 2
                ]
            )

            self._paste_at_joint(
                canvas=canvas,
                sprite=sprite,
                joint_x=world_x,
                joint_y=world_y,
                angle=world_angle,
                pivot_x=float(
                    pivot[0]
                ),
                pivot_y=float(
                    pivot[1]
                )
            )

            for child_name in children.get(
                name,
                []
            ):
                render_node(
                    child_name,
                    (
                        world_x,
                        world_y,
                        world_angle
                    )
                )

        for root_name in children.get(
            None,
            []
        ):
            render_node(
                root_name
            )

        bbox = canvas.getbbox()

        if bbox:
            canvas = canvas.crop(
                bbox
            )

        if scale != 1.0:
            canvas = canvas.resize(
                (
                    max(
                        1,
                        int(
                            canvas.width
                            * scale
                        )
                    ),
                    max(
                        1,
                        int(
                            canvas.height
                            * scale
                        )
                    )
                ),
                Image.Resampling.LANCZOS
            )

        return canvas

    # ============================================================
    # TINT CACHE
    # ============================================================

    def _tint(
        self,
        image,
        color
    ):
        if not isinstance(
            color,
            tuple
        ):
            color = tuple(
                color
            )

        key = (
            id(image),
            color
        )

        if key in self._tint_cache:
            return self._tint_cache[
                key
            ]

        alpha = image.getchannel(
            "A"
        )

        result = Image.new(
            "RGBA",
            image.size,
            color
        )

        result.putalpha(
            alpha
        )

        self._tint_cache[
            key
        ] = result

        return result

    def _paste_at_joint(
        self,
        canvas,
        sprite,
        joint_x,
        joint_y,
        angle,
        pivot_x,
        pivot_y
    ):
        pad = int(
            max(
                sprite.width,
                sprite.height
            )
            * 3
        )

        stage = Image.new(
            "RGBA",
            (
                pad,
                pad
            ),
            (
                0,
                0,
                0,
                0
            )
        )

        center_x = (
            pad // 2
        )

        center_y = (
            pad // 2
        )

        stage.alpha_composite(
            sprite,
            (
                int(
                    center_x
                    - pivot_x
                ),
                int(
                    center_y
                    - pivot_y
                )
            )
        )

        rotated = stage.rotate(
            -angle,
            resample=Image.Resampling.BICUBIC,
            center=(
                center_x,
                center_y
            ),
            expand=False
        )

        canvas.alpha_composite(
            rotated,
            (
                int(
                    joint_x
                    - center_x
                ),
                int(
                    joint_y
                    - center_y
                )
            )
        )
