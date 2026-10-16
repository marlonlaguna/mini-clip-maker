"""Camera shot targets for articulated character rigs."""

from __future__ import annotations

import re


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


def parts_for_target(target, available_parts):
    """Map a semantic shot target to actual part names in a rig."""
    target = normalize_shot(target)["target"]
    names = set(available_parts)
    if target == "full_body":
        return None

    tokens = {
        name: set(re.findall(r"[a-z0-9]+", name.lower()))
        for name in names
    }

    def choose(predicate):
        return {name for name, parts in tokens.items() if predicate(name, parts)}

    if target in {"face", "head"}:
        selected = choose(lambda name, parts: "head" in parts or "face" in parts)
    elif target == "torso":
        selected = choose(lambda name, parts: bool(parts & {"torso", "body"}))
    elif target in {"left_arm", "right_arm", "arms"}:
        sides = {"left", "right"} if target == "arms" else {target.split("_", 1)[0]}
        selected = choose(
            lambda name, parts: bool(parts & sides)
            and bool(parts & {"arm", "upper", "forearm", "hand"})
        )
    else:
        sides = {"left", "right"} if target == "legs" else {target.split("_", 1)[0]}
        selected = choose(
            lambda name, parts: bool(parts & sides)
            and bool(parts & {"leg", "thigh", "shin", "foot", "front", "back"})
        )

    return selected or None
