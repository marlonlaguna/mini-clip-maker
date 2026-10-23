
from pathlib import Path

import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel

# Archivos de referencia
carpeta = Path("voices/tomy")
audio_ref = carpeta / "referencia.wav"
texto_ref = (carpeta / "referencia.txt").read_text(
    encoding="utf-8-sig"
).strip()

# Modelo especializado en clonación
modelo = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    device_map="cuda:0",
    dtype=torch.float32,
    attn_implementation="sdpa",
)

# Texto nuevo con la voz clonada
texto = (
    "Anoche escuché pasos en mi habitación. "
    "Cuando abrí la puerta, no había nadie. "
    "Pero entonces alguien susurró mi nombre."
)

audio, sr = modelo.generate_voice_clone(
    text=texto,
    language="Spanish",
    ref_audio=str(audio_ref),
    ref_text=texto_ref,
    x_vector_only_mode=False,
)

salida = carpeta / "tomy_prueba.wav"
sf.write(str(salida), audio[0], sr)

print(f"Voz generada: {salida}")
