# Actualización del motor de sprites

Para tamaños de frame variables y variantes de rostro de alta resolución, consulta `ANIMACIONES_HD.md`. Las dimensiones de 200×200 descritas aquí siguen siendo el formato básico compatible.

Copia el contenido de este ZIP en la raíz de Mini Clip Maker, aceptando los reemplazos. No copies la carpeta del ZIP como un nivel adicional. La actualización parte del commit `efead9d`.

El comando de trabajo se mantiene:

```powershell
py -3.12 main.py --guion "Demo sprites" "ejemplo-sprites.txt"
```

También se incluye `ejemplo-sprites-sin-dialogo.txt`: necesita la revisión de recursos de OpenAI, pero no carga Qwen ni Whisper. Se genera una pista silenciosa para conservar música, efectos y montaje.

Al primer arranque, `main.py` retira el módulo cliente sustituido si su contenido coincide exactamente con la versión analizada, junto con su caché compilada. La limpieza compara SHA-256 y conserva archivos personalizados. Se puede ejecutar separadamente con `py -3.12 instalar_actualizacion.py`.

## Estructura

- `stick_engine/assets/characters/humanoids/actions.json`: configuración compartida, FPS y estados por acción.
- `stick_engine/assets/characters/humanoids/jhon/`: los 35 PNG originales del adjunto, incluidos `modelo.png` como referencia y 34 tiras de animación.
- `stick_engine/assets/characters/non-humanoids/<nombre>/`: tiras PNG y su propio `actions.json`, sin acciones compartidas.
- `stick_engine/assets/characters/objects/<nombre>/`: un único PNG, sin configuración. Puede ser una imagen estática de cualquier tamaño o una tira horizontal de celdas de 200×200.

Se conserva la escritura `characters` del repositorio. Las carpetas antiguas directamente bajo `characters/` ya no se cargan: sus recursos deben convertirse a la estructura nueva. No se borran tus assets anteriores.

Jhon no tiene un archivo de configuración propio. `modelo.png` nunca se anuncia como acción. La configuración común añade `side_walk` como alias que utiliza `walk.png`, sin duplicar imagen. `walk` y `run` tienen 12 frames; las demás tiras tienen 8. Los PNG del adjunto no se redibujaron ni redimensionaron.

## Configuración de acciones

La configuración común tiene este esquema; el archivo incluido contiene todas las acciones de Jhon:

```json
{
  "formatVersion": 2,
  "frameSize": {"width": 200, "height": 200},
  "defaults": {"fps": 13, "mode": "loop"},
  "actions": {
    "idle": {"mode": "loop"},
    "walk": {"mode": "loop", "movement": {"direction": "facing", "speed": 26}},
    "sleep": {"mode": "hold"},
    "open_door": {"mode": "once"},
    "side_walk": {"file": "walk.png", "mode": "loop"}
  }
}
```

| Estado | Resultado al terminar |
| --- | --- |
| `loop` | Reinicia la tira indefinidamente. |
| `hold` | Conserva el último frame. |
| `once` | Vuelve a `idle` y continúa su reproducción. Si no existe `idle`, usa la primera acción disponible. Si es la misma acción, conserva su primer frame. Nunca oculta al personaje. |

Las preferencias iniciales de `sleep`, `dying`, `fall` y `hiding` son `hold`; `open_door`, `turn_arround`, `front_point` y `side_point` usan `once`. Puedes cambiarlas en la configuración común. Los FPS de todas las acciones son 13 por defecto; para cambiar una añade `"fps": 18` en esa acción. Esto no modifica los 30 FPS del video.

Un humanoide puede añadir `actions.json` dentro de su carpeta para declarar acciones propias o sobrescribir FPS/estado de las comunes:

```json
{"actions": {"walk": {"fps": 18}, "salute": {"file": "salute.png", "fps": 10, "mode": "once"}}}
```

Para un no humanoide se usa el mismo esquema, pero todas sus acciones se declaran en su archivo. Una acción solo está disponible si existe su PNG; las acciones desconocidas se rechazan, y las tiras con dimensiones incorrectas fallan antes de generar audio. Si agregas un PNG específico, decláralo en la configuración específica.

## Guion y cast

La cabecera global conserva las opciones existentes. `stick` y `mixed` requieren un cast explícito; OpenAI nunca asigna un character a un papel:

```text
[CAST]
peter = humanoids/jhon
lucas = jhon

[GUION]
[ESCENA 1 | FONDO=house | SFX=none | PLANO=face:lucas]
[peter | ACCION=speak_side | VOZ=Aiden]
¿Qué pasó?
[lucas | ACCION=afraid]

[ESCENA 2 | DURACION=2 | FONDO=house]
[peter | ACCION=walk | MIRA=left]
```

Los dos papeles pueden usar el mismo asset. Si hay nombres de carpeta repetidos en distintas categorías, usa siempre `categoría/nombre`. Los nombres de papel del guion coinciden con los del cast. `NARRADOR` se reserva para voz en off; no añade un personaje visual.

Cada encabezado de personaje lo incluye en la escena, tenga o no diálogo. Su acción se reproduce durante la escena completa; los diálogos se pronuncian en el orden escrito. Para cambiar de acción a mitad de una secuencia, empieza otra escena. Si un personaje no debe aparecer, omítelo en la escena siguiente.

