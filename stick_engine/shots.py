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
