# stick_engine para Mini Clip Maker

Copia esta carpeta completa dentro de:

C:\mini clip maker\stick_engine\

## Dependencia

El storyboard stick usa el mismo paquete Groq que Mini Clip Maker ya tiene instalado.

## Punto de entrada

```python
from stick_engine import generar_stick_scenes
```

Uso:

```python
clips_stick = generar_stick_scenes(
    guion=guion,
    duracion_segundos=duracion_real,
    ruta_clip=ruta_clip,
    resolucion=config.get("resolucion", "1080x1920"),
    fps=30
)
```

Esto:
1. pregunta a Groq por un storyboard stick,
2. guarda `stick_storyboard.json`,
3. renderiza las escenas,
4. devuelve una lista de Path hacia `scene_001.mp4`, etc.

No necesita API ni instalarse como paquete separado.
