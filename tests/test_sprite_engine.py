"""Pruebas sin llamadas de pago ni modelos descargados; FFmpeg real donde aplica."""
import copy
import importlib
import json
import subprocess
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stick_engine.assets import AssetLibrary
from stick_engine.animation import actor_transform, actor_layout, resolve_facings
from guion_escenas import (parse_cast, parse_scenes, serialize_scenes, preparar_guion_visual,
                          storyboard_from_script, explicit_script, validate_scenes)
from guion_audio import parsear_bloques_audio, limpiar_guion_audio, formatear_guion_audio
from audio_timeline import assemble_audio


def strip(path, count=3):
    image = Image.new("RGBA", (count * 200, 200))
    for i in range(count):
        image.paste((30 + i * 70, 30, 20, 255), (i*200+20, 20, i*200+90, 190))
    image.save(path)


@pytest.fixture
def assets(tmp_path):
    base = tmp_path / "assets"
    folder = base / "characters" / "humanoids" / "hero"
    folder.mkdir(parents=True)
    config = {"defaults": {"fps": 13}, "actions": {"idle": {"mode": "loop"},
        "walk": {"mode": "loop", "movement": {"direction": "facing", "speed": 26}},
        "fall": {"mode": "hold"}, "point": {"mode": "once"}}}
    (folder.parent / "actions.json").write_text(json.dumps(config))
    for name in config["actions"]:
        strip(folder / f"{name}.png")
    strip(folder / "modelo.png")
    (base / "backgrounds").mkdir()
    Image.new("RGBA", (100, 180), "#6d9fb4").save(base / "backgrounds" / "room.png")
    return AssetLibrary(base)


def test_uploaded_jhon_is_not_changed():
    assets = AssetLibrary()
    assert len(assets.actions_for("jhon")) == 35
    assert assets.action("jhon", "run")["frameCount"] == 12
    assert assets.action("jhon", "idle")["frameCount"] == 8
    assert assets.action("jhon", "idle")["fps"] == 13
    assert "modelo" not in assets.actions_for("jhon")


def test_common_actions_and_overrides(assets):
    folder = assets._character_dir("hero")
    (folder / "actions.json").write_text(json.dumps({"actions": {"walk": {"fps": 7}, "special": {"mode": "hold", "fps": 4}}}))
    strip(folder / "special.png")
    assets.clear_cache()
    assert assets.action("hero", "walk")["fps"] == 7
    assert assets.action("hero", "idle")["fps"] == 13
    assert assets.action("hero", "special")["mode"] == "hold"
    catalog = assets.compact_catalog(["hero", "hero"])
    assert len(catalog["characters"]) == 1
    assert catalog["characters"]["humanoids/hero"]["extra_actions"] == ["special"]


def test_frame_modes_and_mirror(assets):
    pixel = lambda action, time, **kw: assets.sprite_frame("hero", action, time, **kw).getpixel((25,25))
    assert pixel("walk", 3/13) == pixel("walk", 0)
    assert pixel("fall", 10) == pixel("fall", 2/13)
    assert assets.sprite_frame("hero", "point", 3/13).tobytes() == assets.sprite_frame("hero", "idle", 0).tobytes()
    right = assets.sprite_frame("hero", "walk", .1)
    left = assets.sprite_frame("hero", "walk", .1, facing="left")
    assert left.tobytes() == right.transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes()
    assert assets.sprite_frame("hero", "walk", .1, facing="left") is left


def test_strict_dimensions_and_actions(assets):
    with pytest.raises(ValueError, match="no disponible"):
        assets.action("hero", "invented")
    Image.new("RGBA", (500, 200)).save(assets._character_dir("hero") / "walk.png")
    assets.clear_cache()
    with pytest.raises(ValueError, match="esperado"):
        assets.actions_for("hero")