`DURACION` es obligatoria si la escena no contiene diálogo. En escenas habladas es una duración mínima: se añade silencio al final si hace falta; el diálogo nunca se corta para cumplirla. `PAUSA` conserva pausas de 0 a 10 segundos y `INSTRUCCION` conserva el comportamiento del modelo de voz. La variante Qwen 0.6B no interpreta instrucciones emocionales.

Puedes conservar guiones anteriores con bloques `[personaje | VOZ=... | INSTRUCCION=...]`, añadiendo un cast explícito. Se convierten a escenas antes de la revisión; `ACCION EXACTA: nombre` se conserva. La narración sin acción utiliza reposo. El modo `image` conserva el flujo anterior, incluyendo `--prompt`.

## Orientación y desplazamiento

`MIRA=right`, `MIRA=left` y `MIRA=auto` controlan la orientación. `left` aplica espejo; `right` usa el PNG original. Sin indicación, Python ordena por posición en pantalla: los de la izquierda miran a la derecha, los de la derecha miran a la izquierda y el central de un grupo impar conserva la tira original. Un personaje solo conserva el original. No interviene OpenAI.

`POSICION=1`, `POSICION=2`, etc., determina el orden de izquierda a derecha. También se admiten `X`/`Y` entre 0 y 1, `ESCALA` positiva y `EMOCION` de las disponibles. Las posiciones no pueden repetirse.

`walk`, `side_walk`, `run` y `sneaking` desplazan horizontalmente según la orientación. `front_walk` avanza en profundidad y crece ligeramente; `back_walk` retrocede y se reduce. La velocidad se expresa en píxeles por segundo para una imagen de 1080 de ancho y se adapta a la resolución. No depende de los FPS de animación. El tamaño en profundidad se limita entre 78 % y 122 %, y se limita el desplazamiento en los bordes para conservar al personaje visible.

En el guion se puede indicar `MOVIMIENTO=up`, `down`, `left`, `right`, `toward`, `away`, `facing` o `none`, junto con `VELOCIDAD=26`. Estas opciones sobrescriben el desplazamiento de la acción en esa escena.

## Fondos, sonidos y primeros planos

Antes del audio se envían a OpenAI el guion completo, el cast fijo y los recursos disponibles. Las acciones humanoides compartidas se envían una sola vez; se enumeran extras y ausencias por personaje del cast. OpenAI devuelve un guion adaptado. Python solo acepta cambios en `FONDO` y `SFX`, valida sus nombres y muestra las sustituciones en consola. Las respuestas que cambian diálogos, cast, acciones, planos u orientación se rechazan y se reintentan hasta tres veces. Si siguen siendo inválidas, se detiene el proceso antes del audio.

`SFX=pasos@0.2,puerta@1.1` usa los nombres reales de los archivos sin extensión y segundos relativos a la escena. `SFX=none` permite silencio. Se respetan `USAR_EFECTOS_SONIDO`, `MAX_EFECTOS_SONIDO` y el volumen configurado. Si ningún sonido resulta apropiado, no se fuerza uno. Los fondos siempre proceden de `assets/backgrounds/`: el motor de sprites ya no genera fondos nuevos por petición del modelo. `PERMITIR_FONDOS_AUTOMATICOS` se sigue leyendo para compatibilidad de configuración.

`PLANO=face:lucas` enfoca a Lucas aunque Peter esté hablando. También se conservan `head`, `torso`, `arms`, `left_arm`, `right_arm`, `legs`, `left_leg`, `right_leg` y `full_body`. El objetivo debe estar presente en la escena. Los encuadres se aproximan a partir del área visible del sprite; no añaden detalle a una imagen de 200×200. En poses tumbadas o con otra persona dibujada dentro del PNG, puede necesitarse ajustar el dibujo para un primer plano exacto. Las puertas, muebles o acompañantes incluidos en una tira forman parte de la imagen y no son assets independientes.

`OBJETOS` permite una lista JSON con objetos `type=emoji`, conservando los efectos existentes. Los objetos físicos PNG se declaran como papeles del cast, por ejemplo `lampara = objects/lampara`, con acción `idle`.

En `mixed` se conservan las ilustraciones de Stable Diffusion y el porcentaje mínimo de sprites. Se puede indicar `TIPO=illustration | PROMPT=descripción en inglés`. En escenas sin tipo explícito, OpenAI puede proponer una ilustración; no cambia el cast. La primera escena y los primeros planos usan sprites. Python aplica el porcentaje mínimo. En `image` continúan las imágenes generadas, movimientos de cámara y montaje anteriores.

Se conservan música, efectos de sonido, subtítulos, imagen final, bitácora `log.json`, render GPU con respaldo CPU y organización por clip. El audio añade `audio.timeline.json` con tiempos exactos de voz y silencios. También se guardan `guion_original.txt`, `guion_adaptado.txt` y `cambios_recursos.json`. `guion_adaptado.txt` puede usarse directamente con `--guion`.

## Verificación

```powershell
py -3.12 -m pytest -q tests/test_sprite_engine.py
```

Las pruebas usan respuestas de API y voz controladas; comprueban el rechazo de recursos y cambios indebidos, los tres tipos de characters, reproducción, espejo, movimiento y escenas mudas. Incluyen montaje real con FFmpeg y render CPU/OpenGL cuando este último está disponible. No son una prueba de tu API de pago ni de Qwen en tu GPU. Los requisitos de ejecución permanecen: OpenAI configurado, FFmpeg, las dependencias existentes del proyecto y Qwen/CUDA cuando haya voz.
