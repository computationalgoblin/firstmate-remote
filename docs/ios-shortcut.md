# iPhone: dictar, enviar y continuar

Este flujo usa Atajos (Shortcuts), HTTPS privado de Tailscale y el gateway de [Fase 3](http-api.md). Tras el commit solo pronuncia **«Enviado»** y termina. El worker continúa en el PC y ntfy entrega preguntas/resultados. No abre Herdr ni una terminal móvil, no sondea el job y no necesita una aplicación iOS nativa.

## Preparación en el dispositivo

Conecta el iPhone a la tailnet del PC. Instala/configura el cliente ntfy con el tema privado ya elegido y permite notificaciones. El transporte HTTP no cambia las condiciones de entrega de ntfy en iOS: valida su llegada real, con pantalla bloqueada, en tu instalación.

Crea en Archivos una carpeta privada `FirstMate` dentro de una ubicación que Atajos pueda leer/escribir sin preguntar cada vez (por ejemplo, una carpeta local seleccionada en «En mi iPhone» si está disponible). Si eliges iCloud Drive, el borrador se sincronizará allí: contiene el dictado. No es una carpeta pública. Selecciona esa misma carpeta en todas las acciones de fichero siguientes.

Crea un atajo auxiliar privado **«First Mate Config»** con estas acciones:

1. **Diccionario**: `base_url` (Texto) = URL HTTPS exacta de Tailscale Serve, sin slash final; `token` (Texto) = token real de tu configuración privada, sin el prefijo `Bearer`.
2. **Detener y generar salida** (Stop and Output): ese diccionario.

No compartas/exportes este atajo con el token. Atajos no se presenta aquí como un almacén de secretos: quien acceda a su editor podrá leerlo. No uses el portapapeles, avisos ni «Vista rápida» para mostrarlo durante la ejecución. El token se usa exclusivamente en la cabecera de la llamada a la base HTTPS fija. No sigas enlaces recibidos en preguntas o notificaciones como URLs de la API.

