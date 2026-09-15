# Construir «First Mate Responder» en iOS

Esta guía construye el atajo que consulta preguntas pendientes, permite escoger la correcta y envía una respuesta durable e idempotente. Complementa el [contrato completo para iPhone](ios-shortcut.md) y el [contrato HTTP](http-api.md); no cambia ninguno de ellos.

Los nombres localizados pueden variar ligeramente entre versiones de iOS. Se usan únicamente acciones documentadas en la receta principal: **Obtener archivo de carpeta**, **Obtener diccionario de la entrada**, **Obtener valor del diccionario**, **Obtener tipo**, **Contar**, **Si**, **Elegir del menú**, **Elegir de la lista**, **Ejecutar atajo**, **URL**, **Obtener contenido de URL**, **Lista**, **Repetir con cada elemento**, **Añadir a variable**, **Coincidir texto**, **Texto**, **Leer texto**, **Dictar texto**, **Reemplazar texto**, **Diccionario**, **Establecer valor del diccionario**, **Obtener texto de la entrada**, **Definir nombre**, **Guardar archivo**, **Establecer variable** y **Detener este atajo**.

## Antes de empezar

Deben existir y funcionar:

- la carpeta privada `FirstMate` usada por los demás atajos;
- **First Mate Config**, que devuelve un Diccionario con `base_url` (Texto) y `token` (Texto);
- **First Mate UUID**, que devuelve un UUID v4 como Texto;
- **First Mate Enviar pendiente**, que conserva el UUID al reintentar, valida el recibo y solo dice «Enviado» después de `accepted=true`;
- Tailscale conectado y la URL HTTPS privada ya configurada.

No copies aquí valores reales, no exportes el atajo configurado y no pongas el token en `pending.json`. Construye un atajo nuevo llamado **First Mate Responder**. Ejecuta cada bloque solo después de completarlo; mientras esté incompleto, deja **Detener este atajo** al final.

## Variables

| Variable | Tipo esperado | Origen |
| --- | --- | --- |
| `ArchivoPendiente` | Archivo o sin valor | `FirstMate/pending.json` |
| `Borrador` | Diccionario | JSON del archivo pendiente |
| `Confirmado` | Booleano | `acknowledged` |
| `Config` | Diccionario | First Mate Config |
| `BaseURL`, `Token` | Texto | Config |
| `RespuestaGET` | Diccionario | GET `/jobs/pending-input` |
| `ErrorPublico` | Texto o sin valor | `error` |
| `Trabajos` | Lista | `jobs` |
| `HayMas` | Booleano | `has_more` |
| `Cantidad` | Número entero | cantidad de Trabajos |
| `Seleccionado` | Diccionario | elemento único o elección explícita |
| `JobID`, `Pregunta`, `Estado` | Texto | trabajo seleccionado |
| `Revision` | Número entero positivo | `input_revision` |
| `ReplyID`, `Prompt` | Texto | UUID y dictado recortado |

## Bloque 1: proteger un borrador incierto

1. Añade **Obtener archivo de carpeta** para `FirstMate/pending.json`, con «Error si no se encuentra» desactivado. Guarda el resultado como `ArchivoPendiente`.
2. Añade **Si** `ArchivoPendiente` **tiene valor**. En esta condición, `ArchivoPendiente` debe ser de tipo **Archivo**.
3. Dentro, aplica **Obtener diccionario de la entrada** y guarda `Borrador` de tipo **Diccionario**. Obtén `acknowledged` como `Confirmado`.
4. Añade **Si** `Confirmado` **es verdadero**. En esta condición, `Confirmado` debe ser de tipo **Booleano**. Deja la rama verdadera sin menú: el borrador ya está confirmado y el flujo puede continuar.
5. En la rama **Si no**, añade **Elegir del menú**:
   - «Reintentar pendiente»: **Ejecutar atajo** `First Mate Enviar pendiente` y después **Detener este atajo**.
   - «Salir»: **Detener este atajo**.
6. Cierra las dos condiciones. Esta forma evita depender de una comparación booleana negativa que no está disponible en todas las versiones localizadas de Atajos.

Verificación: un borrador no confirmado nunca se sobrescribe. Un borrador confirmado permite continuar. Un JSON inválido debe terminar con el error nativo de Atajos, no tratarse como ausencia de borrador.

## Bloque 2: obtener las preguntas pendientes

1. **Ejecutar atajo** `First Mate Config` y guardar `Config` como **Diccionario**. Extrae `base_url` en `BaseURL` de tipo **Texto** y `token` en `Token` de tipo **Texto**.
2. Crea una acción **URL** con `BaseURL` seguida literalmente de `/jobs/pending-input`. No tomes ninguna parte de la URL del dictado, una pregunta o una notificación.
3. Añade **Obtener contenido de URL**:
   - método **GET**;
   - cabecera `Authorization`: texto literal `Bearer ` seguido de `Token`;
   - sin cuerpo.
