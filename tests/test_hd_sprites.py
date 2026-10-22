"""Dimensiones variables y primeros planos sin modificar guiones ni assets reales."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stick_engine.assets import AssetLibrary
from stick_engine.animation import actor_layout, sprite_focus_bounds, sprite_sheet_scale
from stick_engine.shots import prepare_closeup, closeup_sample, portrait_layout


def make_strip(path, size=(200, 200), count=3):
    w, h = size
    image = Image.new("RGBA", (w * count, h))
    draw = ImageDraw.Draw(image)
    for i in range(count):
        x = i * w
        draw.rectangle((x, 0, x + w - 1, h - 1), fill=(30 + i * 5, 80, 210, 255))
        draw.rectangle((x, 0, x + w - 1, h // 8), fill=(240, 35, 30, 255))
        draw.rectangle((x, h * 7 // 8, x + w - 1, h - 1), fill=(35, 230, 45, 255))
        draw.rectangle((x + w // 8, h // 3, x + w // 4, h * 2 // 3), fill=(250, 220, 20, 255))
    image.save(path)


@pytest.fixture
def assets(tmp_path):
    root = tmp_path / "assets"
    char = root / "characters" / "humanoids" / "hero"
    char.mkdir(parents=True)
    config = {"frameSize": {"width": 200, "height": 200},
              "defaults": {"fps": 13, "mode": "loop"}, "actions": {
        "idle": {}, "speak_front": {}, "speak_side": {},
        "afraid": {"mode": "hold"}, "point": {"mode": "once"},
        "walk": {"movement": {"direction": "facing", "speed": 26}},
        "side_walk": {"file": "walk.png"},
    }}
    (char.parent / "actions.json").write_text(json.dumps(config))
    for name in config["actions"]:
        if name != "side_walk":
            make_strip(char / f"{name}.png")
    (root / "backgrounds").mkdir()
    Image.new("RGB", (180, 320), (55, 55, 60)).save(root / "backgrounds" / "room.png")
    return AssetLibrary(root)


@pytest.mark.parametrize("side", [200, 400, 512, 1024])
def test_square_detection_preserves_configured_fps_and_state(assets, side):
    make_strip(assets._character_dir("hero") / "afraid.png", (side, side), 4)
    assets.clear_cache()
    action = assets.action("hero", "afraid")
    assert (action["frame_width"], action["frame_height"], action["frameCount"]) == (side, side, 4)
    assert action["mode"] == "hold" and action["fps"] == 13
    assert assets.sprite_frame("hero", "afraid", 100).getpixel((side // 2, side // 2))[0] == 45


def test_rectangular_suffix_preserves_action_name_alias_and_scale(assets):
    folder = assets._character_dir("hero")
    (folder / "walk.png").unlink()
    make_strip(folder / "walk@400x200.png", (400, 200), 8)
    assets.clear_cache()
    assert assets.action("hero", "walk")["frameCount"] == 8
    assert assets.action("hero", "side_walk")["frameCount"] == 8
    assert assets.sprite_frame("hero", "walk_left", .2).size == (400, 200)
    assert "walk@400x200" not in assets.actions_for("hero")
    make_strip(folder / "walk_closeup@512x512.png", (512,512))
    assets.clear_cache()
    assert assets.closeup_action("hero", "side_walk") == "walk_closeup"
    # El tamaño físico del lienzo normalizado no cambia al duplicar resolución.
    assert sprite_sheet_scale(.8, 200) * 200 == sprite_sheet_scale(.8, 1024) * 1024


def test_frame_size_override_and_conflicting_suffix(assets):
    folder = assets._character_dir("hero")
    make_strip(folder / "walk.png", (400, 200), 5)
    config = {"actions": {"walk": {"frameSize": {"width": 400, "height": 200}}}}
    (folder / "actions.json").write_text(json.dumps(config))
    assets.clear_cache()
    assert assets.action("hero", "walk")["frameCount"] == 5
    (folder / "walk.png").rename(folder / "walk@200x200.png")
    assets.clear_cache()
    with pytest.raises(ValueError, match="no coinciden"):
        assets.actions_for("hero")


def test_bad_dimensions_and_ambiguous_files_are_rejected(assets):
    folder = assets._character_dir("hero")
    (folder / "walk.png").unlink()
    make_strip(folder / "walk@400x200.png", (400, 200))
    make_strip(folder / "walk@512x512.png", (512, 512))
    assets.clear_cache()
    with pytest.raises(ValueError, match="ambigua"):
        assets.action("hero", "walk")
    (folder / "walk@512x512.png").unlink()
    Image.new("RGBA", (1000, 200)).save(folder / "walk@400x200.png")
    assets.clear_cache()
    with pytest.raises(ValueError, match="esperado"):
        assets.action("hero", "walk")


def test_objects_keep_legacy_static_sizes_and_support_explicit_hd_strips(assets):
    base = assets.root / "characters" / "objects"
    static = base / "picture"; static.mkdir(parents=True)
    animated = base / "fire"; animated.mkdir()
    Image.new("RGBA", (800, 400)).save(static / "picture.png")
    make_strip(animated / "fire@400x400.png", (400, 400), 2)
    assets.clear_cache()
    assert assets.action("picture", "idle")["frameCount"] == 1
    assert assets.sprite_frame("picture", "idle", 0).size == (800, 400)
    assert assets.action("fire", "idle")["frameCount"] == 2


def test_nonhumanoids_accept_variable_size_and_closeup(assets):
    dog = assets.root / "characters" / "non-humanoids" / "dog"
    dog.mkdir(parents=True)
    (dog / "actions.json").write_text(json.dumps({"actions": {"bark": {"fps": 7, "mode": "hold"}}}))
    make_strip(dog / "bark.png", (400, 400))
    make_strip(dog / "bark_closeup@512x512.png", (512, 512))
    assets.clear_cache()
    assert assets.closeup_action("dog", "bark") == "bark_closeup"
    assert assets.action("dog", "bark_closeup")["fps"] == 7
    assert assets.action("dog", "bark_closeup")["mode"] == "hold"


def test_26_hd_frames_are_cropped_individually_and_hidden_from_prompt_catalog(assets):
    folder = assets._character_dir("hero")
    make_strip(folder / "speak_side_closeup@1024x1024.png", (1024, 1024), 26)
    assets.clear_cache()
    action = assets.action("hero", "speak_side_closeup")
    assert action["frameCount"] == 26 and action["duration"] == 2
    assert action["view"] == "portrait"
    assert assets.closeup_action("hero", "speak_side") == "speak_side_closeup"
    frame = assets.sprite_frame("hero", "speak_side_closeup", 25 / 13)
    assert frame.size == (1024, 1024) and frame.getpixel((512, 512))[0] == 155
    assert "speak_side_closeup" not in assets.compact_catalog()["characters"]["humanoids/hero"]["extra_actions"]


def test_variant_inherits_and_can_override_playback(assets):
    folder = assets._character_dir("hero")
    make_strip(folder / "afraid_closeup.png", (512, 512))
    assets.clear_cache()
    assert assets.action("hero", "afraid_closeup")["mode"] == "hold"
    (folder / "actions.json").write_text(json.dumps({"actions": {"afraid_closeup": {"fps": 26, "mode": "loop"}}}))
    assets.clear_cache()
    assert assets.action("hero", "afraid_closeup")["fps"] == 26
    assert assets.action("hero", "afraid_closeup")["mode"] == "loop"


def test_custom_portrait_mapping_is_optional_and_validated(assets):
    folder = assets._character_dir("hero")
    make_strip(folder / "portrait@512x512.png", (512,512))
    (folder / "actions.json").write_text(json.dumps({"actions": {
        "portrait": {"view": "portrait", "forAction": "speak_side", "fps": 20}}}))
    assets.clear_cache()
    assert assets.closeup_action("hero", "speak_side") == "portrait"
    assert assets.action("hero", "portrait")["fps"] == 20
    (folder / "actions.json").write_text(json.dumps({"actions": {
        "portrait": {"view": "portrait", "forAction": []}}}))
    assets.clear_cache()
    with pytest.raises(ValueError, match="forAction"):
        assets.actions_for("hero")


def test_once_returns_to_actual_idle_size_without_changing_actor_center(assets):
    folder = assets._character_dir("hero")
    make_strip(folder / "point.png", (400, 400))
    assets.clear_cache()
    image, action = assets.sprite_sample("hero", "point", 1)
    assert image.size == (200, 200) and action["name"] == "idle"
    x, y, w, h, _ = actor_layout({}, assets.action("hero", "point"), 1, 1080, 1920, 2, 540, 1500, 1, image.size)
    assert x + w / 2 == 540


def test_portrait_once_returns_to_idle_closeup_then_falls_back_if_missing(assets):
    folder = assets._character_dir("hero")
    make_strip(folder / "point_closeup.png", (400, 400))
    make_strip(folder / "idle_closeup.png", (512, 512))
    assets.clear_cache()
    image, action = assets.sprite_sample("hero", "point_closeup", 1)
    assert action["name"] == "idle_closeup" and image.size == (512, 512)
    (folder / "idle_closeup.png").unlink()
    assets.clear_cache()
    prepared = [{"char_type": "hero", "action_name": "point", "spec": {"id": "listener", "facing": "right"}}]
    closeup = prepare_closeup(assets, prepared, {"target": "face"}, "listener")
    assert closeup_sample(assets, closeup, 0) is not None
    assert closeup_sample(assets, closeup, 1) is None


def test_closeup_targets_listener_and_preserves_facing_and_other_shots(assets):
    folder = assets._character_dir("hero")
    make_strip(folder / "idle_closeup.png", (512, 512))
    assets.clear_cache()
    prepared = [
        {"char_type": "hero", "action_name": "speak_side", "spec": {"id": "speaker", "facing": "right"}},
        {"char_type": "hero", "action_name": "idle", "spec": {"id": "listener", "facing": "left"}},
    ]
    closeup = prepare_closeup(assets, prepared, {"target": "face"}, "listener")
    assert closeup["target"]["spec"]["id"] == "listener"
    mirrored = closeup_sample(assets, closeup, 0)[0]
    original = assets.sprite_frame("hero", "idle_closeup", 0)
    assert mirrored.tobytes() == original.transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes()
    assert prepare_closeup(assets, prepared, {"target": "torso"}, "listener") is None
    assert prepare_closeup(assets, prepared, {"target": "full_body"}, "listener") is None
    assert assets.closeup_action("hero", "afraid") is None


def test_portrait_framing_keeps_entire_face_and_stable_canvas(assets):
    first = Image.new("RGBA", (1024, 1024))
    second = first.copy(); second.putpixel((100,100), (255,0,0,255))
    assert portrait_layout(first, 1080, 1920) == portrait_layout(second, 1080, 1920)
    assert sprite_focus_bounds("face", 1024, 1024, view="portrait") == (0,0,1024,1024)
    assert sprite_focus_bounds("face", 200, 200)[3] == 60


@pytest.mark.parametrize("backend", ["cpu", "gpu"])
def test_real_hd_portrait_video_keeps_top_bottom_and_mirror(assets, tmp_path, monkeypatch, backend):
    folder = assets._character_dir("hero")
    make_strip(folder / "idle_closeup@1024x1024.png", (1024, 1024), 26)
    assets.clear_cache()
    if backend == "cpu":
        from stick_engine.renderer import StickRenderer
        renderer = StickRenderer()
    else:
        import moderngl
        create = moderngl.create_standalone_context
        monkeypatch.setattr(moderngl, "create_standalone_context", lambda **kw: create(backend="egl", **kw))
        from stick_engine.renderer_gpu import StickRendererGPU
        try:
            renderer = StickRendererGPU()
        except Exception as exc:
            pytest.skip(f"OpenGL no disponible: {exc}")
    renderer.assets = assets
    texture_sizes = []
    if backend == "gpu":
        original_upload = renderer._pil_to_texture
        def upload(image):
            texture_sizes.append(image.size)
            return original_upload(image)
        monkeypatch.setattr(renderer, "_pil_to_texture", upload)
    monkeypatch.setattr(renderer, "_video_encoder", lambda: ("libx264", "veryfast"))
    scene = {"width": 320, "height": 568, "fps": 30, "duration": .3, "background": "room",
             "characters": [{"id": "speaker", "type": "hero", "action": "speak_side", "position": 1},
                            {"id": "listener", "type": "hero", "action": "idle", "position": 2}],
             "shot": {"target": "face", "character": "listener"}}
    video = tmp_path / f"{backend}.mp4"
    try:
        renderer.render(scene, video)
    finally:
        if hasattr(renderer, "close"):
            renderer.close()
    output = tmp_path / f"{backend}.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-frames:v", "1", str(output)], check=True)
    with Image.open(output) as image:
        x, y, w, h = portrait_layout(Image.new("RGBA", (1024,1024)), 320, 568)
        top = image.getpixel((160, round(y+h*.05)))
        bottom = image.getpixel((160, round(y+h*.95)))
        left = image.getpixel((round(x+w*.18), round(y+h*.5)))
        right = image.getpixel((round(x+w*.82), round(y+h*.5)))
        assert top[0] > 200 and top[1] < 80
        assert bottom[1] > 180 and bottom[0] < 80
        assert left[2] > 150 and right[0] > 200 and right[1] > 180
    if backend == "gpu":
        assert (1024,1024) in texture_sizes
        assert all(w <= 1024 for w, _ in texture_sizes)
