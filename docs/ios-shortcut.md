# iPhone: enviar, escuchar y responder sin terminal

Este flujo usa Atajos (Shortcuts), HTTPS privado de Tailscale y el gateway de [Fases 3–4](http-api.md). «First Mate» envía, pronuncia **«Enviado»** tras el commit y termina. El worker continúa en el PC; **ntfy avisa y el usuario inicia «Leer First Mate»** para escuchar resultados o preguntas. «First Mate Responder» permite contestarlas. El MVP funciona bajo demanda sin conocer cada job ni usar una terminal. La llegada de un push no ejecuta un Shortcut ni `Speak Text`; Announce Notifications es una mejora opcional, pendiente de prueba física.

La decisión sigue el informe autorizado `investigar-ntfy-ios-voz/report.md` del 14-09-2026. Su propuesta conceptual se concreta aquí como `/voice/events`, paginado, y el cursor se guarda **después** de terminar el audio, no antes. Las instrucciones siguientes son una receta de construcción, todavía no una validación en hardware.

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

1. **Obtener archivo de carpeta** `FirstMate/pending.json`, con «Error si no se encuentra» desactivado. Añade **Si** el resultado tiene valor; en esta condición la variable debe ser de tipo **Archivo**. Dentro, usa **Obtener diccionario de la entrada** y extrae `acknowledged`. Añade **Si** `acknowledged` es verdadero; en esta condición debe ser de tipo **Booleano**, y la rama verdadera continúa sin menú. En la rama **Si no**, usa **Elegir del menú**: «Reintentar pendiente» → ejecutar «First Mate Enviar pendiente» y detener; «Salir» → detener. Si el JSON no es válido, deja que la acción se detenga y revisa el fichero; no sobrescribas una operación incierta.
2. **Ejecutar atajo** «First Mate UUID» → **Establecer variable** `RequestID`. Se genera una sola vez por operación; no dentro de reintentos.
3. **Dictar texto** (Dictate Text), idioma español, finalizar al dejar de hablar (o al tocar, según preferencia) → `Dictado`.
4. **Reemplazar texto**, expresión regular activada, patrón `^\s+|\s+$`, reemplazo vacío, sobre `Dictado` → `Prompt`. **Si** `Prompt` no tiene valor: **Detener este atajo**. Esto no envía ni guarda una operación vacía.
5. **Diccionario** con `kind` Texto `request`, `request_id` Texto `RequestID`, `prompt` Texto `Prompt`, `acknowledged` Booleano falso. No pongas comillas alrededor de las variables.
6. **Obtener texto de la entrada** del diccionario, **Definir nombre** `pending.json`, **Guardar archivo** en `FirstMate`, sin preguntar ubicación, sobrescribir activado. El guardado debe completarse **antes** del POST. Solo sustituye aquí el recibo anterior ya confirmado.
7. **Ejecutar atajo** «First Mate Enviar pendiente»; **Detener este atajo** al volver.

Al acabar el dictado, el único intercambio obligatorio de red es el POST. En una conexión disponible debería tardar pocos segundos; el servidor solo espera SQLite. No hay garantía de duración si iOS está sin cobertura, Tailscale está desconectado o falta un permiso: el plazo propio de la acción de red lo decide iOS. Puedes cerrar/cancelar la interfaz en ese caso y reintentar el borrador más tarde con el mismo UUID.

## Atajo «First Mate Responder»

Para construirlo por etapas en el dispositivo, consulta también la [guía práctica autocontenida de «First Mate Responder»](ios-shortcut-responder.md), con bloques verificables y tipos explícitos para cada condición «Si».

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

## Atajo «Leer First Mate»: cursor local y lectura ordenada

Este atajo ignora la entrada que reciba por URL y solo contacta la `base_url` de «First Mate Config». No toma tokens, URLs ni IDs de ntfy. No requiere que una notificación haya llegado: puede leer todo el historial conservado desde `after=0`. La voz procede exclusivamente de `question` o `spoken_response`, jamás del diccionario completo.

