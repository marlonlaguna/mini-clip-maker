import json
import re
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw

from .utils import ASSETS_DIR


ALIASES = {
    "none": "idle",
    "stand": "idle",
    "hello": "wave",
}


class AssetLibrary:
    """
    Librería de assets con caché en memoria.

    El objetivo es evitar abrir/decodificar los mismos PNG y JSON miles de
    veces durante el render de un video.
    """

    def __init__(self):
        self.root = ASSETS_DIR

        self._background_cache = {}
        self._rig_cache = {}
        self._action_cache = {}
        self._sprite_cache = {}
        self._emotion_cache = {}
        self._sheet_cache = {}
        self._sheet_frame_cache = {}
        self._sheet_type_cache = {}

        self._catalog_cache = None

    # ============================================================
    # HELPERS
    # ============================================================

    @staticmethod
    def _read_json(path: Path):
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    @staticmethod
    def _type_key(value):
        value = unicodedata.normalize("NFKD", str(value or ""))
        value = "".join(
            char for char in value
            if not unicodedata.combining(char)
        ).lower()
        return re.sub(r"[^a-z0-9]+", "_", value).strip("_")

    def _character_dir(self, character_type):
        characters_dir = self.root / "characters"
        direct = characters_dir / str(character_type)
        if direct.is_dir():
            return direct

        wanted = self._type_key(character_type)
        if characters_dir.exists():
            for candidate in characters_dir.iterdir():
                if candidate.is_dir() and self._type_key(candidate.name) == wanted:
                    return candidate
        return direct

    @staticmethod
    def _sheet_image_path(character_dir, config):
        declared = str(config.get("spriteSheet", "") or "").strip()
        candidates = []
        if declared:
            candidates.append(character_dir / declared)
        candidates.extend((character_dir / "charset.png", character_dir / "charset.PNG"))

        for path in candidates:
            if path.is_file():
                return path

        pngs = sorted(character_dir.glob("*.png"))
        return pngs[0] if pngs else None

    def is_sprite_sheet(self, character_type):
        key = self._type_key(character_type)
        if key in self._sheet_type_cache:
            return self._sheet_type_cache[key]
        character_dir = self._character_dir(character_type)
        actions_path = character_dir / "actions.json"
        if not actions_path.is_file():
            self._sheet_type_cache[key] = False
            return False
        try:
            config = self._read_json(actions_path)
        except (OSError, ValueError, json.JSONDecodeError):
            self._sheet_type_cache[key] = False
            return False
        result = self._sheet_image_path(character_dir, config) is not None
        self._sheet_type_cache[key] = result
        return result

    def _sheet_data(self, character_type):
        character_dir = self._character_dir(character_type)
        key = self._type_key(character_dir.name)
        if key in self._sheet_cache:
            return self._sheet_cache[key]

        config_path = character_dir / "actions.json"
        if not config_path.is_file():
            raise FileNotFoundError(
                f"No existe actions.json para '{character_type}'"
            )

        config = self._read_json(config_path)
        image_path = self._sheet_image_path(character_dir, config)
        if image_path is None:
            raise FileNotFoundError(
                f"No se encontró charset PNG para '{character_type}'"
            )

        with Image.open(image_path) as source:
            source_mode = source.mode
            image = source.convert("RGBA")
        # Los charsets actuales usan fondo blanco. Solo se elimina el blanco
        # conectado al borde para conservar detalles blancos dentro del sprite.
        if source_mode != "RGBA":
            marked = image.convert("RGB")
            marker = (1, 2, 3)
            for seed in ((0, 0), (marked.width - 1, 0), (0, marked.height - 1), (marked.width - 1, marked.height - 1)):
                ImageDraw.floodfill(marked, seed, marker, thresh=24)
            alpha = Image.new("L", marked.size, 255)
            alpha_pixels = alpha.load()
            marker_pixels = marked.load()
            for y in range(marked.height):
                for x in range(marked.width):
                    if marker_pixels[x, y] == marker:
                        alpha_pixels[x, y] = 0
            image.putalpha(alpha)

        animations = config.get("animations", [])
        if isinstance(animations, dict):
            animations = [
                dict(value, name=name)
                for name, value in animations.items()
                if isinstance(value, dict)
            ]
        animation_map = {
            str(item.get("name", "")).strip(): item
            for item in animations
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        }
        if not animation_map:
            raise ValueError(
                f"actions.json de '{character_type}' no contiene animaciones"
            )

        frame_size = config.get("frameSize", {})
        data = {
            "config": config,
            "image": image,
            "animations": animation_map,
            "frame_width": int(frame_size.get("width", 100)),
            "frame_height": int(frame_size.get("height", 100)),
            "default_fps": float(config.get("frameRate", 8.0)),
        }
        if data["frame_width"] <= 0 or data["frame_height"] <= 0:
            raise ValueError(
                f"frameSize inválido en {config_path}"
            )

        self._sheet_cache[key] = data
        return data

    # ============================================================
    # BACKGROUNDS
    # ============================================================

    def background(self, name):
        if name in self._background_cache:
            return self._background_cache[name]

        path = (
            self.root
            / "backgrounds"
            / f"{name}.png"
        )

        if not path.exists():
            available = self.backgrounds()

            raise FileNotFoundError(
                f"Background '{name}' no existe. "
                f"Disponibles: {available}"
            )

        image = Image.open(path).convert("RGBA")
        self._background_cache[name] = image

        return image

    # ============================================================
    # RIGS
    # ============================================================

    def rig(self, character_type):
        if character_type in self._rig_cache:
            return self._rig_cache[character_type]

        path = (
            self._character_dir(character_type)
            / "rig.json"
        )

        if not path.exists():
            available = self.character_types()

            raise FileNotFoundError(
                f"Tipo de personaje '{character_type}' no existe. "
                f"Disponibles: {available}"
            )

        data = self._read_json(path)
        self._rig_cache[character_type] = data

        return data

    # ============================================================
    # ACTIONS
    # ============================================================

    def action(
        self,
        character_type,
        action_name
    ):
        if self.is_sprite_sheet(character_type):
            data = self._sheet_data(character_type)
            actions = data["animations"]
            requested = str(action_name or "none").strip()
            if requested not in actions:
                aliases = {
                    "idle": ("none",),
                    "stand": ("none",),
                    "walk": ("walk_front",),
                    "run": ("walk_front",),
                    "talk": ("speak",),
                    "speaking": ("speak",),
                    "look_back": ("turn_around",),
                    "turn": ("turn_around",),
                    "scared": ("afraid",),
                    "fear": ("afraid",),
                    "crying": ("cry",),
                    "pointing": ("point",),
                }
                requested = next(
                    (candidate for candidate in aliases.get(requested, ()) if candidate in actions),
                    "none" if "none" in actions else next(iter(actions)),
                )
            key = (self._type_key(character_type), requested)
            if key not in self._action_cache:
                self._action_cache[key] = actions[requested]
            return self._action_cache[key]

        action_name = ALIASES.get(action_name, action_name)

        key = (
            character_type,
            action_name
        )

        if key in self._action_cache:
            return self._action_cache[key]

        path = (
            self._character_dir(character_type)
            / "actions"
            / f"{action_name}.json"
        )

        if not path.exists():
            available = self.actions_for(
                character_type
            )

            raise FileNotFoundError(
                f"Acción '{action_name}' no existe para "
                f"'{character_type}'. Disponibles: {available}"
            )

        data = self._read_json(path)
        self._action_cache[key] = data

        return data

    def sprite_frame(self, character_type, action_name, t, fps=None):
        data = self._sheet_data(character_type)
        action = self.action(character_type, action_name)
        frames = action.get("frames", [])
        if not isinstance(frames, list) or not frames:
            raise ValueError(
                f"La acción '{action_name}' no contiene frames"
            )

        frame_count = min(
            len(frames),
            max(1, int(action.get("frameCount", len(frames)))),
        )
        rate = float(fps or action.get("frameRate") or data["default_fps"] or 8.0)
        elapsed_frame = int(max(0.0, float(t)) * rate)
        if frame_count == 1:
            frame_index = 0
        elif action.get("loop", True):
            frame_index = elapsed_frame % frame_count
        else:
            # Las acciones de una sola ejecución terminan en su último frame.
            frame_index = min(elapsed_frame, frame_count - 1)
        frame_spec = frames[frame_index]
        x = int(frame_spec.get("x", 0))
        y = int(frame_spec.get("y", 0))
        frame_width = data["frame_width"]
        frame_height = data["frame_height"]
        cache_key = (self._type_key(character_type), str(action.get("name", action_name)), frame_index)

        if cache_key not in self._sheet_frame_cache:
            image = data["image"]
            if x < 0 or y < 0 or x + frame_width > image.width or y + frame_height > image.height:
                raise ValueError(
                    f"Frame fuera del charset en acción '{action_name}': ({x}, {y})"
                )
            self._sheet_frame_cache[cache_key] = image.crop(
                (x, y, x + frame_width, y + frame_height)
            )
        return self._sheet_frame_cache[cache_key]

    def sprite_frame_size(self, character_type):
        data = self._sheet_data(character_type)
        return data["frame_width"], data["frame_height"]

    # ============================================================
    # SPRITES
    # ============================================================

    def sprite(
        self,
        character_type,
        sprite_name
    ):
        key = (
            character_type,
            sprite_name
        )

        if key in self._sprite_cache:
            return self._sprite_cache[key]

        path = (
            self._character_dir(character_type)
            / sprite_name
        )

        if not path.exists():
            raise FileNotFoundError(
                f"Sprite '{sprite_name}' no existe para "
                f"'{character_type}'"
            )

        image = Image.open(path).convert("RGBA")
        self._sprite_cache[key] = image

        return image

    # ============================================================
    # EMOTIONS
    # ============================================================

    def emotion(
        self,
        emotion_name
    ):
        if emotion_name in self._emotion_cache:
            return self._emotion_cache[emotion_name]

        path = (
            self.root
            / "ui"
            / "emotions"
            / f"{emotion_name}.png"
        )

        if not path.exists():
            available = self.emotions()

            raise FileNotFoundError(
                f"Emoción '{emotion_name}' no existe. "
                f"Disponibles: {available}"
            )

        image = Image.open(path).convert("RGBA")
        self._emotion_cache[emotion_name] = image

        return image

    # ============================================================
    # CATÁLOGO DINÁMICO
    # ============================================================

    def backgrounds(self):
        backgrounds_dir = (
            self.root
            / "backgrounds"
        )

        if not backgrounds_dir.exists():
            return []

        return sorted(
            p.stem
            for p in backgrounds_dir.glob("*.png")
        )

    def emotions(self):
        emotions_dir = (
            self.root
            / "ui"
            / "emotions"
        )

        if not emotions_dir.exists():
            return []

        return sorted(
            p.stem
            for p in emotions_dir.glob("*.png")
        )

    def character_types(self):
        characters_dir = (
            self.root
            / "characters"
        )

        if not characters_dir.exists():
            return []

        return sorted(
            p.name
            for p in characters_dir.iterdir()
            if p.is_dir()
            and (
                (p / "rig.json").exists()
                or (
                    (p / "actions.json").is_file()
                    and self._sheet_image_path(
                        p,
                        self._read_json(p / "actions.json"),
                    ) is not None
                )
            )
        )

    def actions_for(
        self,
        character_type
    ):
        if self.is_sprite_sheet(character_type):
            return list(
                self._sheet_data(character_type)["animations"].keys()
            )

        actions_dir = self._character_dir(character_type) / "actions"

        if not actions_dir.exists():
            return []

        return sorted(
            p.stem
            for p in actions_dir.glob("*.json")
        )

    def catalog(self):
        # El catálogo cambia solo cuando agregas/quitas assets. Durante una
        # ejecución de Mini Clip Maker no necesitamos reconstruirlo.
        if self._catalog_cache is not None:
            return self._catalog_cache

        characters = {}
        character_parts = {}

        for character_type in self.character_types():
            characters[character_type] = self.actions_for(
                character_type
            )
            character_parts[character_type] = (
                []
                if self.is_sprite_sheet(character_type)
                else [
                    part.get("name", "")
                    for part in self.rig(character_type).get("parts", [])
                    if part.get("name")
                ]
            )

        self._catalog_cache = {
            "backgrounds": self.backgrounds(),
            "characters": characters,
            "character_parts": character_parts,
            "emotions": self.emotions(),
        }

        return self._catalog_cache

    # ============================================================
    # CACHE CONTROL
    # ============================================================

    def clear_cache(self):
        """Útil solo si cambias assets mientras el proceso sigue abierto."""
        self._background_cache.clear()
        self._rig_cache.clear()
        self._action_cache.clear()
        self._sprite_cache.clear()
        self._emotion_cache.clear()
        self._sheet_cache.clear()
        self._sheet_frame_cache.clear()
        self._sheet_type_cache.clear()
        self._catalog_cache = None