Los nombres localizados de acciones pueden variar ligeramente con iOS; se incluyen los ingleses cuando conviene. Apple documenta la configuración de método, cabeceras y cuerpo JSON en [Get Contents of URL](https://support.apple.com/en-au/guide/shortcuts/apd58d46713f/ios).

## UUID sin acciones de terceros

Crea el auxiliar **«First Mate UUID»** con acciones integradas. Así no dependes de que una versión de iOS o una aplicación adicional ofrezca una acción llamada «Generar UUID»:

1. **Texto**: `0123456789abcdef`; **Dividir texto** (Split Text), separador **Cada carácter** → variable `Hex` (16 elementos).
2. **Repetir** 32 veces. Dentro: si **Índice de repetición** es 13, **Texto** `4`. Si no, si el índice es 17, **Número aleatorio** entre 9 y 12 y **Obtener elemento de la lista**, índice ese número, lista `Hex`. En los otros índices, número aleatorio entre 1 y 16 y obtener ese elemento de `Hex`. Deja como resultado de cada rama el carácter elegido; la salida de **Fin de Si** será el resultado de la iteración. Los índices de listas en Atajos empiezan en 1.
3. **Combinar texto** (Combine Text) de **Resultados de repetición**, separador **Personalizado** vacío → cadena de 32 caracteres.
4. **Reemplazar texto**, expresión regular activada: buscar `^(.{8})(.{4})(.{4})(.{4})(.{12})$`, reemplazar por `$1-$2-$3-$4-$5`.
5. **Detener y generar salida** con ese texto. En la prueba de construcción verifica el patrón `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$` y que dos ejecuciones dan valores distintos.

Esto construye identificadores con formato UUID v4 y bits de versión/variante correctos; el generador aleatorio de Atajos se usa para correlación e idempotencia, **no para secretos de autenticación**. Cada operación guarda el UUID una vez antes de enviar y lo conserva en los reintentos.

## Borrador durable y atajo de envío común

El fichero `pending.json` conserva **una operación sin confirmar**. No ejecutes estos atajos simultáneamente: Atajos no ofrece aquí un lock entre ejecuciones. Reintenta o resuelve el borrador pendiente antes de crear otro. No borres el borrador tras un error de red.

Esquema que construirán los atajos de dictado/respuesta:

```json
{
  "kind": "request",
  "request_id": "513adcfb-c431-4dd3-91bc-f94f972c3e32",
  "prompt": "Revisa las pruebas",
  "acknowledged": false
}
```

Para responder, `kind` será `reply` y habrá además `job_id` e `input_revision` (Número). No se guarda el token. Opcionalmente, una petición nueva puede incluir un `voice_session_id` conservado de un recibo anterior para agrupar la conversación; si no lo necesitas, omítelo y conserva el asignado por el servidor en el recibo.

Crea **«First Mate Enviar pendiente»** con las acciones siguientes:

1. **Obtener archivo de carpeta** (Get File from Folder): carpeta `FirstMate`, ruta `pending.json`. **Obtener diccionario de la entrada** con el contenido del fichero → variable `Borrador`. Si el fichero falta o no es JSON válido, termina con el error de Atajos; no hagas una llamada.
2. **Obtener valor del diccionario** `acknowledged`. **Si** es verdadero: **Detener este atajo**. No se vuelve a enviar una operación ya confirmada.
3. Extrae `kind`, `request_id` y `prompt`. Verifica ID no vacío y dictado no vacío. Si `kind=request`, fija `Ruta=/jobs`. Si `kind=reply`, verifica `job_id` mediante **Coincidir texto** con `^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$`, comprueba `input_revision` como número entero positivo y fija `Ruta=/jobs/[job_id]/reply`. Cualquier otro caso: mostrar «Borrador inválido» y detener. No leas la ruta o la URL desde un texto dictado.
4. **Diccionario** → `Cuerpo`: `request_id` (Texto) y `prompt` (Texto). En la rama reply, añade `input_revision` (Número) con **Establecer valor del diccionario** y guarda el diccionario resultante de nuevo en `Cuerpo`. En la rama request, añade `voice_session_id` solo si lo configuraste y existe.
5. **Ejecutar atajo** «First Mate Config» → `Config`. Extrae `base_url` y `token`. **URL**: variable `base_url` seguida de `Ruta`.
6. **Obtener contenido de URL** (Get Contents of URL), desplegar opciones: método **POST**; cabeceras `Authorization` = texto `Bearer ` seguido de la variable `token`, `Content-Type` = `application/json`; cuerpo de solicitud **JSON**. Añade los campos de `Cuerpo` como pares tipados: `request_id` Texto, `prompt` Texto y, en reply, `input_revision` Número (o `voice_session_id` Texto en request). Usa una acción POST en cada rama para no enviar campos vacíos/ajenos. Inserta **variables**, no un JSON de texto con interpolación manual: Atajos debe escapar comillas y saltos de línea. El gateway no devuelve redirecciones; usa exclusivamente la base HTTPS configurada.
7. **Obtener diccionario de la entrada** de la respuesta → `Recibo`. Extrae `accepted`, `id`, `voice_session_id`, `state` y `error`. Solo sigue si no existe `error`, `accepted` es verdadero, `id` coincide con el patrón UUID anterior, `voice_session_id` tiene valor y `state` coincide exactamente con uno de: `queued`, `running`, `waiting_for_input`, `completed`, `failed`, `cancelled`. Para comparar estados, crea una acción **Lista** con esos seis textos y usa **Si** la lista contiene `state`. En reply, exige también `id=job_id` del borrador. En cualquier otro caso muestra **«No se confirmó el envío; conserva el borrador y reintenta»** y detén el atajo.
8. **Establecer valor del diccionario**: `acknowledged` = Booleano verdadero en `Borrador`; conserva el diccionario resultante. Añade `receipt` = diccionario `Recibo` y conserva el resultado. **Obtener texto de la entrada** convierte este diccionario a JSON; **Definir nombre** = `pending.json`; **Guardar archivo** en la carpeta `FirstMate`, «Preguntar dónde guardar» desactivado y «Sobrescribir si existe» activado. Conserva el UUID y recibo hasta comenzar otra operación. Un fallo al guardar deja el borrador anterior reintentable: el servidor deduplicará.
9. **Leer texto** (Speak Text): texto literal **Enviado**. **Detener este atajo** (Stop This Shortcut, o Stop and Output sin contenido). No añadas «Esperar», «Repetir», GET de estado ni lectura del resultado. Terminar la ejecución no fuerza a iOS a cerrar su aplicación; finaliza el atajo y su actividad de envío.

Los POST del servidor devuelven 202. La acción estándar de Atajos normalmente entrega el cuerpo, sin exponer cómodamente el código HTTP como una variable separada: por eso el contrato `accepted` + ID + estado valida el recibo. Si tu versión muestra un error de transporte/HTTP y detiene la ejecución, no se ejecutan los pasos 7–9, y `pending.json` ya estaba guardado. Nunca pronuncies «Enviado» en la rama de error ni leas el cuerpo de error completo.

## Atajo principal «First Mate»

1. **Obtener archivo de carpeta** `FirstMate/pending.json`, con «Error si no se encuentra» desactivado. Si hay fichero, **Obtener diccionario de la entrada**. Si `acknowledged` no es verdadero, usa **Elegir del menú**: «Reintentar pendiente» → ejecutar «First Mate Enviar pendiente» y detener; «Salir» → detener. Si el JSON no es válido, deja que la acción se detenga y revisa el fichero; no sobrescribas una operación incierta.
2. **Ejecutar atajo** «First Mate UUID» → **Establecer variable** `RequestID`. Se genera una sola vez por operación; no dentro de reintentos.
3. **Dictar texto** (Dictate Text), idioma español, finalizar al dejar de hablar (o al tocar, según preferencia) → `Dictado`.
4. **Reemplazar texto**, expresión regular activada, patrón `^\s+|\s+$`, reemplazo vacío, sobre `Dictado` → `Prompt`. **Si** `Prompt` no tiene valor: **Detener este atajo**. Esto no envía ni guarda una operación vacía.
5. **Diccionario** con `kind` Texto `request`, `request_id` Texto `RequestID`, `prompt` Texto `Prompt`, `acknowledged` Booleano falso. No pongas comillas alrededor de las variables.
6. **Obtener texto de la entrada** del diccionario, **Definir nombre** `pending.json`, **Guardar archivo** en `FirstMate`, sin preguntar ubicación, sobrescribir activado. El guardado debe completarse **antes** del POST. Solo sustituye aquí el recibo anterior ya confirmado.
7. **Ejecutar atajo** «First Mate Enviar pendiente»; **Detener este atajo** al volver.

Al acabar el dictado, el único intercambio obligatorio de red es el POST. En una conexión disponible debería tardar pocos segundos; el servidor solo espera SQLite. No hay garantía de duración si iOS está sin cobertura, Tailscale está desconectado o falta un permiso: el plazo propio de la acción de red lo decide iOS. Puedes cerrar/cancelar la interfaz en ese caso y reintentar el borrador más tarde con el mismo UUID.

## Atajo «First Mate Responder»

1. Aplica el mismo control de borrador pendiente del paso 1 de «First Mate». No sobrescribas un envío o respuesta inciertos.
2. Ejecuta «First Mate Config»; **URL** `base_url/jobs/pending-input`; **Obtener contenido de URL**, método **GET**, cabecera Bearer, **sin cuerpo**. Convierte la respuesta en diccionario. Exige ausencia de `error`, lista `jobs` y Booleano `has_more`; una respuesta inválida termina el atajo.
3. **Contar** los elementos de `jobs`. Si hay cero y `has_more=false`: leer «No hay preguntas pendientes» y detener. Si hay cero y `has_more=true`, detener con aviso de respuesta inválida.
4. Si hay **exactamente uno y `has_more=false`**, obtén **Primer elemento de la lista** → `Seleccionado`. No uses solo `count=1` como prueba si la lista está truncada.
5. Si hay varios **o `has_more=true`**, crea `Opciones` (lista) y `Mapa` (diccionario vacío). **Repetir con cada elemento** de `jobs`: extrae `id`, `question`, `input_revision` y `state`; comprueba estado `waiting_for_input`, UUID válido, pregunta no vacía y revisión entera positiva. Construye una etiqueta con **Texto**: `[Índice de repetición] · [question] · [id]`. **Añadir a variable** `Opciones`; **Establecer valor del diccionario** en `Mapa`, clave esa etiqueta completa y valor el diccionario original; guarda el resultado otra vez en `Mapa`. **Elegir de la lista** `Opciones`, selección múltiple desactivada. Usa la etiqueta elegida como clave para recuperar `Seleccionado` desde `Mapa`. Cancelar la lista detiene el flujo; nunca usa el primero como fallback. Si `has_more=true`, avisa antes «Se muestran las primeras 100; elige una explícitamente». La etiqueta incluye ID completo, por lo que preguntas idénticas no se confunden.
6. Verifica también los campos de `Seleccionado` en la rama de una pregunta. Guarda `id` como `JobID` e `input_revision` como `Revision`. **Leer texto**: solo `question` de `Seleccionado`, sin concatenar el JSON. No extraigas IDs del texto de una pregunta o de una notificación.
7. **Ejecutar atajo** «First Mate UUID» → `ReplyID`; **Dictar texto** → recortar espacios con el mismo reemplazo; si queda vacío, detener.
8. **Diccionario**: `kind` Texto `reply`, `request_id` Texto `ReplyID`, `prompt` Texto dictado, `job_id` Texto `JobID`, `input_revision` Número `Revision`, `acknowledged` Booleano falso. Guarda `pending.json` exactamente como en el atajo principal, antes de la red.
9. Ejecuta «First Mate Enviar pendiente» y detén. Esta operación continúa **el mismo job y voice_session_id**. No se envía una nueva petición `/jobs` para contestar una pregunta.

Un `409/conflict` con este borrador significa que no puede aplicarse a la pregunta seleccionada (o que el ID pertenece a otra operación). No cambies la revisión y reenvíes automáticamente. Conserva el fichero para revisión, consulta de nuevo las preguntas y, después de decidir descartar esa respuesta obsoleta, archívalo fuera de `pending.json` y vuelve a ejecutar «First Mate Responder» para dictar una respuesta nueva. Un simple timeout se resuelve con **reintentar el borrador**, sin consultar ni elegir de nuevo. El servidor comprueba revisión y encolado en la misma transacción.

## Action Button, Siri y prueba en iPhone

Primero ejecuta cada atajo desde Atajos, con el teléfono desbloqueado. Autoriza micrófono/dictado, acceso a la carpeta y conexión a la URL privada cuando iOS lo solicite. Comprueba que el diccionario guardado se vuelve a leer con sus tipos correctos. No publiques capturas con configuración o dictados privados.

En un iPhone compatible: **Ajustes → Botón de acción → Atajo → Elegir un atajo → First Mate**. Mantén pulsado para ejecutarlo. Para cambiar entre envío y respuesta desde el mismo botón, puedes crear un atajo lanzador con **Elegir del menú** («Nueva petición» / «Responder») que ejecute uno de los dos; no adivines automáticamente la intención del dictado. Apple describe el [Action button](https://developer.apple.com/design/human-interface-guidelines/action-button) y la [ejecución de atajos con Siri](https://support.apple.com/en-gb/HT209055). Con Siri, pronuncia el nombre: «Siri, First Mate» o «Siri, First Mate Responder»; iOS puede pedir desbloqueo según las acciones y permisos.

Validación manual pendiente en hardware; no se afirma haber probado un iPhone, Siri, AirPods ni entrega ntfy real desde esta entrega:

| Prueba | Resultado esperado |
| --- | --- |
| Dictado vacío | Termina sin POST ni nuevo borrador |
| Petición simple por Wi-Fi y por datos móviles/Tailscale | «Enviado» pocos segundos después de acabar el dictado; un job |
| Trabajo lento | Atajo finalizado y teléfono bloqueado; trabajo sigue; resultado por ntfy después |
| Desconexión tras envío / confirmación perdida | Borrador sigue disponible; mismo UUID al reintentar; un job |
| Token incorrecto / servicio inaccesible | Nunca dice «Enviado»; no regenera UUID |
| Una pregunta pendiente | Lee solo esa pregunta; respuesta conserva job/sesión |
| Dos preguntas, incluso con el mismo texto | Elección explícita; continúa solo el ID elegido |
| Pregunta respondida/cancelada desde otro cliente durante el dictado | Conflicto; no contesta una pregunta posterior |
| Action Button, Siri y AirPods | Dictado y «Enviado» por el dispositivo previsto, sin leer respuesta completa ni diagnósticos |
| ntfy con pantalla bloqueada | Notificación real de pregunta/resultado según la configuración del proveedor y de iOS |

Las pruebas automáticas cubren HTTP y procesos locales. Para medir el objetivo móvil, registra solo duración desde final del dictado hasta «Enviado», modo de red y si llegó la notificación; no el token ni contenido privado.

## Distribución del atajo

No se incluye un `.shortcut` supuesto, renombrado desde JSON/plist, ni un enlace iCloud inventado. Esta entrega Linux no dispone del mecanismo Apple para producir y verificar un atajo firmado/importable de forma reproducible. Construye las acciones anteriores en el iPhone y pruébalas allí. Apple sí permite [firmar atajos con la CLI de macOS](https://support.apple.com/en-ae/guide/shortcuts-mac/-apd455c82f02/mac); al firmarlos, Apple recibe una copia para validación. Si posteriormente distribuyes uno por exportación o enlace iCloud, hazlo desde Atajos con su mecanismo soportado, elimina primero secretos/datos personales y verifica la importación en otro dispositivo. No se requiere ese artefacto para usar este flujo.