Usa **un cursor por dispositivo y base** en `FirstMate/voice-cursor.json`, separado de `pending.json`. Ejecuta un solo lector a la vez; no compartas el fichero entre iPhones por iCloud. Dos ejecuciones solapadas pueden repetir audio o sobrescribir un cursor con otro anterior. Esta receta no ofrece exclusión mutua de Atajos. No conviertas un fichero `busy` residual en un bloqueo permanente.

Formato local (URL ilustrativa; sustituir por la configuración privada):

```json
{"base_url":"https://pc.example.ts.net","after":0}
```

`after` es **Número**, entero de `0` a `9007199254740991`. No es una fecha, contador de jobs ni posición en la página. No guardes `has_more`, texto leído, preguntas ni credenciales en este fichero. Si el archivo falta en el primer uso, empieza en `0`. Si se pierde después, releer desde `0` repite lo conservado. Si está corrupto, detén la lectura y restablécelo conscientemente a `0` desde Archivos/Atajos; nunca adivines el último ID. Un fallo de sobrescritura puede dejar un fichero inválido: esta recuperación favorece repetición.

### Construcción, acción por acción

1. **Ejecutar atajo** «First Mate Config» → `Config`. **Obtener valor del diccionario** para `base_url` → `BaseURL` y `token` → `Token`. Exige ambos como texto no vacío; `BaseURL` debe ser la URL HTTPS fija seleccionada durante la instalación, sin query, fragmento ni slash final. Para `Token`, **Coincidir texto** `^[A-Za-z0-9_-]{32,256}$`; exige una coincidencia completa. Una configuración inválida: **Leer texto** «Revisa la configuración privada de First Mate» y **Detener este atajo**. Nunca leas el token.
2. **Obtener archivo de carpeta**, carpeta `FirstMate`, ruta `voice-cursor.json`, «Error si no se encuentra» desactivado. Si no hay archivo: **Número** `0` → `Cursor`. Si existe: **Obtener diccionario de la entrada** → `Guardado`; exige exactamente las claves `base_url`, `after`, URL igual a `BaseURL` y `after` como entero dentro del rango anterior → `Cursor`. Ante URL distinta, campo ausente, JSON inválido o número inválido, detén sin GET ni sobrescritura; revisa configuración/archivo. Al cambiar de base no reutilices su cursor aunque tenga el mismo dominio: restablécelo conscientemente a `0`.
3. **Número** `0` → `Leidos`. **Repetir** `10` veces (máximo diez páginas por invocación). Dentro del bucle, **Establecer variable** `CursorPeticion` = `Cursor`. Para interpolarlo sin formato numérico regional, crea un **Diccionario** temporal con `after` Número `CursorPeticion`, **Obtener texto de la entrada** para serializar JSON, **Coincidir texto** `"after"\s*:\s*([0-9]+)\s*[,}]` y **Obtener grupo del texto coincidente**, grupo `1` → `CursorURL`; exige exactamente una coincidencia. No uses fechas ni números con separadores de miles. **Texto** `BaseURL/voice/events?after=CursorURL&limit=5`, insertando ambas variables → **URL**.
4. **Obtener contenido de URL**, método **GET**, cabecera `Authorization` = `Bearer ` seguido de `Token`, sin cuerpo. **Obtener diccionario de la entrada** → `Pagina`. No añadas reintento automático ni sondeo con «Esperar». Si Atajos interrumpe por red/HTTP/JSON, no se ejecutan acciones posteriores y el cursor durable anterior se conserva. Si devuelve un diccionario con `error`, aplica la tabla de errores inferior y detén.
5. Valida **toda la página** mediante las acciones y reglas de la siguiente sección, antes de hablar o guardar. Conserva la lista `events` → `Eventos` y `has_more` → `HayMas`. `next_cursor` sirve para comprobar el esquema; **no lo guardes como progreso**.
6. **Contar** `Eventos`. Si es cero: si `Leidos=0`, **Leer texto** «No hay respuestas nuevas»; **Detener este atajo**. No cambies el archivo por una página vacía.
7. **Repetir con cada elemento** de `Eventos`, en el orden recibido. **Obtener valor del diccionario** `event_type`. Si es `needs_input`, extraer **solo** `question` → `Voz`; en los otros tres tipos, extraer **solo** `spoken_response` → `Voz`. **Leer texto** `Voz`, español, desplegar opciones y activar **Esperar hasta que termine** (Wait Until Finished). No uses reproducción en segundo plano. Opcionalmente, antes de una pregunta, leer el literal «Pregunta del historial; usa First Mate Responder para consultar las pendientes»; nunca tratarla como selección de respuesta.
8. **Solo después de volver de Leer texto**, extrae `event_id` del elemento → `Candidato`. **Diccionario**: `base_url` Texto `BaseURL`, `after` Número `Candidato`. **Obtener texto de la entrada** para serializar a JSON; **Definir nombre** `voice-cursor.json`; **Guardar archivo** en `FirstMate`, «Preguntar dónde guardar» desactivado, «Sobrescribir si existe» activado. A continuación **Obtener archivo de carpeta** de esa ruta, convertir a diccionario y verificar URL y `after=Candidato`. Si falla lectura/escritura/verificación, detén sin hablar el siguiente elemento. Tras verificar, **Establecer variable** `Cursor=Candidato` y **Calcular** `Leidos+1` → `Leidos`.
9. Tras **Fin de repetir con cada elemento**, si `HayMas=false`, **Detener este atajo**. Si es verdadero, la siguiente iteración del bucle exterior pide la página siguiente con `Cursor`, ya guardado elemento a elemento. No añadas `+1` al ID: el servidor usa `id > after` y puede haber huecos.
10. Tras las diez iteraciones, **Leer texto** «Quedan respuestas. Vuelve a ejecutar Leer First Mate para continuar» y detener. El límite evita una sesión interminable; la siguiente invocación recupera lo restante. Una nueva llegada después de `has_more=false` se escucha al volver a invocar, sin pérdida.