def test_nonhumanoids_and_configless_objects(assets):
    base = assets.root / "characters"
    dog = base / "non-humanoids" / "dog"
    dog.mkdir(parents=True)
    (dog / "actions.json").write_text(json.dumps({"actions": {"bark": {"mode": "once", "fps": 9}}}))
    strip(dog / "bark.png")
    for name, size in (("lamp", (120,180)), ("flame", (600,200))):
        folder = base / "objects" / name
        folder.mkdir(parents=True)
        Image.new("RGBA", size, "red").save(folder / "sprite.png")
    assets.clear_cache()
    assert assets.actions_for("dog") == ["bark"]
    assert assets.action("lamp", "idle")["frameCount"] == 1
    assert assets.action("flame", "idle")["frameCount"] == 3
    assert assets.sprite_frame("lamp", "idle", 10).size == (120,180)


@pytest.mark.parametrize("count,expected", [(1,["right"]),(2,["right","left"]),(3,["right","right","left"]),
    (4,["right","right","left","left"]),(5,["right","right","right","left","left"])])
def test_automatic_orientation(count, expected):
    chars = [{"position":i+1} for i in range(count)]
    assert [c["facing"] for c in resolve_facings(chars)] == expected
    assert all("facing" not in c for c in chars)


def test_explicit_orientation_and_actual_positions():
    chars = [{"position":1,"x":.8},{"position":2,"x":.2}]
    assert [c["facing"] for c in resolve_facings(chars)] == ["left","right"]
    assert resolve_facings([{"position":1,"facing":"left"}])[0]["facing"] == "left"


def test_motion_is_independent_of_frame_rate(assets):
    action = assets.action("hero","walk")
    spec = {"facing":"left"}
    assert actor_transform(spec,action,2,1080,1920,5)[0] == -52
    assert actor_transform(spec,{**action,"fps":130},2,1080,1920,5) == actor_transform(spec,action,2,1080,1920,5)
    for direction, sign in (("toward",1),("away",-1)):
        dx,dy,scale = actor_transform({"movement":{"direction":direction,"speed":20}},action,2,1080,1920,5)
        assert dx == 0 and dy * sign > 0 and (scale-1) * sign > 0
    x,y,w,h,_ = actor_layout(spec,action,500,320,568,500,80,450,.5,(200,200))
    assert x >= 0 and x+w <= 320


def example():
    return ("[ESCENA 1 | FONDO=missing | DURACION=1 | PLANO=face:bob]\n"
            "[peter | ACCION=walk | VOZ=Aiden]\nHola, Bob.\n[bob | ACCION=idle]\n"
            "[ESCENA 2 | DURACION=1.5]\n[peter | ACCION=fall]\n")


def adapt_response(text, background="room", sounds="none"):
    scenes = parse_scenes(text)
    for scene in scenes:
        scene["fields"]["FONDO"] = background
        scene["fields"]["SFX"] = sounds
    return json.dumps({"guion": serialize_scenes(scenes), "cambios": []})


def test_preflight_preserves_cast_and_warns(assets, capsys):
    cast = parse_cast("peter = hero\nbob = hero",assets)
    adapted, changes = preparar_guion_visual(example(),cast,assets,[],chat=lambda *a,**kw: adapt_response(example()))
    assert len(parse_scenes(adapted)) == 2 and len(changes) >= 2
    assert "ADVERTENCIA" in capsys.readouterr().out
    timeline={"scenes":[{"id":"1","start":0,"end":1},{"id":"2","start":1,"end":2.5}]}
    board = storyboard_from_script(adapted,cast,assets,2.5,320,568,30,timeline=timeline)
    assert board["storyboard"][0]["shot"]["character"] == "bob"
    assert board["storyboard"][0]["narration"] == "Hola, Bob."
    assert board["storyboard"][1]["duration"] == 1.5
    assert board["cast"][0]["type"] == "humanoids/hero"


