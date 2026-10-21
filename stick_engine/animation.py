from .utils import lerp


# The legacy character rigs have a 454 px visible idle height after trimming
# their transparent canvas. Scale sprite-sheet cells to that same reference.
SPRITE_SHEET_REFERENCE_HEIGHT = 454.0


def sprite_sheet_scale(actor_scale, frame_height):
    return float(actor_scale) * SPRITE_SHEET_REFERENCE_HEIGHT / max(
        1.0,
        float(frame_height),
    )


def sprite_focus_bounds(target, width, height):
    """Approximate legacy close-up targets inside a full-body sprite cell."""
    target = str(target or "full_body").strip().lower()
    regions = {
        "face": (0.18, 0.02, 0.82, 0.34),
        "head": (0.18, 0.02, 0.82, 0.34),
        "torso": (0.12, 0.24, 0.88, 0.67),
        "left_arm": (0.05, 0.20, 0.95, 0.66),
        "right_arm": (0.05, 0.20, 0.95, 0.66),
        "arms": (0.05, 0.20, 0.95, 0.66),
        "left_leg": (0.08, 0.48, 0.92, 0.98),
        "right_leg": (0.08, 0.48, 0.92, 0.98),
        "legs": (0.08, 0.48, 0.92, 0.98),
    }
    region = regions.get(target)
    if region is None:
        return None
    left, top, right, bottom = region
    return (
        left * width,
        top * height,
        right * width,
        bottom * height,
    )

def sample_action(action, t):
    duration = max(float(action.get("duration", 1.0)), 0.001)
    local_t = t % duration if action.get("loop", True) else min(max(t, 0.0), duration)

    frames = sorted(
        action.get("keyframes", [{"time": 0.0}]),
        key=lambda x: float(x.get("time", 0.0))
    )

    if len(frames) == 1:
        return {
            k: float(v)
            for k, v in frames[0].items()
            if k != "time" and isinstance(v, (int, float))
        }

    a, b = frames[0], frames[-1]
    for i in range(len(frames) - 1):
        fa, fb = frames[i], frames[i + 1]
        ta, tb = float(fa.get("time", 0)), float(fb.get("time", duration))
        if ta <= local_t <= tb:
            a, b = fa, fb
            break

    ta = float(a.get("time", 0))
    tb = float(b.get("time", ta))
    mix = 0.0 if tb <= ta else (local_t - ta) / (tb - ta)

    result = {}
    for key in (set(a) | set(b)) - {"time"}:
        av = a.get(key, 0.0)
        bv = b.get(key, av)
        if isinstance(av, (int, float)) and isinstance(bv, (int, float)):
            result[key] = lerp(float(av), float(bv), mix)
    return result