La finalización de «Leer texto» es la señal disponible para guardar; no demuestra que el usuario haya oído el audio. Si el volumen o la ruta eran incorrectos, puede restablecer el cursor a un ID anterior conocido o a `0` para repetir. Si se cancela antes del guardado, el elemento vuelve a salir; si se guardó, se continúa con el siguiente. **Nunca** coloques el guardado antes de la acción de voz ni al inicio de una página.

### Validación del esquema en Atajos

Construye estas comprobaciones dentro del paso 5 con **Obtener valor del diccionario**, **Todas las claves**, **Contar**, **Obtener tipo**, **Coincidir texto**, **Si** y **Repetir con cada elemento**. Cada condición fallida ejecuta **Leer texto** con el literal «Respuesta de First Mate inválida; no se avanzó la lectura» y **Detener este atajo**. Si una conversión da un error nativo de Atajos, deja que interrumpa. No uses conversiones de texto a número como sustituto de comprobar el tipo JSON.

Para comprobar un conjunto exacto de claves, obtén **Todas las claves**, cuenta y exige el tamaño indicado; crea una **Lista** de claves permitidas y recorre las recibidas: si la lista no contiene una, detén. Para cada número exige tipo Número, finito, rango indicado e igualdad con su valor **Redondear número** a unidades. Los booleanos deben ser booleanos JSON, no texto ni 0/1: si tu iOS los presenta como Número en «Obtener tipo», convierte el diccionario a texto JSON y exige una coincidencia `"has_more"\s*:\s*(true|false)\s*[,}]`. Para `after`, `next_cursor` y `event_id` comprueba además en su diccionario serializado que el valor no está entre comillas ni es `true/false`: patrón `"CLAVE"\s*:\s*[0-9]+\s*[,}]`, sustituyendo CLAVE. En la prueba de construcción incluye expresamente `"1"`, `true`, `1.5` y campos ausentes como casos inválidos.

