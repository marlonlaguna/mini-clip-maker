"""Camera shot targets for sprites."""

from __future__ import annotations

SHOT_TARGETS = {
    "full_body",
    "face",
    "head",
    "torso",
    "left_arm",
    "right_arm",
    "arms",
    "left_leg",
    "right_leg",
    "legs",
}


def normalize_shot(shot):
    """Return a validated shot descriptor, keeping old scenes compatible."""
    if isinstance(shot, str):
        shot = {"target": shot}
    if not isinstance(shot, dict):
        shot = {}

    target = str(shot.get("target", "full_body")).strip().lower()
    aliases = {
        "wide": "full_body",
        "full": "full_body",
        "close_up": "face",
        "closeup": "face",
        "face_close_up": "face",
        "arm_left": "left_arm",
        "arm_right": "right_arm",
        "leg_left": "left_leg",
        "leg_right": "right_leg",
    }
    target = aliases.get(target, target)
    if target not in SHOT_TARGETS:
        target = "full_body"

    character = shot.get("character")
    character = str(character).strip() if character is not None else ""
    if target == "full_body":
        character = ""

    return {
        "target": target,
        "character": character or None,
    }


def prepare_closeup(assets, prepared_characters, shot, character_id):
    """Resuelve una variante visual sin modificar cast, acción ni guion."""
    if shot["target"] not in {"face", "head"}:
        return None
    target = next((item for item in prepared_characters if item["spec"].get("id") == character_id), None)
    if target is None:
        return None
    name = assets.closeup_action(target["char_type"], target["action_name"])
    if name is None:
        print(f"[STICK] AVISO: {character_id}/{target['action_name']} sin variante closeup; se conserva el acercamiento habitual.")
        return None
    action = assets.action(target["char_type"], name)
    print(f"[STICK] Primer plano HD de {character_id}: {action['file'].name}, "
          f"{action['frame_width']}×{action['frame_height']}, {action['fps']:g} FPS.")
    return {"target": target, "action_name": name}


def speech_sample(assets, char_type, action_name, spec, t):
    """Cierra la boca al escuchar o durante pausas, sin alterar otras acciones."""
    if action_name.startswith("speak") and "speech_intervals" in spec:
        active = any(start <= t < end for start, end in spec["speech_intervals"])
        if not active:
            action = assets.action(char_type, action_name)
            if "idle" in assets.actions_for(char_type):
                idle = "idle"
                if action["view"] == "portrait":
                    idle = assets.closeup_action(char_type, "idle")
                if idle is not None:
                    return assets.sprite_sample(char_type, idle, t, facing=spec["facing"])
            # Sin idle compatible se mantiene el primer frame; nunca se sustituye
            # un retrato HD por un cuerpo completo de otro tamaño.
            t = 0.0
    return assets.sprite_sample(char_type, action_name, t, facing=spec["facing"])


def closeup_sample(assets, closeup, t):
    if closeup is None:
        return None
    target = closeup["target"]
    image, action = speech_sample(assets, target["char_type"], closeup["action_name"], target["spec"], t)
    return (image, action) if action["view"] == "portrait" else None


def portrait_layout(image, width, height, scale=1.0):
    """Ancla el busto al borde inferior, con escala estable entre frames."""
    factor = min(width * 1.50 / image.width, height * 0.90 / image.height) * float(scale)
    w, h = image.width * factor, image.height * factor
    overscan = max(2.0, height * 0.005)
    return (width - w) / 2.0, height - h + overscan, w, h
