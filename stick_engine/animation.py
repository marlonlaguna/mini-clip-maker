"""Orientación, reproducción y desplazamiento independientes del FPS del video."""
from .utils import clamp, smoothstep

SPRITE_SHEET_REFERENCE_HEIGHT = 454.0
# Sobre el tamaño previo: reducción del 7%, seguida de otro 10%.
CHARACTER_SIZE_FACTOR = 0.90 * 0.93 * 0.90
GROUP_EDGE_DROP = 0.06


def sprite_sheet_scale(actor_scale, frame_height):
    return float(actor_scale) * SPRITE_SHEET_REFERENCE_HEIGHT / max(1.0, float(frame_height))


def resolve_facings(characters):
    ordered = sorted(characters, key=lambda c: int(c.get("position", 1)))
    middle = (len(ordered) - 1) / 2.0
    screen_order = sorted(range(len(ordered)), key=lambda i: float(ordered[i].get("x", (i + 0.5) / max(1, len(ordered)))))
    rank = {index: place for place, index in enumerate(screen_order)}
    result = []
    for i, original in enumerate(ordered):
        spec = dict(original)
        explicit = spec.get("facing", "auto")
        explicit = {"izquierda": "left", "derecha": "right", "default": "right"}.get(explicit, explicit)
        if explicit not in {"auto", "left", "right", None, ""}:
            raise ValueError(f"Orientación inválida: {explicit}")
        spec["facing"] = explicit if explicit in {"left", "right"} else ("left" if rank[i] > middle else "right")
        # Curva simétrica según el orden real en pantalla. Con número par,
        # los dos del centro comparten altura. Y explícita tiene prioridad.
        nearest = 0.0 if len(ordered) % 2 else 0.5
        spec["_ground_offset"] = (
            GROUP_EDGE_DROP * ((abs(rank[i] - middle) - nearest) / (middle - nearest)) ** 2
            if len(ordered) >= 3 else 0.0
        )
        result.append(spec)
    return result


def actor_transform(spec, action, t, width, height, duration):
    """Devuelve dx, dy, escala de profundidad. Velocidad en px/s a 1080p."""
    movement = spec.get("movement")
    automatic = action.get("movement", {})
    if movement is None:
        movement = automatic
    if not movement:
        return 0.0, 0.0, 1.0
    elapsed = max(0.0, t - float(movement.get("start", 0)))
    if movement is automatic and action.get("mode") != "loop":
        elapsed = min(elapsed, action["duration"])
    direction = movement.get("direction", "facing")
    if direction == "facing":
        direction = spec.get("facing", "right")
    if "distance" in movement:
        progress = clamp(elapsed / max(0.001, float(movement.get("duration", duration))), 0, 1)
        if movement.get("easing") == "smooth":
            progress = smoothstep(progress)
        pixels = float(movement["distance"]) * width * progress
    else:
        pixels = float(movement.get("speed", 24)) * width / 1080.0 * elapsed
    if direction in {"left", "right"}:
        return pixels * (-1 if direction == "left" else 1), 0.0, 1.0
    if direction in {"up", "away", "back", "down", "toward", "front"}:
        sign = -1 if direction in {"up", "away", "back"} else 1
        depth = clamp(1 + sign * float(movement.get("depth_rate", 0.035)) * elapsed, 0.78, 1.22)
        return 0.0, sign * pixels * height / max(1, width) * 0.35, depth
    raise ValueError(f"Dirección de desplazamiento inválida: {direction}")


def actor_layout(spec, action, t, width, height, duration, slot, ground, scale, frame_size):
    dx, dy, depth = actor_transform(spec, action, t, width, height, duration)
    scale *= depth * float(spec.get("scale", 1.0))
    w, h = frame_size
    sheet_scale = sprite_sheet_scale(scale, h)
    aw, ah = w * sheet_scale, h * sheet_scale
    center = float(spec.get("x", slot / width)) * width + dx
    ground = float(spec.get("y", ground / height)) * height + dy
    if "y" not in spec:
        ground += float(spec.get("_ground_offset", 0.0)) * height
    # Los márgenes transparentes del frame pueden salir del encuadre.
    # Limitar por el lienzo entero amontonaba los sprites grandes en el centro.
    if aw > width * 0.84:
        center = clamp(center, width * 0.08, width * 0.92)
    else:
        center = clamp(center, min(aw / 2, width / 2), max(width - aw / 2, width / 2))
    ground = clamp(ground, min(ah, height), height * 0.96)
    # Reducir después de fijar el centro y el suelo evita cambiar de límites
    # de posición cuando el tamaño cruza el ancho permitido del encuadre.
    aw *= CHARACTER_SIZE_FACTOR
    ah *= CHARACTER_SIZE_FACTOR
    scale *= CHARACTER_SIZE_FACTOR
    return center - aw / 2, ground - ah, aw, ah, scale


def sprite_focus_bounds(target, width, height, image=None, view="body"):
    """Encuadre aproximado sobre la zona ocupada del frame."""
    regions = {
        "face": (0.20, 0.0, 0.80, 0.30), "head": (0.20, 0.0, 0.80, 0.30),
        "torso": (0.12, 0.22, 0.88, 0.67),
        "left_arm": (0.0, 0.2, 1.0, 0.67), "right_arm": (0.0, 0.2, 1.0, 0.67),
        "arms": (0.0, 0.2, 1.0, 0.67),
        "left_leg": (0.05, 0.48, 0.95, 1.0), "right_leg": (0.05, 0.48, 0.95, 1.0),
        "legs": (0.05, 0.48, 0.95, 1.0),
    }
    region = regions.get(str(target))
    if region is None:
        return None
    left, top, right, bottom = (0, 0, width, height)
    if image is not None and image.getbbox():
        left, top, right, bottom = image.getbbox()
    if view == "portrait" and target in {"face", "head"}:
        return left, top, right, bottom
    rw, rh = right - left, bottom - top
    a, b, c, d = region
    return left + a * rw, top + b * rh, left + c * rw, top + d * rh
