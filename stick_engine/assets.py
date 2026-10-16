import json
from pathlib import Path

from PIL import Image

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
            self.root
            / "characters"
            / character_type
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
        action_name = ALIASES.get(
            action_name,
            action_name
        )

        key = (
            character_type,
            action_name
        )

        if key in self._action_cache:
            return self._action_cache[key]

        path = (
            self.root
            / "characters"
            / character_type
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
            self.root
            / "characters"
            / character_type
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
            and (p / "rig.json").exists()
        )

    def actions_for(
        self,
        character_type
    ):
        actions_dir = (
            self.root
            / "characters"
            / character_type
            / "actions"
        )

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
            character_parts[character_type] = [
                part.get("name", "")
                for part in self.rig(character_type).get("parts", [])
                if part.get("name")
            ]

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
        self._catalog_cache = None
