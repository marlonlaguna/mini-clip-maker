"""Catálogo de sprites por acción. Los personajes articulados ya no se cargan."""
from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path
from PIL import Image
from .utils import ASSETS_DIR

CATEGORIES = ("humanoids", "non-humanoids", "objects")
AUTO_FRAME_SIZES = frozenset({200, 400, 512, 1024})
FRAME_SUFFIX = re.compile(r"^(?P<name>.+)@(?P<w>[1-9]\d*)x(?P<h>[1-9]\d*)$", re.I)
ALIASES = {
    "none": "idle", "stand": "idle", "walk_front": "front_walk",
    "walk_back": "back_walk", "walk_left": "walk", "walk_right": "walk",
    "side_walk": "walk", "speak": "speak_front", "talk": "speak_front",
    "speaking": "speak_front", "turn_around": "turn_arround",
    "shoot": "shooting_a_gun", "point": "side_point", "muerto": "dying",
    "scared": "afraid",
}


class AssetLibrary:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else ASSETS_DIR
        self.clear_cache()

    @staticmethod
    def _type_key(value):
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(c for c in text if not unicodedata.combining(c)).lower()
        return re.sub(r"[^a-z0-9]+", "_", text).strip("_")

    @staticmethod
    def _read_json(path):
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError(f"La configuración debe ser un objeto: {path}")
        return data

    def _directories(self):
        if self._directory_cache is None:
            self._directory_cache = {}
            for category in CATEGORIES:
                folder = self.root / "characters" / category
                if folder.is_dir():
                    for path in sorted(folder.iterdir()):
                        if path.is_dir() and not path.name.startswith("."):
                            self._directory_cache[f"{category}/{path.name}"] = path
        return self._directory_cache

    def resolve_character(self, name):
        requested = str(name).strip().replace("\\", "/")
        if requested in self._directories():
            return requested
        matches = [key for key, path in self._directories().items()
                   if self._type_key(path.name) == self._type_key(requested)
                   or self._type_key(key) == self._type_key(requested)]
        if len(matches) != 1:
            raise ValueError(f"Character {'ambiguo' if matches else 'inexistente'}: {name!r}. "
                             f"Usa categoría/nombre. Disponibles: {self.character_types()}")
        return matches[0]

    def _character_dir(self, name):
        return self._directories()[self.resolve_character(name)]

    def character_types(self):
        return sorted(self._directories())

    @staticmethod
    def _animation_map(config):
        raw = config.get("actions", config.get("animations", {}))
        if isinstance(raw, list):
            raw = {a["name"]: a for a in raw if isinstance(a, dict) and "name" in a}
        if not isinstance(raw, dict):
            raise ValueError("actions debe ser un objeto")
        return raw

    @staticmethod
    def _sprite_name(path):
        """Separa la acción lógica del sufijo opcional @anchoXalto."""
        stem = Path(path).stem
        match = FRAME_SUFFIX.fullmatch(stem)
        if match:
            return match["name"], (int(match["w"]), int(match["h"]))
        return stem, None

    @staticmethod
    def _configured_frame_size(value):
        if not isinstance(value, dict) or set(value) != {"width", "height"}:
            raise ValueError("frameSize de la acción debe contener width y height")
        values = (value["width"], value["height"])
        if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in values):
            raise ValueError("frameSize debe usar enteros positivos")
        return values

    def _frame_geometry(self, path, category, spec):
        with Image.open(path) as image:
            width, height = image.size
        _, suffix_size = self._sprite_name(path)
        configured = self._configured_frame_size(spec["frameSize"]) if "frameSize" in spec else None
        if configured and suffix_size and configured != suffix_size:
            raise ValueError(f"{path}: frameSize y el sufijo del archivo no coinciden")
        explicit = configured or suffix_size
        if explicit:
            fw, fh = explicit
        elif category == "objects":
            # Conserva los objetos estáticos existentes; las tiras grandes de
            # objetos requieren sufijo para no reinterpretar una imagen vieja.
            fw, fh = (200, 200) if height == 200 and width % 200 == 0 else (width, height)
        elif height in AUTO_FRAME_SIZES:
            fw = fh = height
        else:
            raise ValueError(f"{path}: esperado alto 200, 400, 512 o 1024; "
                             "para otros tamaños usa @ANCHOxALTO o frameSize por acción")
        if height != fh or width < fw or width % fw:
            raise ValueError(f"{path}: esperado una tira horizontal de celdas {fw}×{fh}; recibido {width}×{height}")
        return fw, fh, width // fw

    def _action_path(self, folder, filename, files):
        if not isinstance(filename, str) or Path(filename).name != filename or "\\" in filename:
            raise ValueError(f"file debe estar en la carpeta del character: {filename}")
        path = folder / filename
        if path.is_file():
            return path
        logical, explicit = self._sprite_name(filename)
        if explicit:
            return None
        candidates = [p for p in files.values() if self._sprite_name(p)[0] == logical]
        if len(candidates) > 1:
            raise ValueError(f"Acción ambigua {logical!r}: especifica file o conserva una única tira por acción")
        return candidates[0] if candidates else None

    def _character_data(self, name):
        key = self.resolve_character(name)
        if key in self._character_cache:
            return self._character_cache[key]
        category = key.split("/", 1)[0]
        folder = self._directories()[key]
        common = {}
        if category == "humanoids":
            common_path = folder.parent / "actions.json"
            if not common_path.is_file():
                raise FileNotFoundError(f"Falta la configuración común: {common_path}")
            common = self._read_json(common_path)
        specific = {}
        if category != "objects" and (folder / "actions.json").is_file():
            specific = self._read_json(folder / "actions.json")
        if category == "non-humanoids" and not specific:
            raise FileNotFoundError(f"Falta actions.json para {key}")
        defaults = {"fps": 13, "mode": "loop"}
        defaults.update(common.get("defaults", {}))
        defaults.update(specific.get("defaults", {}))
        declarations = {n: dict(v) for n, v in self._animation_map(common).items()}
        for action, value in self._animation_map(specific).items():
            if not isinstance(value, dict):
                raise ValueError(f"Configuración inválida: {key}/{action}")
            declarations[action] = {**declarations.get(action, {}), **value}
        files = {p.stem: p for p in folder.iterdir()
                 if p.is_file() and p.suffix.lower() == ".png"
                 and (category == "objects" or self._sprite_name(p)[0].lower() not in {"modelo", "model", "preview", "reference"})}
        if category == "objects":
            if len(files) != 1:
                raise ValueError(f"{key}: debe contener un único PNG, estático o tira horizontal")
            declarations = {"idle": {"file": next(iter(files.values())).name}}
        else:
            # Las variantes de una acción conocida heredan sus FPS/estado. No
            # exigen repetir configuración por personaje ni por resolución.
            for path in files.values():
                logical, _ = self._sprite_name(path)
                if logical.endswith("_closeup"):
                    base = logical[:-len("_closeup")]
                    source = base if base in declarations else ALIASES.get(base, base)
                    if source in declarations:
                        inherited = {k: v for k, v in declarations[source].items()
                                     if k not in {"file", "frameSize", "movement", "closeup", "view", "forAction"}}
                        declarations[logical] = {**inherited, "view": "portrait", "forAction": source,
                                                 **declarations.get(logical, {})}
        animations = {}
        used_paths = set()
        for action, declaration in declarations.items():
            spec = {**defaults, **declaration}
            filename = spec.get("file", f"{action}.png")
            path = self._action_path(folder, filename, files)
            if path is None:
                continue
            fw, fh, count = self._frame_geometry(path, category, spec)
            rate = float(spec.get("fps", 13))
            mode = spec.get("mode", "loop")
            view = spec.get("view", "portrait" if action.endswith("_closeup") else "body")
            if view not in {"body", "portrait"}:
                raise ValueError(f"view inválido en {key}/{action}: usa body o portrait")
            for field in ("closeup", "forAction"):
                if field in spec and (not isinstance(spec[field], str) or not spec[field]):
                    raise ValueError(f"{field} debe ser un nombre de acción en {key}/{action}")
            if not math.isfinite(rate) or rate <= 0 or mode not in {"loop", "hold", "once"}:
                raise ValueError(f"FPS o mode inválidos en {key}/{action}")
            animations[action] = {
                **spec, "name": action, "file": path, "fps": rate, "mode": mode,
                "view": view,
                "loop": mode == "loop", "frameCount": count,
                "frame_width": fw, "frame_height": fh, "duration": count / rate,
            }
            used_paths.add(path)
        if not animations:
            raise ValueError(f"No hay acciones configuradas con PNG válido en {folder}")
        extras = [p.name for p in files.values() if p not in used_paths]
        if extras:
            raise ValueError(f"{key}: configura estas acciones específicas en actions.json: {extras}")
        self._character_cache[key] = {"category": category, "actions": animations}
        return self._character_cache[key]

    def is_sprite_sheet(self, character_type):
        self._character_data(character_type)
        return True

    def actions_for(self, character_type):
        return sorted(self._character_data(character_type)["actions"])

    def action(self, character_type, action_name):
        actions = self._character_data(character_type)["actions"]
        requested = str(action_name or "idle").strip()
        if requested not in actions:
            requested = ALIASES.get(requested, requested)
        if requested not in actions:
            raise ValueError(f"Acción {action_name!r} no disponible para {character_type}. Disponibles: {sorted(actions)}")
        return actions[requested]

    def default_action(self, character_type):
        data = self._character_data(character_type)["actions"]
        actions = sorted(name for name, action in data.items() if action["view"] == "body") or sorted(data)
        return "idle" if "idle" in actions else actions[0]

    def closeup_action(self, character_type, action_name):
        action = self.action(character_type, action_name)
        actions = self._character_data(character_type)["actions"]
        if action["view"] == "portrait":
            return action["name"]
        candidates = [action.get("closeup"), action["name"] + "_closeup"]
        source_name, _ = self._sprite_name(action["file"])
        if source_name != action["name"]:
            candidates.append(source_name + "_closeup")
        if action["name"].startswith("speak_"):
            candidates.append("speak_closeup")
        for name in candidates:
            if name in actions and actions[name]["view"] == "portrait":
                return name
        custom = [name for name, variant in actions.items()
                  if variant["view"] == "portrait" and variant.get("forAction") == action["name"]]
        if len(custom) > 1:
            raise ValueError(f"Variantes de primer plano ambiguas para {character_type}/{action_name}: {custom}")
        return custom[0] if custom else None

    def _frame_state(self, character_type, action_name, t, fps=None):
        key = self.resolve_character(character_type)
        action = self.action(key, action_name)
        elapsed = max(0.0, float(t))
        rate = action["fps"] if fps is None else float(fps)
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError("Los FPS de animación deben ser positivos y finitos")
        index = int(elapsed * rate + 1e-8)
        count = action["frameCount"]
        if action["mode"] == "once" and index >= count:
            default = self.default_action(key)
            if action["view"] == "portrait":
                default = self.closeup_action(key, default) or default
            if default != action["name"]:
                return self._frame_state(key, default, elapsed - count / rate)
            index = 0
        elif action["mode"] == "loop":
            index %= count
        else:
            index = min(index, count - 1)
        return action, index

    def sprite_sample(self, character_type, action_name, t, fps=None, facing="right"):
        """Devuelve imagen y metadata de la acción efectiva, incluido once→idle."""
        key = self.resolve_character(character_type)
        action, index = self._frame_state(key, action_name, t, fps)
        cache_key = (key, action["name"], index, facing == "left")
        if cache_key not in self._frame_cache:
            path = action["file"]
            if path not in self._image_cache:
                with Image.open(path) as im:
                    self._image_cache[path] = im.convert("RGBA")
            w, h = action["frame_width"], action["frame_height"]
            frame = self._image_cache[path].crop((index * w, 0, (index + 1) * w, h))
            if facing == "left":
                frame = frame.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            frame.info["sprite_frame_key"] = cache_key
            self._frame_cache[cache_key] = frame
        return self._frame_cache[cache_key], action

    def sprite_frame(self, character_type, action_name, t, fps=None, facing="right"):
        return self.sprite_sample(character_type, action_name, t, fps, facing)[0]

    def sprite_frame_size(self, character_type, action_name=None):
        action = self.action(character_type, action_name or self.default_action(character_type))
        return action["frame_width"], action["frame_height"]

    def background(self, name):
        if name not in self.backgrounds():
            raise FileNotFoundError(f"Background {name!r} no existe. Disponibles: {self.backgrounds()}")
        if name not in self._background_cache:
            with Image.open(self.root / "backgrounds" / f"{name}.png") as im:
                self._background_cache[name] = im.convert("RGBA")
        return self._background_cache[name]

    def emotion(self, name):
        if name not in self.emotions():
            raise FileNotFoundError(f"Emoción no disponible: {name}")
        if name not in self._emotion_cache:
            with Image.open(self.root / "ui" / "emotions" / f"{name}.png") as im:
                self._emotion_cache[name] = im.convert("RGBA")
        return self._emotion_cache[name]

    def backgrounds(self):
        return sorted(p.stem for p in (self.root / "backgrounds").glob("*.png"))

    def emotions(self):
        return sorted(p.stem for p in (self.root / "ui" / "emotions").glob("*.png"))

    def catalog(self):
        if self._catalog_cache is None:
            characters = {name: self.actions_for(name) for name in self.character_types()}
            self._catalog_cache = {
                "backgrounds": self.backgrounds(), "characters": characters,
                "character_parts": {name: [] for name in characters}, "emotions": self.emotions(),
            }
        return self._catalog_cache

    def compact_catalog(self, character_types=None):
        """Acciones humanoides comunes una vez; extras por character del cast."""
        selected = [self.resolve_character(n) for n in character_types] if character_types is not None else self.character_types()
        selected = list(dict.fromkeys(selected))
        common_path = self.root / "characters" / "humanoids" / "actions.json"
        common = sorted(name for name, spec in self._animation_map(self._read_json(common_path)).items()
                        if spec.get("view") != "portrait" and not name.endswith("_closeup")) if common_path.is_file() else []
        result = {"humanoid_actions": common, "characters": {}}
        for name in selected:
            data = self._character_data(name)
            actions = {name for name, action in data["actions"].items() if action["view"] != "portrait"}
            if data["category"] == "humanoids":
                result["characters"][name] = {"category": "humanoids", "extra_actions": sorted(actions - set(common))}
                missing = sorted(set(common) - actions)
                if missing:
                    result["characters"][name]["missing_actions"] = missing
            else:
                result["characters"][name] = {"category": data["category"], "actions": sorted(actions)}
        return result

    def clear_cache(self):
        self._directory_cache = None
        self._character_cache = {}
        self._image_cache = {}
        self._frame_cache = {}
        self._background_cache = {}
        self._emotion_cache = {}
        self._catalog_cache = None