| Objeto | Comprobaciones obligatorias |
| --- | --- |
| `Pagina` | Diccionario con exactamente `events`, `next_cursor`, `has_more`; `events` es Array/lista JSON con 0–5 elementos, `next_cursor` entero en rango, `has_more` Booleano. No aceptar diccionarios como lista. |
| Cada evento | Diccionario con exactamente cinco claves: `event_id`, `job_id`, `event_type`, `at` y el campo de voz permitido por el tipo. |
| `event_id` | Número entero positivo hasta `9007199254740991`, estrictamente mayor que el anterior (inicializa `Anterior=CursorPeticion`, actualízalo en cada iteración de validación). No exigir IDs consecutivos. |
| `job_id` | Texto que coincide completamente con `^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$`. |
| `event_type` | Texto, miembro exacto de la Lista `needs_input`, `completed`, `failed`, `cancelled`. |
| Voz | `needs_input` exige solo `question`; los demás, solo `spoken_response`. Texto no blanco, **Contar caracteres** entre 1 y 900. Nunca usar un campo alternativo si falta el esperado. |
| `at` | Número finito en segundos Unix; no ordenar ni calcular el cursor con él. Para probar finitud sin formato regional, usa el JSON serializado del evento y exige `"at"\s*:\s*-?[0-9]+([.][0-9]+)?([eE][+-]?[0-9]+)?\s*[,}]`. |
| Coherencia | Si la lista está vacía: `has_more=false` y `next_cursor=CursorPeticion`. Si no: `next_cursor` igual al último `event_id`. Si `has_more=true`: exactamente cinco elementos. |

Los nombres de tipos y acciones varían con el idioma/iOS. Comprueba en el dispositivo que una lista vacía y una lista de un elemento se conservan como arrays al leer `events`; usa el tipo JSON del diccionario serializado (`"events"\s*:\s*\[`) si Atajos presenta el array vacío como «sin valor». No transformes ese caso en una llamada ni en un avance de cursor. Las pruebas Python validan el contrato del gateway; no ejecutan estas acciones de Apple.

### Vacío, red, autenticación y repetición

| Situación | Comportamiento del lector |
| --- | --- |
| `events=[]`, sin lecturas previas en esta invocación | «No hay respuestas nuevas», cursor intacto. No implica que los jobs hayan terminado. |
| Modo avión, Tailscale desconectado, timeout o respuesta perdida | Atajos puede detenerse con su error nativo. Repite «Leer First Mate» cuando vuelva la red; conserva el cursor, sin saltar al final. |
| `401` / `error=unauthorized` | Si el cuerpo llega, leer «Revisa el token privado de First Mate» y detener. Actualizar «First Mate Config» por medio privado; nunca leer el error completo ni el token. |
| `429`, `503`, `408` | Si el cuerpo llega, leer «First Mate no está disponible. Reintenta más tarde» y detener; dejar pasar al menos 60 segundos antes de reintentar `429/503`. No bucle agresivo. |
| `409/cursor_ahead` | «Revisa el cursor y la base de First Mate», detener. Revisar la base/URL y restablecer conscientemente a `0` si hubo restauración/cambio. |
| `400`, otro error o esquema inesperado | «Respuesta de First Mate inválida; no se avanzó la lectura», detener. Corregir la construcción/configuración conservando el archivo. |
| Interrupción después de hablar y antes de guardar | Se vuelve a pronunciar ese evento al reintentar. No deduplicar por texto, hora, job ni aviso ntfy. |
| Dos avisos cercanos o duplicados | Se recorren ambos eventos en orden de ID. Tocar de nuevo consulta a partir del cursor local; un push nunca lo modifica. |
| Pregunta histórica ya contestada | Puede escucharse otra vez, pero «First Mate Responder» consulta el estado actual antes de elegir y dictar. |

