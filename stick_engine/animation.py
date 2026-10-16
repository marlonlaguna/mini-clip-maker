from .utils import lerp

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