@pytest.mark.parametrize("bad", ["text","cast","action","sound","background"])
def test_preflight_rejects_changes_and_unavailable_assets(assets,bad):
    cast = parse_cast("peter=hero\nbob=hero", assets)
    response=adapt_response(example())
    if bad == "text": response=response.replace("Hola, Bob.","Changed")
    if bad == "cast": response=response.replace("peter", "intruder")
    if bad == "action": response=response.replace("ACCION=walk","ACCION=idle")
    if bad == "sound": response=adapt_response(example(),sounds="invented")
    if bad == "background": response=adapt_response(example(),background="invented")
    calls=[]
    def chat(*a,**kw): calls.append(1); return response
    with pytest.raises(RuntimeError):
        preparar_guion_visual(example(),cast,assets,[],chat=chat)
    assert len(calls) == 3


def test_audio_parser_and_exact_scene_timing():
    text=example()
    assert limpiar_guion_audio(text) == "Hola, Bob."
    blocks=parsear_bloques_audio(formatear_guion_audio(text))
    assert blocks[1]["text"] == "" and blocks[1]["scene_duration"] == "1.5"
    calls=[]
    def synth(text,voice,instruction): calls.append(voice);return np.ones(12000),24000
    audio,timeline=assemble_audio(blocks,synth,lambda t:[t] if t else [],"Ryan")
    assert calls == ["Aiden"]
    assert timeline["scenes"] == [{"id":"1","start":0,"end":1},{"id":"2","start":1,"end":2.5}]
    assert len(audio) == 60000
    assert not np.any(audio[24000:])


def test_global_parser_keeps_scene_headers():
    import main
    text="[TITULO]\nTest\n[MODO_VIDEO]\nstick\n[CAST]\npeter=hero\nbob=hero\n[GUION]\n"+example()
    config=main.parsear_guion_configurado(text)
    assert config["cast"] == "peter=hero\nbob=hero"
    assert len(parse_scenes(config["guion"])) == 2


def test_silent_audio_and_subtitles_without_models(tmp_path,monkeypatch):
    from generar_audio import generar_audio
    from generar_subtitulos import generar_subtitulos
    monkeypatch.setenv("QWEN_PYTHON",str(tmp_path/"does-not-exist"))
    script=tmp_path/'guion.txt'; script.write_text('[ESCENA 1 | DURACION=1.2]\n[peter | ACCION=walk]\n')
    audio=generar_audio(script,tmp_path/'audio.wav')
    with wave.open(str(audio)) as w: assert w.getnframes() == 28800
    output=generar_subtitulos(audio,tmp_path/'subtitulos.ass')
    assert '[Events]' in output.read_text() and 'Dialogue:' not in output.read_text()
    assert json.loads((tmp_path/'segmentos.json').read_text()) == []


def test_legacy_voice_tags_survive_conversion(assets):
    source='[peter | VOZ=Aiden | INSTRUCCION=ACCION EXACTA: walk. | PAUSA=0.3]\nHola.\n'
    text=explicit_script(source,{'peter':'hero'},assets)
    block=parsear_bloques_audio(text)[0]
    assert block['voice']=='Aiden' and block['pause']=='0.3' and block['text']=='Hola.'


def test_real_cpu_and_opengl_rendering(tmp_path,monkeypatch):
    from stick_engine.renderer import StickRenderer
    monkeypatch.setattr(StickRenderer,'_video_encoder',lambda self:('libx264','veryfast'))
    scene={'background':'house','width':320,'height':568,'duration':.6,'fps':30,
           'characters':[{'id':'peter','type':'jhon','action':'walk','position':1},
                         {'id':'bob','type':'jhon','action':'idle','position':2}],
           'shot':{'target':'face','character':'bob'}}
    cpu=StickRenderer(); cpu.render(scene,tmp_path/'cpu.mp4')
    import moderngl
    original=moderngl.create_standalone_context
    monkeypatch.setattr(moderngl,'create_standalone_context',lambda **kw:original(backend='egl',**kw))
    from stick_engine.renderer_gpu import StickRendererGPU
    try: gpu=StickRendererGPU()
    except Exception as exc: pytest.skip(f'OpenGL no disponible: {exc}')
    monkeypatch.setattr(gpu,'_video_encoder',lambda:('libx264','veryfast'))
    try: gpu.render(scene,tmp_path/'gpu.mp4')
    finally: gpu.close()
    for name in ('cpu','gpu'):
        raw=subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=width,height,nb_frames','-of','json',str(tmp_path/f'{name}.mp4')])
        stream=json.loads(raw)['streams'][0]
        assert (stream['width'],stream['height'],stream['nb_frames']) == (320,568,'18')