4. Convierte la respuesta con **Obtener diccionario de la entrada** y guarda `RespuestaGET` de tipo **Diccionario**. Extrae `error` como `ErrorPublico`.
5. Añade **Si** `ErrorPublico` **tiene valor**. En esta condición, `ErrorPublico` debe ser de tipo **Texto**. Dentro, lee solo «No se pudieron consultar las preguntas» y detén el atajo; no leas el cuerpo completo.
6. Extrae `jobs` como `Trabajos`, de tipo esperado **Lista**, y `has_more` como `HayMas`, de tipo esperado **Booleano**. Usa **Obtener tipo** para guardar `TipoTrabajos` y `TipoHayMas`, ambos resultados de tipo **Texto**.
7. Añade **Si** `TipoTrabajos` **no es Lista**. En esta condición, `TipoTrabajos` debe ser **Texto**. Lee «Respuesta de First Mate inválida» y detén.
8. Añade **Si** `TipoHayMas` **no representa Booleano**. En esta condición, `TipoHayMas` debe ser **Texto**. Lee la misma frase y detén. Si iOS presenta booleanos JSON como Número, verifica el JSON serializado con `"has_more"\s*:\s*(true|false)\s*[,}]`; no aceptes los textos `"true"` o `"false"`.
9. Aplica **Contar** a `Trabajos` y guarda `Cantidad` de tipo **Número** entero.

Verificación: la petición es GET, no tiene cuerpo y no incorpora el token a la URL.

## Bloque 3: resolver cero o una pregunta

1. Añade **Si** `Cantidad` **es 0**. En esta condición, `Cantidad` debe ser de tipo **Número** entero.
2. Dentro, añade **Si** `HayMas` **es verdadero**. En esta condición, `HayMas` debe ser de tipo **Booleano**:
   - rama verdadera: **Leer texto** «Respuesta de First Mate inválida» y detener;
   - rama **Si no**: **Leer texto** «No hay preguntas pendientes» y detener.
3. Después del bloque anterior, añade **Si** `Cantidad` **es 1**. En esta condición, `Cantidad` debe ser de tipo **Número** entero.
4. Dentro, añade **Si** `HayMas` **es verdadero**. En esta condición, `HayMas` debe ser de tipo **Booleano**. En la rama verdadera continúa al bloque de selección explícita. En la rama **Si no**, usa **Obtener primer elemento de la lista** sobre `Trabajos` y guarda `Seleccionado` como **Diccionario**.

No selecciones automáticamente el único elemento visible cuando `has_more=true`: la respuesta está truncada y existen más preguntas.

## Bloque 4: selección segura con varias preguntas

Ejecuta este bloque cuando `Cantidad` sea mayor que uno o `HayMas` sea verdadero. En Atajos se puede expresar con ramas de las condiciones del bloque anterior, sin convertir los valores a texto.

1. Crea `Opciones` como **Lista** vacía y `Mapa` como **Diccionario** vacío.
2. Añade **Si** `HayMas` **es verdadero**. En esta condición, `HayMas` debe ser de tipo **Booleano**. Lee «Se muestran las primeras 100; elige una explícitamente».
3. Añade **Repetir con cada elemento** de `Trabajos`. Cada elemento debe ser un **Diccionario**. Extrae:
   - `id` → `IDElemento`, tipo **Texto**;
   - `question` → `PreguntaElemento`, tipo **Texto**;
   - `input_revision` → `RevisionElemento`, tipo **Número**;
   - `state` → `EstadoElemento`, tipo **Texto**.
4. Valida cada elemento antes de presentarlo:
   - **Si** `IDElemento` no coincide completamente con `^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$`: `IDElemento` debe ser **Texto**; detén con «Respuesta de First Mate inválida».
   - **Si** `PreguntaElemento` no tiene valor después de recortar espacios: `PreguntaElemento` debe ser **Texto**; detén con la misma frase.
   - **Si** `RevisionElemento` es menor que 1: `RevisionElemento` debe ser **Número** entero; detén. Comprueba además igualdad con su valor redondeado a unidades.
   - **Si** `EstadoElemento` no es exactamente `waiting_for_input`: `EstadoElemento` debe ser **Texto**; detén.
5. Crea con **Texto** la etiqueta `[Índice de repetición] · [PreguntaElemento] · [IDElemento]`. Usa **Añadir a variable** para incorporarla a `Opciones`. Con **Establecer valor del diccionario**, guarda en `Mapa` la etiqueta completa como clave y el Diccionario original como valor; conserva el Diccionario resultante otra vez en `Mapa`.
6. Usa **Elegir de la lista** sobre `Opciones`, con selección múltiple desactivada. Usa la etiqueta elegida como clave de `Mapa` y guarda el resultado como `Seleccionado`, de tipo **Diccionario**. Cancelar la lista termina el flujo; no uses el primer elemento como alternativa.

La etiqueta lleva el ID completo para distinguir preguntas con texto idéntico. Nunca deduzcas un ID desde la pregunta o la notificación.

## Bloque 5: validar y leer la pregunta elegida