La acción estándar de red puede detener el atajo antes de entregar el cuerpo de error y no ofrece aquí un `try/catch` portátil. Por eso no se promete pronunciar una frase de error en todos los iPhones: el requisito de conservación del cursor no depende de capturar ese error.

## ntfy en iOS: aviso y apertura opcional al tocar

En el servidor propio, configura HTTPS, `auth-default-access: deny-all`, ACL por tema, credencial de publicación separada de la de lectura del iPhone y un tema aleatorio. Para entrega iOS inmediata, ntfy documenta `upstream-base-url: https://ntfy.sh`; el upstream recibe hash del URL del tema e ID de mensaje y el teléfono recupera el contenido. Revisa [control de acceso y entrega iOS de ntfy](https://docs.ntfy.sh/config/#ios-instant-notifications). El token HTTP del gateway es distinto del de ntfy.

Instala ntfy iOS, añade servidor y credencial de lectura, y suscríbete al tema privado. Permite notificaciones, entrega inmediata y pantalla bloqueada; excluye ntfy del resumen programado. Los cuerpos contienen texto privado de voz: configura vistas previas según tu privacidad y valida qué aparece en pantalla y se anuncia.

El publicador admite `notifications.click` vacío (predeterminado) o exactamente:

```toml
click = "shortcuts://run-shortcut?name=Leer%20First%20Mate"
```

[ntfy documenta `click`](https://docs.ntfy.sh/publish/#click-action) para abrir un destino al tocar, y [Apple documenta el esquema de ejecución](https://support.apple.com/guide/shortcuts/apd624386f42/ios). La combinación concreta exige **PRUEBA FÍSICA PENDIENTE**. Actívala solo para probar después de construir el atajo; conserva vacío como configuración cotidiana hasta validar. No hay acciones HTTP ni parámetros con texto, secretos o IDs. El enlace no autoriza el GET; el atajo carga su propia configuración. Un toque puede pedir desbloqueo. La mera llegada nunca se presenta como disparador automático.

## AirPods, Focus, bloqueo y anuncios opcionales

Conecta los AirPods y comprueba la salida activa y el volumen antes de invocar «Leer First Mate». En cada Focus relevante, permite ntfy explícitamente si deseas recibir avisos: la prioridad del push no constituye permiso para saltarlo. Apple explica el [control de apps en Focus](https://support.apple.com/en-us/105112). **Pendiente:** silencio activado/desactivado, Focus permitiendo/silenciando ntfy, música en curso, llamada y un solo AirPod; registra ruta de audio, volumen y pausas de música. No se garantiza audio durante llamadas ni por auriculares desconectados.

Opcional: Ajustes → Notificaciones → **Anunciar notificaciones**, activar y comprobar si ntfy aparece entre apps compatibles; si aparece, habilitar sus anuncios. Apple requiere auriculares compatibles puestos, teléfono bloqueado y pantalla apagada; las respuestas habladas al anuncio dependen del soporte de la app. Véase [Announce Notifications](https://support.apple.com/en-us/102536). **Pendiente con ntfy:** lectura íntegra, latencia, vistas previas Always/When Unlocked/Never y compatibilidad real. No uses «Responder» al anuncio como sustituto de «First Mate Responder» ni marques el feed como escuchado por un anuncio: puede repetirse después y es deliberado.

## Action Button, Siri y prueba en iPhone

Primero ejecuta cada atajo desde Atajos, con el teléfono desbloqueado. Autoriza micrófono/dictado, acceso a la carpeta y conexión a la URL privada cuando iOS lo solicite. Comprueba que el diccionario guardado se vuelve a leer con sus tipos correctos. No publiques capturas con configuración o dictados privados.

Para acceso directo a lectura en un iPhone compatible: **Ajustes → Botón de acción → Atajo → Elegir un atajo → Leer First Mate**. Mantén pulsado para ejecutarlo. Si prefieres conservar el botón para enviar, deja «First Mate» y usa Siri para leer; también puedes crear un lanzador **Elegir del menú** («Nueva petición» / «Leer resultados» / «Responder») que ejecute el atajo elegido. Apple describe el [Action Button](https://support.apple.com/guide/iphone/use-and-customize-the-action-button-iphe89d61d66/ios) y la [ejecución con Siri](https://support.apple.com/guide/shortcuts/apd07c25bb38/ios). Invoca «Siri, Leer First Mate», «Siri, First Mate» o «Siri, First Mate Responder». Comprueba que Siri esté permitida con el dispositivo bloqueado. iOS puede exigir desbloqueo para acciones, archivos o permisos: el fallback del MVP es desbloquear y ejecutar el mismo atajo, sin terminal. La lectura bajo demanda es el contrato; manos libres con pantalla bloqueada sigue pendiente de validación.

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
| Leer First Mate sin jobs conocidos, sin ntfy y con dos resultados de igual hora | Lee ambos en orden; cursor queda en el segundo |
| Siete eventos, `limit=5`, otro evento mientras habla | Pagina sin saltos; nuevas llegadas tras el snapshot se recuperan al invocar de nuevo |
| Cancelar antes de hablar, durante audio y después de audio/antes de guardar | Cursor solo tras finalización y guardado; se admite repetición del último |
| Cierre y reapertura de Atajos / reinicio del iPhone | Recupera cursor durable y continúa; archivo perdido se recupera desde 0 |
| Token inválido, modo avión, archivo corrupto, base restaurada | No avanza cursor ni lee JSON/errores privados; recuperación según tabla |
| Tap ntfy con `click` vacío y luego habilitado | Vacío conserva comportamiento ntfy; habilitado abre atajo solo al tocar; anotar desbloqueo |
| Siri y Action Button con pantalla bloqueada/apagada y desbloqueada | Anotar permisos y necesidad de Face ID; validar GET, voz y guardado |
| AirPods, silencio, Focus, música, llamada, un auricular | Anotar salida, volumen y comportamiento; no asumir que silencio/Focus sean equivalentes |
| Announce Notifications on/off y previews Always/When Unlocked/Never | Registrar tono, texto anunciado y exposición; mejora opcional, no requisito de lectura bajo demanda |

Todas las filas están **PENDIENTES DE PRUEBA FÍSICA**. Usa contenido sintético sin secretos y registra modelo de iPhone/AirPods, versiones de iOS/ntfy, modo de red, fecha, resultado y desbloqueos. Objetivo de instalación: lectura y respuesta correctas en al menos 9/10 intentos por Siri/Action Button, sin perder eventos ni seleccionar otro job. Si el bloqueo impide el flujo, documenta uso desbloqueado como experiencia validada; Announce Notifications no condiciona la aprobación.

Las pruebas automáticas cubren HTTP y procesos locales. Para medir el objetivo móvil, registra solo duración desde final del dictado hasta «Enviado», modo de red y si llegó la notificación; no el token ni contenido privado.

## Distribución del atajo

No se incluye un `.shortcut` supuesto, renombrado desde JSON/plist, ni un enlace iCloud inventado. Esta entrega Linux no dispone del mecanismo Apple para producir y verificar un atajo firmado/importable de forma reproducible. Construye las acciones anteriores en el iPhone y pruébalas allí. Apple sí permite [firmar atajos con la CLI de macOS](https://support.apple.com/en-ae/guide/shortcuts-mac/-apd455c82f02/mac); al firmarlos, Apple recibe una copia para validación. Si posteriormente distribuyes uno por exportación o enlace iCloud, hazlo desde Atajos con su mecanismo soportado, elimina primero secretos/datos personales y verifica la importación en otro dispositivo. No se requiere ese artefacto para usar este flujo.