def test_full_silent_clip_before_audio_and_real_mux(tmp_path,monkeypatch):
    import main
    import openai_client
    import generar_video
    sg=importlib.import_module('stick_engine.generar_stick')
    from stick_engine.renderer import StickRenderer
    monkeypatch.setattr(StickRenderer,'_video_encoder',lambda self:('libx264','veryfast'))
    monkeypatch.setattr(sg,'_crear_renderer',lambda:(StickRenderer(),'cpu'))
    monkeypatch.setattr(main,'CLIPS_DIR',tmp_path/'clips')
    monkeypatch.setattr(main,'GUIONES_DIR',tmp_path/'guiones')
    monkeypatch.setattr(main,'SOUND_EFFECTS_DIR',tmp_path/'sounds')
    monkeypatch.setattr(generar_video,'SOUND_EFFECTS_DIR',tmp_path/'sounds')
    source=tmp_path/'source.txt'
    source.write_text('[TITULO]\nSilent\n[MODO_VIDEO]\nstick\n[RESOLUCION]\n320x568\n[CAST]\npeter=jhon\nbob=jhon\n[GUION]\n'
                      '[ESCENA 1 | FONDO=house | DURACION=0.6]\n[peter | ACCION=front_walk]\n[bob | ACCION=idle]\n'
                      '[ESCENA 2 | FONDO=house | DURACION=0.6 | PLANO=face:bob]\n[peter | ACCION=speak_side]\n[bob | ACCION=afraid]\n')
    order=[]
    def chat(messages,**kwargs):
        order.append('adapt')
        script=messages[1]['content'].split('GUION:\n',1)[1]
        return adapt_response(script,background='house')
    monkeypatch.setattr(openai_client,'openai_chat',chat)
    audio=main._llamar_generar_audio
    def tracked_audio(**kwargs):order.append('audio');return audio(**kwargs)
    monkeypatch.setattr(main,'_llamar_generar_audio',tracked_audio)
    video=main.crear_clip('guion','Silent',str(source))
    assert order==['adapt','audio']
    streams=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(video)]))['streams']
    assert {s['codec_type'] for s in streams}=={'video','audio'}
    board=json.loads((video.parent/'stick_storyboard.json').read_text())
    assert board['storyboard'][1]['start']==.6
    assert board['storyboard'][1]['shot']['character']=='bob'
    assert (video.parent/'guion_adaptado.txt').is_file()
    assert json.loads((video.parent/'log.json').read_text())['runs'][-1]['status']=='completed'


def test_mixed_preserves_explicit_shots_and_types(assets):
    cast={'peter':'hero','bob':'hero'}
    scenes=parse_scenes(example())
    scenes[1]['fields']['TIPO']='illustration'
    scenes[1]['fields']['PROMPT']='An empty room, cinematic illustration'
    text=serialize_scenes(scenes)
    adapted,_=preparar_guion_visual(text,cast,assets,[],chat=lambda *a,**kw:adapt_response(text),modo_video='mixed')
    board=storyboard_from_script(adapted,cast,assets,2.5,320,568,30,modo_video='mixed',minimum_stick=50)
    assert board['storyboard'][0]['scene_type']=='stick'
    assert board['storyboard'][1]['scene_type']=='illustration'