Estas comprobaciones se aplican tanto al elemento único como al elegido de una lista.

1. Extrae de `Seleccionado`: `id` → `JobID` (**Texto**), `question` → `Pregunta` (**Texto**), `input_revision` → `Revision` (**Número**) y `state` → `Estado` (**Texto**).
2. Añade las comprobaciones siguientes; cualquiera lee «Respuesta de First Mate inválida» y detiene:
   - **Si** `JobID` no coincide completamente con el patrón UUID anterior. En esta condición, `JobID` debe ser **Texto**.
   - **Si** `Pregunta` no tiene valor después de recortar espacios. En esta condición, `Pregunta` debe ser **Texto**.
   - **Si** `Revision` es menor que 1 o difiere de su valor redondeado a unidades. En esta condición, `Revision` debe ser **Número** entero positivo.
   - **Si** `Estado` no es exactamente `waiting_for_input`. En esta condición, `Estado` debe ser **Texto**.
3. Guarda `JobID` y `Revision` con **Establecer variable**.
4. Usa **Leer texto** únicamente con `Pregunta`. No concatentes el Diccionario, el ID ni diagnósticos.

Verificación: con varias preguntas siempre aparece la elección explícita; solo se pronuncia el campo `question` del elemento elegido.

## Bloque 6: dictar y guardar la respuesta antes de enviarla

1. **Ejecutar atajo** `First Mate UUID` una sola vez y guardar `ReplyID` de tipo **Texto**.
2. Usa **Dictar texto**. Aplica **Reemplazar texto**, expresión regular `^\s+|\s+$`, reemplazo vacío, y guarda `Prompt` de tipo **Texto**.
3. Añade **Si** `Prompt` **no tiene valor**. En esta condición, `Prompt` debe ser de tipo **Texto**. Detén el atajo sin escribir ni enviar.
4. Crea un **Diccionario** con tipos explícitos:
   - `kind`: Texto literal `reply`;
   - `request_id`: Texto `ReplyID`;
   - `prompt`: Texto `Prompt`;
   - `job_id`: Texto `JobID`;
   - `input_revision`: Número `Revision`;
   - `acknowledged`: Booleano falso.
5. Convierte el Diccionario con **Obtener texto de la entrada**, aplica **Definir nombre** `pending.json` y **Guardar archivo** en la carpeta `FirstMate`, con «Preguntar dónde guardar» desactivado y «Sobrescribir si existe» activado. El guardado debe terminar antes de cualquier POST.
6. **Ejecutar atajo** `First Mate Enviar pendiente` y después **Detener este atajo**.

`First Mate Enviar pendiente` debe enviar `POST /jobs/{job_id}/reply` con `request_id` Texto, `prompt` Texto e `input_revision` Número. Debe exigir que el `id` del recibo sea igual a `JobID`, marcar el borrador como confirmado y decir «Enviado» únicamente tras un recibo válido. Al reintentar conserva `ReplyID`: no ejecutes otra vez el selector ni generes otro UUID.

## Errores y conflictos

- Un timeout o pérdida de conexión deja `pending.json` sin confirmar. Vuelve a ejecutar **First Mate Responder**, elige «Reintentar pendiente» y conserva el mismo UUID.
- Un `409/conflict` indica que la revisión ya no es aplicable o que el ID pertenece a otra operación. No cambies `input_revision`, no regeneres el UUID y no apliques el dictado a otra pregunta.
- Tras un conflicto, consulta de nuevo las preguntas solo después de decidir conscientemente descartar la respuesta obsoleta. Archiva el borrador fuera de `pending.json`; no lo borres silenciosamente.
- Un error de autenticación nunca debe decir «Enviado». Revisa **First Mate Config** por un medio privado, sin leer ni mostrar el token.
- Nunca leas en voz alta JSON, cuerpos de error, tokens, IDs ni diagnósticos.

## Prueba final sin secretos

1. Con el iPhone desbloqueado y Tailscale conectado, crea mediante **First Mate** una petición sintética que solicite una pregunta inocua, sin datos personales.
2. Espera el aviso y ejecuta **First Mate Responder**.
3. Comprueba que se lee únicamente la pregunta sintética. Cuando haya varias preguntas visibles o `has_more=true`, comprueba que obliga a elegir explícitamente.
4. Dicta una respuesta sintética breve. Confirma que `pending.json` se guarda antes de la red y que se oye «Enviado» solo tras el recibo.
5. Ejecuta **First Mate Responder** otra vez y verifica que la pregunta contestada ya no se ofrece como pendiente.
6. Registra únicamente versión de iOS y ntfy, Wi‑Fi o datos móviles, tiempo aproximado hasta «Enviado», resultado y necesidad de desbloqueo. No registres dictados, preguntas, IDs, URLs ni credenciales.

Después valida por separado la notificación con pantalla bloqueada y AirPods, como indica la [matriz de prueba física](ios-shortcut.md#action-button-siri-y-prueba-en-iphone). La notificación no confirma escucha y nunca modifica el cursor de **Leer First Mate**.
