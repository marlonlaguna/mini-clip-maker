"""Crea voice.pt desde referencia.wav + referencia.txt.
Uso: .venv-qwen\Scripts\python.exe crear_voz_personaje.py humanoids/tomy_teenager
"""
import argparse
from dataclasses import asdict
from pathlib import Path
import json
import torch
from qwen_tts import Qwen3TTSModel

parser = argparse.ArgumentParser()
parser.add_argument('character', help='Ejemplo: humanoids/tomy_teenager')
parser.add_argument('--wav', default=None, help='Audio fuente opcional')
parser.add_argument('--txt', default=None, help='Transcripción fuente opcional')
args = parser.parse_args()
root = Path(__file__).resolve().parent
characters_root = (root / 'stick_engine' / 'assets' / 'characters').resolve()
folder = (characters_root / args.character.replace('\\', '/')).resolve()
if not folder.is_relative_to(characters_root) or not folder.is_dir():
    raise SystemExit(f'Personaje inexistente: {folder}')
source_wav = Path(args.wav).resolve() if args.wav else folder / 'referencia.wav'
source_txt = Path(args.txt).resolve() if args.txt else folder / 'referencia.txt'
if not source_wav.is_file() or not source_txt.is_file():
    raise SystemExit(f'Se requieren {source_wav} y {source_txt}')
ref_text = source_txt.read_text(encoding='utf-8-sig').strip()
if not ref_text:
    raise SystemExit('La transcripción está vacía')
if not torch.cuda.is_available():
    raise SystemExit('Se requiere CUDA para este comando')
model = Qwen3TTSModel.from_pretrained(
    'Qwen/Qwen3-TTS-12Hz-0.6B-Base',
    device_map='cuda:0', dtype=torch.float32, attn_implementation='sdpa')
prompt = model.create_voice_clone_prompt(
    ref_audio=str(source_wav), ref_text=ref_text, x_vector_only_mode=False)
# Persistir únicamente tensores y valores simples (no unpickle arbitrario).
target = folder / 'voice.pt'
torch.save({'items': [asdict(p) for p in prompt]}, target)
config = folder / 'voice.json'
if not config.exists():
    config.write_text(json.dumps({'engine': 'qwen_clone', 'language': 'Spanish', 'prompt': 'voice.pt'}, indent=2), encoding='utf-8')
print(f'Voz lista: {target}')