def test_cleanup_only_deletes_known_source(tmp_path,monkeypatch):
    import hashlib
    import instalar_actualizacion as installer
    obsolete=tmp_path/'old_client.py';obsolete.write_text('replaced source')
    personal=tmp_path/'custom_client.py';personal.write_text('personal changes')
    monkeypatch.setattr(installer,'OBSOLETE_DIGESTS',{hashlib.sha256(obsolete.read_bytes()).hexdigest()})
    assert installer.retirar_archivos_obsoletos(tmp_path)==['old_client.py']
    assert personal.read_text()=='personal changes'
    obsolete.write_bytes(b'\xef\xbb\xbfreplaced source')
    assert installer.retirar_archivos_obsoletos(tmp_path)==['old_client.py']


def test_image_mode_preserves_montage_music_sfx_and_final_image(tmp_path,monkeypatch):
    import generar_video as video_module
    images=tmp_path/'images'; images.mkdir()
    Image.new('RGB',(160,284),'#527c99').save(images/'scene_001.png')
    ending=tmp_path/'ending.png';Image.new('RGB',(160,284),'#b34a4a').save(ending)
    sounds=tmp_path/'sounds';sounds.mkdir()
    music=tmp_path/'music';music.mkdir()
    def wav(path,length):
        with wave.open(str(path),'wb') as output:
            output.setnchannels(1);output.setsampwidth(2);output.setframerate(24000)
            output.writeframes((np.sin(np.arange(round(length*24000))*2*np.pi*440/24000)*8000).astype('<i2').tobytes())
    wav(tmp_path/'audio.wav',.6);wav(sounds/'ding.wav',.2);wav(music/'background.wav',.6)
    config={'resolucion':'160x284','musica':str(music/'background.wav'),'volumen_musica':.1,
            'usar_efectos_sonido':True,'max_efectos_sonido':8,'imagen_final':str(ending),'duracion_imagen_final':.2}
    cfg=tmp_path/'config.json';cfg.write_text(json.dumps(config))
    (tmp_path/'stick_storyboard.json').write_text(json.dumps({'storyboard':[{'start':0,'sound_effects':[{'name':'ding','time':.1}]}]}))
    monkeypatch.setattr(video_module,'SOUND_EFFECTS_DIR',sounds)
    output=video_module.generar_video(tmp_path/'audio.wav',images,tmp_path/'missing.ass',tmp_path/'video.mp4',cfg,modo_video='image')
    result=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(output)]))
    assert {s['codec_type'] for s in result['streams']}=={'video','audio'}


def test_speech_worker_keeps_scene_silence_and_voice_tags(tmp_path,monkeypatch):
    import generar_audio_qwen as worker
    import soundfile as sf
    class Model:
        tts_model_size='0b6'
        def generate_custom_voice(self,text,language,speaker,**kw):
            assert speaker=='Aiden' and language=='Spanish'
            return [np.sin(np.arange(12000)*.1).astype(np.float32)*.2],24000
    class Loader:
        @staticmethod
        def from_pretrained(*a,**kw):return Model()
    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace(cuda=SimpleNamespace(is_available=lambda:True),float32='float32'))
    monkeypatch.setitem(sys.modules,'qwen_tts',SimpleNamespace(Qwen3TTSModel=Loader))
    script=tmp_path/'source.txt';script.write_text(example())
    output=tmp_path/'audio.wav'
    monkeypatch.setattr(sys,'argv',['worker',str(script),str(output),'Ryan'])
    assert worker.main()==0
    audio,rate=sf.read(output)
    timeline=json.loads(output.with_suffix('.timeline.json').read_text())
    assert rate==24000 and len(audio)==60000
    assert timeline['scenes'][1]['start']==1 and timeline['blocks'][0]['text']=='Hola, Bob.'
