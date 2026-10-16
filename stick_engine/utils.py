from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = ENGINE_DIR / "assets"

COLORS = {
    "blue": (60, 130, 245, 255),
    "red": (235, 75, 65, 255),
    "green": (70, 180, 95, 255),
    "yellow": (245, 205, 70, 255),
    "orange": (245, 145, 55, 255),
    "purple": (155, 90, 210, 255),
    "pink": (235, 110, 165, 255),
    "brown": (160, 105, 60, 255),
    "black": (35, 35, 35, 255),
    "white": (245, 245, 245, 255),
    "gray": (130, 130, 130, 255),
    "grey": (130, 130, 130, 255),
}

def parse_color(value):
    value = (value or "black").lower().strip()
    if value in COLORS:
        return COLORS[value]
    if value.startswith("#") and len(value) in (7, 9):
        h = value[1:]
        if len(h) == 6:
            h += "ff"
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4, 6))
    raise ValueError(f"Color no soportado: {value}")

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def lerp(a, b, t):
    return a + (b - a) * t

def smoothstep(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)
