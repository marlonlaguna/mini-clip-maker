# Animaciones de tamaño variable y primeros planos HD

Actualización sobre `main`, commit `bb55aa1`. Copia los archivos del ZIP en la raíz de Mini Clip Maker y acepta los reemplazos. El ZIP contiene código, pruebas, esta guía y un guion de ejemplo; los retratos HD se crean aparte y se guardan junto a los PNG actuales del personaje.

Se conservan el comando `main.py --guion`, el formato del guion, el cast, la adaptación de recursos previa al audio, voz, subtítulos, música, sonidos, imagen final y los modos `image`, `stick` y `mixed`. La configuración común actual de FPS y estados se conserva: no se reemplaza `humanoids/actions.json`.

## Tamaños de frame

Para humanoides y no humanoides, el motor reconoce tiras horizontales de celdas cuadradas de **200, 400, 512 o 1024 px** usando la altura del PNG. El ancho debe ser un múltiplo exacto de esa altura.

| PNG | Interpretación |
| --- | --- |
| `walk.png`, 2400×200 | 12 frames de 200×200, como antes |
| `idle.png`, 3200×400 | 8 frames de 400×400 |
| `speak_side_closeup.png`, 26624×1024 | 26 frames de 1024×1024 |
| `sleep@400x200.png`, 3200×200 | 8 frames de 400×200 |

El sufijo `@ANCHOxALTO` fija dimensiones rectangulares o tamaños distintos de los predefinidos. Se reconoce como parte del archivo, no del nombre de acción: `sleep@400x200.png` sigue siendo la acción `sleep` en el guion. También funciona para acciones con alias, como `side_walk` que usa `walk.png`.

Una tira de 3200×200 sin sufijo se interpreta como 16 frames de 200×200. No se adivina que pretendía contener 8 celdas de 400×200: para eso usa el sufijo o `frameSize` por acción.

Solo puede haber una tira para cada acción lógica. Evita conservar a la vez `walk@400x200.png` y `walk@512x512.png`: usa nombres de acciones diferentes para variantes distintas. `modelo.png` y las referencias habituales siguen excluidos del catálogo.

## Primeros planos automáticos

Añade a la carpeta del personaje la variante correspondiente a su acción:

```text
idle_closeup@1024x1024.png
speak_side_closeup@1024x1024.png
speak_front_closeup@1024x1024.png
afraid_closeup@1024x1024.png
```

Por ejemplo, los retratos de Ana van en `stick_engine/assets/characters/humanoids/ana/`. Son tiras horizontales, igual que las demás animaciones, pero cada celda contiene **cabeza y hombros en alta resolución**, con fondo transparente, proporciones y posición constantes entre frames.

El sufijo `_closeup` identifica un retrato. Aumentar la resolución de un sprite de cuerpo completo no lo convierte en retrato y ampliar un PNG de 200×200 no recupera detalle. La detección de resolución y el tipo de encuadre son independientes.

Estas variantes heredan FPS y `loop`, `hold` o `once` de la acción original. No requieren archivo de configuración individual. El motor no hereda el desplazamiento corporal para la variante de retrato. Los PNG adicionales que no correspondan a una variante `_closeup` conocida siguen requiriendo declaración como acciones propias.

El guion se escribe igual:

```text
[ESCENA reaccion | FONDO=bedroom_house | PLANO=face:ESPOSA]
[ESPOSA | ACCION=afraid | POSICION=1]
[ESPOSO | ACCION=speak_side | POSICION=2 | VOZ=Ryan]
¿Qué encontraste?
```

Python selecciona `afraid_closeup` de Ana, aunque esté hablando Jhon. El mismo mecanismo funciona con `PLANO=head:ESPOSA`. Si falta la variante correspondiente, se muestra un aviso y se usa el acercamiento habitual; no se sustituye miedo por reposo ni se cambia el guion. Los planos de torso, brazos y piernas mantienen su funcionamiento.

En planos de cuerpo completo se mantienen los sprites habituales. Se conserva el espejo según `MIRA` o la orientación automática. Los retratos se encuadran sobre el lienzo completo, evitando el recorte de frente que produciría aplicarles la región de cabeza de un sprite corporal. La escala se mantiene estable aunque cambie el área transparente entre frames. CPU renderiza los detalles a resolución nativa y GPU sube a memoria un frame a la vez, no la tira completa de 26624 px de ancho.

Al terminar una variante `once`, el motor vuelve a `idle_closeup` si existe; si falta, vuelve al acercamiento normal de `idle`. Los estados `hold` conservan su último frame. El número de frames y la resolución pueden variar entre acciones sin desplazar el centro de apoyo al volver a reposo.

## Configuración opcional

Para sobrescribir una variante concreta, añade únicamente la entrada necesaria a la configuración común o a `actions.json` del personaje. Por ejemplo:

```json
{
  "actions": {
    "afraid_closeup": {"fps": 13, "mode": "loop"},
    "sleep": {"frameSize": {"width": 400, "height": 200}, "mode": "hold"}
  }
}
```

`frameSize` dentro de una acción fija su tamaño. Si el archivo también tiene sufijo, ambas dimensiones deben coincidir. El campo `frameSize` global de 200×200 de la configuración anterior no bloquea la detección automática de otras resoluciones.

También se admite una variante con otro nombre usando `view` y `forAction`:

```json
{"actions": {"retrato_hablando": {"view": "portrait", "forAction": "speak_side", "fps": 13, "mode": "loop"}}}
```

En ese caso el PNG puede llamarse `retrato_hablando@1024x1024.png`. Para elegir expresamente una variante entre varias, la acción original puede incluir `"closeup": "nombre_de_variante"`. Sin selección explícita se prioriza la variante exacta `<acción>_closeup`, después la del PNG corporal compartido (por ejemplo `side_walk` puede reutilizar `walk_closeup`); `speak_closeup` se admite como variante genérica para hablar si faltan las anteriores. Los retratos no se duplican en el catálogo compacto enviado a OpenAI: la selección visual pertenece a Python.

## Objetos y rendimiento

Los objetos conservan su comportamiento: una imagen estática de cualquier tamaño o una tira de 200×200, sin configuración. Para un objeto animado con otro tamaño usa el sufijo, por ejemplo `fire@400x400.png`. Así una imagen estática antigua de 800×400 sigue siendo estática.

26 frames de 1024×1024 a 13 FPS forman un loop de dos segundos. La tira decodificada en RGBA ocupa aproximadamente **104 MiB**, además de frames recortados, espejos y texturas. Para las primeras pruebas puedes usar menos frames o 512×512 y después sustituir la tira por la definitiva. No hay nuevos requisitos de ejecución ni llamadas extra a OpenAI por los retratos. La animación sigue siendo un loop visual; no se añade sincronización labial con el audio.

## Prueba

```powershell
py -3.12 main.py --guion "Prueba de primeros planos HD" "prueba-primeros-planos-hd.txt"
```

El ejemplo usa a Ana y Jhon. Con los retratos añadidos selecciona HD; sin ellos sirve para comprobar el respaldo a los acercamientos actuales.

Validación automatizada:

```powershell
py -3.12 -m pytest -q tests
```

Las pruebas existentes se conservan y se añaden pruebas de tamaños, recorte, herencia de configuración, espejo, reproducción y videos reales CPU/OpenGL. El render OpenGL se prueba cuando hay contexto disponible; las pruebas no consumen APIs de pago ni cargan un modelo Qwen real.
