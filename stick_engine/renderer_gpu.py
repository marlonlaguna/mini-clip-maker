import math
import subprocess
from array import array
from pathlib import Path

import moderngl
from PIL import Image, ImageDraw, ImageFont

from .assets import AssetLibrary
from .animation import sample_action
from .utils import clamp, parse_color, smoothstep


# 1.0 = resolución nativa.
# Si luego quieres más velocidad puedes probar 0.75.
GPU_RENDER_SCALE = 1.0


class StickRendererGPU:

    def __init__(self):
        self.assets = AssetLibrary()

        self.ctx = moderngl.create_standalone_context(
            require=330
        )

        self.ctx.enable(
            moderngl.BLEND
        )

        self.ctx.blend_func = (
            moderngl.SRC_ALPHA,
            moderngl.ONE_MINUS_SRC_ALPHA
        )

        self.program = self.ctx.program(

            vertex_shader="""
                #version 330

                in vec2 in_pos;
                in vec2 in_uv;

                uniform vec2 u_resolution;

                out vec2 v_uv;

                void main() {

                    float x =
                        (in_pos.x / u_resolution.x)
                        * 2.0 - 1.0;

                    float y =
                        (in_pos.y / u_resolution.y)
                        * 2.0 - 1.0;

                    gl_Position =
                        vec4(
                            x,
                            y,
                            0.0,
                            1.0
                        );

                    v_uv = in_uv;
                }
            """,

            fragment_shader="""
                #version 330

                uniform sampler2D u_texture;

                uniform vec4 u_tint;

                uniform int u_use_tint;

                in vec2 v_uv;

                out vec4 fragColor;

                void main() {

                    vec4 tex =
                        texture(
                            u_texture,
                            v_uv
                        );

                    if (
                        tex.a <= 0.001
                    ) {
                        discard;
                    }

                    if (
                        u_use_tint == 1
                    ) {

                        fragColor =
                            vec4(
                                u_tint.rgb,
                                tex.a
                                *
                                u_tint.a
                            );

                    } else {

                        fragColor = tex;
                    }
                }
            """
        )

        self.vbo = (
            self.ctx.buffer(
                reserve=(
                    6
                    * 4
                    * 4
                )
            )
        )

        self.vao = (
            self.ctx.vertex_array(
                self.program,
                [
                    (
                        self.vbo,
                        "2f 2f",
                        "in_pos",
                        "in_uv"
                    )
                ]
            )
        )

        self.program[
            "u_texture"
        ].value = 0

        self._texture_cache = {}

        self._emoji_texture_cache = {}

        self._rig_structure_cache = {}

        self._encoder_cache = None

        self.emoji_font_candidates = [

            Path(
                r"C:\Windows\Fonts\seguiemj.ttf"
            ),

            Path(
                r"C:\Windows\Fonts\segoeuiemoji.ttf"
            ),

            Path(
                r"C:\Windows\Fonts\arial.ttf"
            )
        ]

        self._emoji_font_cache = {}

    # ============================================================
    # RENDER
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

        if (
            output_width <= 0
            or
            output_height <= 0
        ):

            raise ValueError(
                "Resolución inválida"
            )

        if duration <= 0:

            raise ValueError(
                "duration debe ser > 0"
            )

        if fps <= 0:

            raise ValueError(
                "fps debe ser > 0"
            )

        width = self._even(

            max(
                2,
                int(
                    output_width
                    *
                    GPU_RENDER_SCALE
                )
            )
        )

        height = self._even(

            max(
                2,
                int(
                    output_height
                    *
                    GPU_RENDER_SCALE
                )
            )
        )

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

        count = len(
            characters
        )

        actor_scale = (
            self._auto_scale(
                count,
                width,
                height
            )
        )

        slots = (
            self._slot_centers(
                count,
                width
            )
        )

        ground_y = (
            height
            * 0.83
        )

        prepared_characters = []

        for (
            index,
            spec
        ) in enumerate(
            characters
        ):

            char_type = (
                spec.get(
                    "type",
                    "stickman"
                )
            )

            action_name = (
                spec.get(
                    "action",
                    "idle"
                )
            )

            prepared_characters.append(
                {
                    "index":
                        index,

                    "spec":
                        spec,

                    "char_type":
                        char_type,

                    "action_name":
                        action_name,

                    "action":
                        self.assets.action(
                            char_type,
                            action_name
                        ),

                    "color":
                        parse_color(
                            spec.get(
                                "color",
                                "black"
                            )
                        )
                }
            )

        # --------------------------------------------------------
        # GPU FRAMEBUFFER
        # --------------------------------------------------------

        color_tex = (
            self.ctx.texture(
                (
                    width,
                    height
                ),
                4
            )
        )

        color_tex.filter = (
            moderngl.LINEAR,
            moderngl.LINEAR
        )

        fbo = (
            self.ctx.framebuffer(
                color_attachments=[
                    color_tex
                ]
            )
        )

        fbo.use()

        self.ctx.viewport = (
            0,
            0,
            width,
            height
        )

        self.program[
            "u_resolution"
        ].value = (
            float(width),
            float(height)
        )

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

            "-an"
        ]

        if (
            width,
            height
        ) != (
            output_width,
            output_height
        ):

            command += [

                "-vf",

                (
                    f"scale="
                    f"{output_width}:"
                    f"{output_height}:"
                    f"flags=lanczos"
                )
            ]

        command += [

            "-c:v",
            encoder,

            "-preset",
            preset,

            "-pix_fmt",
            "yuv420p",

            "-movflags",
            "+faststart",

            str(
                output_path
            )
        ]

        proc = subprocess.Popen(

            command,

            stdin=subprocess.PIPE,

            stdout=(
                subprocess.DEVNULL
            ),

            stderr=(
                subprocess.PIPE
            )
        )

        if proc.stdin is None:

            raise RuntimeError(
                "No se pudo abrir FFmpeg"
            )

        total_frames = max(

            1,

            round(
                duration
                *
                fps
            )
        )

        try:

            background_texture = (
                self._background_texture(
                    scene[
                        "background"
                    ]
                )
            )

            # ====================================================
            # FRAMES
            # ====================================================

            for frame_index in range(
                total_frames
            ):

                t = (
                    frame_index
                    /
                    fps
                )

                fbo.use()

                fbo.clear(
                    0.0,
                    0.0,
                    0.0,
                    1.0
                )

                # ------------------------------------------------
                # BACKGROUND
                # ------------------------------------------------

                self._draw_texture_rect(

                    texture=(
                        background_texture
                    ),

                    x=0.0,

                    y=0.0,

                    width=float(
                        width
                    ),

                    height=float(
                        height
                    ),

                    tint=None
                )

                # ------------------------------------------------
                # CHARACTERS
                # ------------------------------------------------

                for prepared in (
                    prepared_characters
                ):

                    index = (
                        prepared[
                            "index"
                        ]
                    )

                    spec = (
                        prepared[
                            "spec"
                        ]
                    )

                    char_type = (
                        prepared[
                            "char_type"
                        ]
                    )

                    action = (
                        prepared[
                            "action"
                        ]
                    )

                    color = (
                        prepared[
                            "color"
                        ]
                    )

                    pose = (
                        sample_action(
                            action,
                            t
                        )
                    )

                    (
                        parts,
                        bbox
                    ) = (
                        self._character_geometry(
                            char_type,
                            pose
                        )
                    )

                    (
                        min_x,
                        min_y,
                        max_x,
                        max_y
                    ) = bbox

                    movement_x = (
                        self._movement_x(

                            movement=(
                                spec.get(
                                    "movement"
                                )
                            ),

                            t=t,

                            width=width,

                            scene_duration=(
                                duration
                            )
                        )
                    )

                    root_x = (
                        float(
                            pose.get(
                                "root_x",
                                0.0
                            )
                        )
                        *
                        actor_scale
                    )

                    root_y = (
                        float(
                            pose.get(
                                "root_y",
                                0.0
                            )
                        )
                        *
                        actor_scale
                    )

                    actor_center_x = (
                        (
                            min_x
                            +
                            max_x
                        )
                        /
                        2.0
                        *
                        actor_scale
                    )

                    actor_bottom_y = (
                        max_y
                        *
                        actor_scale
                    )

                    offset_x = (

                        slots[index]

                        +
                        movement_x

                        +
                        root_x

                        -
                        actor_center_x
                    )

                    offset_y = (

                        ground_y

                        +
                        root_y

                        -
                        actor_bottom_y
                    )

                    # --------------------------------------------
                    # BODY PARTS
                    # --------------------------------------------

                    for part in parts:

                        texture = (
                            self._sprite_texture(

                                char_type,

                                part[
                                    "sprite"
                                ]
                            )
                        )

                        screen_corners = [

                            (
                                px
                                *
                                actor_scale
                                +
                                offset_x,

                                py
                                *
                                actor_scale
                                +
                                offset_y
                            )

                            for (
                                px,
                                py
                            )
                            in part[
                                "corners"
                            ]
                        ]

                        self._draw_texture_quad(

                            texture=(
                                texture
                            ),

                            corners=(
                                screen_corners
                            ),

                            tint=(
                                None
                                if part.get("embedded_color", False)
                                else color
                            )
                        )

                    # --------------------------------------------
                    # EMOTION
                    # --------------------------------------------

                    emotion = (
                        spec.get(
                            "emotion"
                        )
                    )

                    if emotion:

                        actor_x = (
                            min_x
                            *
                            actor_scale
                            +
                            offset_x
                        )

                        actor_y = (
                            min_y
                            *
                            actor_scale
                            +
                            offset_y
                        )

                        actor_width = (
                            (
                                max_x
                                -
                                min_x
                            )
                            *
                            actor_scale
                        )

                        self._draw_emotion(

                            emotion_name=(
                                str(
                                    emotion
                                )
                            ),

                            actor_x=(
                                actor_x
                            ),

                            actor_y=(
                                actor_y
                            ),

                            actor_width=(
                                actor_width
                            ),

                            actor_scale=(
                                actor_scale
                            ),

                            frame_width=(
                                width
                            )
                        )

                # ------------------------------------------------
                # EMOJIS
                # ------------------------------------------------

                for obj in scene.get(
                    "objects",
                    []
                ):

                    if (
                        str(
                            obj.get(
                                "type",
                                ""
                            )
                        ).lower()
                        ==
                        "emoji"
                    ):

                        self._draw_emoji_object(

                            obj=obj,

                            t=t,

                            width=width,

                            height=height,

                            scene_duration=(
                                duration
                            )
                        )

                # ------------------------------------------------
                # GPU -> FFMPEG
                # ------------------------------------------------

                frame_bytes = (
                    fbo.read(
                        components=4,
                        alignment=1
                    )
                )

                proc.stdin.write(
                    frame_bytes
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
                    +
                    stderr
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

        finally:

            fbo.release()

            color_tex.release()

        return output_path

    # ============================================================
    # RIG
    # ============================================================

    def _rig_structure(
        self,
        char_type
    ):

        if char_type in (
            self._rig_structure_cache
        ):

            return (
                self._rig_structure_cache[
                    char_type
                ]
            )

        rig = (
            self.assets.rig(
                char_type
            )
        )

        parts = {

            part[
                "name"
            ]:
            part

            for part
            in rig[
                "parts"
            ]
        }

        children = {}

        for part in rig[
            "parts"
        ]:

            children.setdefault(

                part.get(
                    "parent"
                ),

                []

            ).append(
                part[
                    "name"
                ]
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

    def _character_geometry(
        self,
        char_type,
        pose
    ):

        (
            _,
            parts_by_name,
            children
        ) = (
            self._rig_structure(
                char_type
            )
        )

        ordered_parts = []

        all_points = []

        def walk(
            name,
            parent_world=None
        ):

            part = (
                parts_by_name[
                    name
                ]
            )

            local_angle = (

                float(
                    part.get(
                        "angle",
                        0.0
                    )
                )

                +

                float(
                    pose.get(
                        name,
                        0.0
                    )
                )
            )

            local_x = (

                float(
                    part.get(
                        "x",
                        0.0
                    )
                )

                +

                float(
                    pose.get(
                        f"{name}_x",
                        0.0
                    )
                )
            )

            local_y = (

                float(
                    part.get(
                        "y",
                        0.0
                    )
                )

                +

                float(
                    pose.get(
                        f"{name}_y",
                        0.0
                    )
                )
            )

            if (
                parent_world
                is None
            ):

                world_x = local_x

                world_y = local_y

                world_angle = (
                    local_angle
                )

            else:

                (
                    parent_x,
                    parent_y,
                    parent_angle
                ) = (
                    parent_world
                )

                rad = math.radians(
                    parent_angle
                )

                rotated_x = (

                    local_x
                    *
                    math.cos(
                        rad
                    )

                    -

                    local_y
                    *
                    math.sin(
                        rad
                    )
                )

                rotated_y = (

                    local_x
                    *
                    math.sin(
                        rad
                    )

                    +

                    local_y
                    *
                    math.cos(
                        rad
                    )
                )

                world_x = (
                    parent_x
                    +
                    rotated_x
                )

                world_y = (
                    parent_y
                    +
                    rotated_y
                )

                world_angle = (
                    parent_angle
                    +
                    local_angle
                )

            sprite = (
                self.assets.sprite(

                    char_type,

                    part[
                        "sprite"
                    ]
                )
            )

            pivot = (
                part.get(

                    "pivot",

                    [
                        sprite.width
                        /
                        2.0,

                        sprite.height
                        /
                        2.0
                    ]
                )
            )

            pivot_x = float(
                pivot[
                    0
                ]
            )

            pivot_y = float(
                pivot[
                    1
                ]
            )

            local_corners = [

                (
                    -pivot_x,
                    -pivot_y
                ),

                (
                    sprite.width
                    -
                    pivot_x,

                    -pivot_y
                ),

                (
                    sprite.width
                    -
                    pivot_x,

                    sprite.height
                    -
                    pivot_y
                ),

                (
                    -pivot_x,

                    sprite.height
                    -
                    pivot_y
                )
            ]

            angle_rad = (
                math.radians(
                    world_angle
                )
            )

            cos_a = math.cos(
                angle_rad
            )

            sin_a = math.sin(
                angle_rad
            )

            world_corners = []

            for (
                cx,
                cy
            ) in (
                local_corners
            ):

                rx = (
                    cx
                    *
                    cos_a

                    -

                    cy
                    *
                    sin_a
                )

                ry = (
                    cx
                    *
                    sin_a

                    +

                    cy
                    *
                    cos_a
                )

                point = (

                    world_x
                    +
                    rx,

                    world_y
                    +
                    ry
                )

                world_corners.append(
                    point
                )

                all_points.append(
                    point
                )

            ordered_parts.append(
                {
                    "name":
                        name,

                    "sprite":
                        part[
                            "sprite"
                        ],

                    "embedded_color":
                        bool(part.get("embedded_color", False)),

                    "corners":
                        world_corners
                }
            )

            for child_name in (
                children.get(
                    name,
                    []
                )
            ):

                walk(
                    child_name,
                    (
                        world_x,
                        world_y,
                        world_angle
                    )
                )

        for root_name in (
            children.get(
                None,
                []
            )
        ):

            walk(
                root_name
            )

        if not all_points:

            return (
                ordered_parts,
                (
                    0.0,
                    0.0,
                    1.0,
                    1.0
                )
            )

        xs = [
            point[0]
            for point
            in all_points
        ]

        ys = [
            point[1]
            for point
            in all_points
        ]

        bbox = (

            min(
                xs
            ),

            min(
                ys
            ),

            max(
                xs
            ),

            max(
                ys
            )
        )

        return (
            ordered_parts,
            bbox
        )

    # ============================================================
    # DRAW
    # ============================================================

    def _draw_texture_rect(
        self,
        texture,
        x,
        y,
        width,
        height,
        tint=None
    ):

        corners = [

            (
                x,
                y
            ),

            (
                x + width,
                y
            ),

            (
                x + width,
                y + height
            ),

            (
                x,
                y + height
            )
        ]

        self._draw_texture_quad(

            texture,

            corners,

            tint
        )

    def _draw_texture_quad(
        self,
        texture,
        corners,
        tint=None
    ):

        (
            tl,
            tr,
            br,
            bl
        ) = corners

        data = array(

            "f",

            [
                tl[0],
                tl[1],
                0.0,
                0.0,

                tr[0],
                tr[1],
                1.0,
                0.0,

                br[0],
                br[1],
                1.0,
                1.0,

                tl[0],
                tl[1],
                0.0,
                0.0,

                br[0],
                br[1],
                1.0,
                1.0,

                bl[0],
                bl[1],
                0.0,
                1.0
            ]
        )

        self.vbo.write(
            data.tobytes()
        )

        texture.use(
            location=0
        )

        if tint is None:

            self.program[
                "u_use_tint"
            ].value = 0

            self.program[
                "u_tint"
            ].value = (
                1.0,
                1.0,
                1.0,
                1.0
            )

        else:

            (
                r,
                g,
                b,
                a
            ) = (
                self._rgba(
                    tint
                )
            )

            self.program[
                "u_use_tint"
            ].value = 1

            self.program[
                "u_tint"
            ].value = (

                r / 255.0,

                g / 255.0,

                b / 255.0,

                a / 255.0
            )

        self.vao.render(
            mode=(
                moderngl.TRIANGLES
            )
        )

    # ============================================================
    # TEXTURES
    # ============================================================

    def _pil_to_texture(
        self,
        image
    ):

        image = image.convert(
            "RGBA"
        )

        texture = (
            self.ctx.texture(

                image.size,

                4,

                image.tobytes()
            )
        )

        texture.filter = (

            moderngl.LINEAR,

            moderngl.LINEAR
        )

        texture.repeat_x = False

        texture.repeat_y = False

        return texture

    def _background_texture(
        self,
        name
    ):

        key = (
            "background",
            name
        )

        if (
            key
            not in
            self._texture_cache
        ):

            self._texture_cache[
                key
            ] = (
                self._pil_to_texture(

                    self.assets.background(
                        name
                    )
                )
            )

        return (
            self._texture_cache[
                key
            ]
        )

    def _sprite_texture(
        self,
        char_type,
        sprite_name
    ):

        key = (

            "sprite",

            char_type,

            sprite_name
        )

        if (
            key
            not in
            self._texture_cache
        ):

            self._texture_cache[
                key
            ] = (
                self._pil_to_texture(

                    self.assets.sprite(
                        char_type,
                        sprite_name
                    )
                )
            )

        return (
            self._texture_cache[
                key
            ]
        )

    def _emotion_texture(
        self,
        emotion_name
    ):

        key = (
            "emotion",
            emotion_name
        )

        if (
            key
            not in
            self._texture_cache
        ):

            self._texture_cache[
                key
            ] = (
                self._pil_to_texture(

                    self.assets.emotion(
                        emotion_name
                    )
                )
            )

        return (
            self._texture_cache[
                key
            ]
        )

    # ============================================================
    # EMOTIONS
    # ============================================================

    def _draw_emotion(
        self,
        emotion_name,
        actor_x,
        actor_y,
        actor_width,
        actor_scale,
        frame_width
    ):

        image = (
            self.assets.emotion(
                emotion_name
            )
        )

        texture = (
            self._emotion_texture(
                emotion_name
            )
        )

        bubble_scale = (
            clamp(
                actor_scale
                *
                0.72,
                0.30,
                1.0
            )
        )

        bubble_width = (
            image.width
            *
            bubble_scale
        )

        bubble_height = (
            image.height
            *
            bubble_scale
        )

        bubble_x = (

            actor_x

            +
            actor_width
            /
            2.0

            -
            bubble_width
            /
            2.0
        )

        bubble_y = (

            actor_y

            -
            bubble_height

            -
            18.0
            *
            actor_scale
        )

        bubble_x = clamp(

            bubble_x,

            8.0,

            max(
                8.0,
                frame_width
                -
                bubble_width
                -
                8.0
            )
        )

        bubble_y = max(
            8.0,
            bubble_y
        )

        self._draw_texture_rect(

            texture,

            bubble_x,

            bubble_y,

            bubble_width,

            bubble_height,

            tint=None
        )

    # ============================================================
    # EMOJIS
    # ============================================================

    def _emoji_font(
        self,
        size
    ):

        size = max(
            12,
            int(
                size
            )
        )

        if (
            size
            in
            self._emoji_font_cache
        ):

            return (
                self._emoji_font_cache[
                    size
                ]
            )

        for path in (
            self.emoji_font_candidates
        ):

            if path.exists():

                try:

                    font = (
                        ImageFont.truetype(
                            str(
                                path
                            ),
                            size
                        )
                    )

                    self._emoji_font_cache[
                        size
                    ] = font

                    return font

                except Exception:
                    pass

        font = (
            ImageFont.load_default()
        )

        self._emoji_font_cache[
            size
        ] = font

        return font

    def _emoji_texture(
        self,
        value,
        size
    ):

        key = (
            value,
            int(
                size
            )
        )

        if (
            key
            in
            self._emoji_texture_cache
        ):

            return (
                self._emoji_texture_cache[
                    key
                ]
            )

        font = (
            self._emoji_font(
                size
            )
        )

        probe = Image.new(

            "RGBA",

            (
                size * 3,
                size * 3
            ),

            (
                0,
                0,
                0,
                0
            )
        )

        draw = (
            ImageDraw.Draw(
                probe
            )
        )

        try:

            bbox = (
                draw.textbbox(

                    (
                        0,
                        0
                    ),

                    value,

                    font=font,

                    embedded_color=True
                )
            )

        except Exception:

            bbox = (
                draw.textbbox(

                    (
                        0,
                        0
                    ),

                    value,

                    font=font
                )
            )

        width = max(
            1,
            bbox[2]
            -
            bbox[0]
        )

        height = max(
            1,
            bbox[3]
            -
            bbox[1]
        )

        margin = max(
            4,
            int(
                size
                *
                0.12
            )
        )

        image = Image.new(

            "RGBA",

            (
                width
                +
                margin * 2,

                height
                +
                margin * 2
            ),

            (
                0,
                0,
                0,
                0
            )
        )

        draw = (
            ImageDraw.Draw(
                image
            )
        )

        pos = (

            margin
            -
            bbox[0],

            margin
            -
            bbox[1]
        )

        try:

            draw.text(

                pos,

                value,

                font=font,

                embedded_color=True
            )

        except Exception:

            draw.text(

                pos,

                value,

                font=font,

                fill=(
                    255,
                    255,
                    255,
                    255
                )
            )

        texture = (
            self._pil_to_texture(
                image
            )
        )

        result = (

            texture,

            image.width,

            image.height
        )

        self._emoji_texture_cache[
            key
        ] = result

        return result

    def _draw_emoji_object(
        self,
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

            18,

            int(
                requested_size
                *
                width
                /
                1080.0
            )
        )

        movement = (
            obj.get(
                "movement"
            )
        )

        offset_x = 0.0

        offset_y = 0.0

        if movement:

            direction = str(
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

            move_duration = float(
                movement.get(
                    "duration",
                    scene_duration
                )
            )

            progress = clamp(

                (
                    t
                    -
                    start
                )

                /

                max(
                    0.001,
                    move_duration
                ),

                0.0,

                1.0
            )

            if (
                str(
                    movement.get(
                        "easing",
                        "smooth"
                    )
                ).lower()
                ==
                "smooth"
            ):

                progress = (
                    smoothstep(
                        progress
                    )
                )

            if (
                direction
                ==
                "right"
            ):

                offset_x = (
                    distance
                    *
                    progress
                )

            elif (
                direction
                ==
                "left"
            ):

                offset_x = (
                    -distance
                    *
                    progress
                )

            elif (
                direction
                ==
                "down"
            ):

                offset_y = (
                    distance
                    *
                    progress
                )

            elif (
                direction
                ==
                "up"
            ):

                offset_y = (
                    -distance
                    *
                    progress
                )

        final_x = clamp(

            x
            +
            offset_x,

            -0.20,

            1.20
        )

        final_y = clamp(

            y
            +
            offset_y,

            -0.20,

            1.20
        )

        px = (
            final_x
            *
            width
        )

        py = (
            final_y
            *
            height
        )

        (
            texture,
            texture_width,
            texture_height
        ) = (
            self._emoji_texture(
                value,
                size
            )
        )

        self._draw_texture_rect(

            texture,

            px
            -
            texture_width
            /
            2.0,

            py
            -
            texture_height
            /
            2.0,

            float(
                texture_width
            ),

            float(
                texture_height
            ),

            tint=None
        )

    # ============================================================
    # MOVEMENT
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

        if (
            movement.get(
                "type",
                "linear"
            )
            !=
            "linear"
        ):

            return 0.0

        direction = str(
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

        move_duration = float(
            movement.get(

                "duration",

                max(
                    0.001,
                    scene_duration
                    -
                    start
                )
            )
        )

        progress = clamp(

            (
                t
                -
                start
            )

            /

            max(
                0.001,
                move_duration
            ),

            0.0,

            1.0
        )

        easing = str(
            movement.get(
                "easing",
                "linear"
            )
        ).lower()

        if (
            easing
            ==
            "smooth"
        ):

            progress = (
                smoothstep(
                    progress
                )
            )

        pixels = (
            distance
            *
            width
        )

        if (
            direction
            ==
            "left"
        ):

            pixels *= -1.0

        return (
            pixels
            *
            progress
        )

    # ============================================================
    # POSITION / SCALE
    # ============================================================

    def _validate_positions(
        self,
        characters
    ):

        positions = [

            int(
                character.get(
                    "position",
                    index + 1
                )
            )

            for (
                index,
                character
            )
            in enumerate(
                characters
            )
        ]

        if any(
            position < 1
            for position
            in positions
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
            !=
            len(
                positions
            )
        ):

            raise ValueError(
                "position no puede repetirse"
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
            *
            0.08
        )

        right = (
            width
            *
            0.92
        )

        slot_width = (
            right
            -
            left
        ) / count

        return [

            left
            +
            slot_width
            *
            (
                index
                +
                0.5
            )

            for index
            in range(
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
            *
            0.84

            /
            count
        )

        return clamp(

            min(

                slot_width
                /
                360.0,

                (
                    height
                    *
                    0.56
                )
                /
                620.0
            ),

            0.18,

            1.5
        )

    # ============================================================
    # ENCODER
    # ============================================================

    def _video_encoder(
        self
    ):

        if (
            self._encoder_cache
            is not None
        ):

            return (
                self._encoder_cache
            )

        try:

            result = (
                subprocess.run(

                    [
                        "ffmpeg",
                        "-hide_banner",
                        "-encoders"
                    ],

                    capture_output=True,

                    text=True,

                    check=False
                )
            )

            text = (
                (
                    result.stdout
                    or
                    ""
                )
                +
                (
                    result.stderr
                    or
                    ""
                )
            )

            if (
                "h264_nvenc"
                in
                text
            ):

                self._encoder_cache = (

                    "h264_nvenc",

                    "p1"
                )

                return (
                    self._encoder_cache
                )

        except Exception:
            pass

        self._encoder_cache = (

            "libx264",

            "ultrafast"
        )

        return (
            self._encoder_cache
        )

    # ============================================================
    # HELPERS
    # ============================================================

    @staticmethod
    def _rgba(
        color
    ):

        values = tuple(
            color
        )

        if len(
            values
        ) == 3:

            return (

                values[0],

                values[1],

                values[2],

                255
            )

        return (

            values[0],

            values[1],

            values[2],

            values[3]
        )

    @staticmethod
    def _even(
        value
    ):

        value = int(
            value
        )

        if (
            value
            %
            2
            ==
            0
        ):

            return value

        return (
            value
            -
            1
        )

    # ============================================================
    # CLOSE
    # ============================================================

    def close(
        self
    ):

        for texture in (
            self._texture_cache.values()
        ):

            try:
                texture.release()
            except Exception:
                pass

        for (
            texture,
            _,
            _
        ) in (
            self._emoji_texture_cache.values()
        ):

            try:
                texture.release()
            except Exception:
                pass

        try:

            self.vao.release()

            self.vbo.release()

            self.program.release()

            self.ctx.release()

        except Exception:
            pass