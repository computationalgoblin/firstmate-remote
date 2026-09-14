# Gateway HTTP privado (Fases 3–4)

El gateway es un transporte de la misma `Repository` SQLite que usa la CLI. El worker sigue ejecutando `JobManager` y entregando eventos a ntfy. Arrancar el gateway no arranca el worker, First Mate ni Herdr. Salud HTTP comprueba acceso a la base, no disponibilidad del primario. Una petición aceptada con el worker parado queda en cola.

## Despliegue

1. Instala el paquete y rellena la configuración común según el [README](../README.md). Gateway y worker deben apuntar a la misma base y home. Crea el directorio privado de la base antes de iniciar la unidad con `ProtectSystem=strict`:

   ```bash
   install -d -m 700 ~/.config/fmvoice ~/.local/state/fmvoice
   ```

2. Genera el secreto **en tu instalación**, sin copiarlo a Git, historial de shell ni logs. Este ejemplo escribe el fichero solo si todavía no existe; no imprime el valor:

   ```bash
   python3 - <<'PY'
   import os, secrets
   from pathlib import Path
   os.umask(0o077)
   path = Path('~/.config/fmvoice/gateway.env').expanduser()
   with path.open('x') as f:
       f.write('FMVOICE_API_TOKEN=' + secrets.token_urlsafe(32) + '\n')
   PY
   ```

   El nombre de variable puede cambiarse con `gateway.token_env`; su valor debe contener 32–256 caracteres URL-safe (`A–Z a–z 0–9 _ -`). No hay token predeterminado ni autenticación desactivable. Copia el valor al iPhone por un medio privado. No incluyas credenciales en URL, capturas, exportaciones de Shortcuts ni informes. El fichero de ejemplo contiene únicamente el **nombre** de variable. La configuración `[gateway]` rechaza claves desconocidas y listeners fuera de IPv4 loopback.

3. Instala la unidad:

   ```bash
   cp config/fmvoice-gateway.service ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now fmvoice-gateway.service
   ```

   La unidad usa `%h`, sin nombres ni rutas personales, y carga obligatoriamente `gateway.env`. Si cambias la ruta de SQLite, adapta `ReadWritePaths` al directorio que contiene la base y sus ficheros WAL/SHM. En primer plano: carga las variables privadas en el entorno y ejecuta `fmvoice gateway`. El puerto predeterminado es `8765`; `0` selecciona un puerto efímero para pruebas. El servicio maneja SIGTERM/SIGINT y deja terminar las peticiones acotadas; no cambia la ejecución de los jobs.

4. Acceso preferido: conecta PC e iPhone a tu tailnet, habilita HTTPS de Tailscale y configura **Serve** para reenviar al listener:

   ```bash
   tailscale serve --bg http://127.0.0.1:8765
   tailscale serve status
   ```

   Usa en el Shortcut la URL HTTPS exacta que imprima Serve. Serve restringe el acceso a la tailnet; sus reglas de acceso deben permitir solo los usuarios/dispositivos previstos. El Bearer sigue siendo obligatorio, también para `/health`. No uses Funnel ni abras el puerto en el router/firewall. No se modifica ni publica el socket de Herdr. No se confía en cabeceras `X-Forwarded-For` o identidad de proxy como autenticación. Consulta la [documentación oficial de Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve) para opciones y administración del listener existente; no sustituyas otros servicios sin revisar su configuración.

No se ha configurado Tailscale ni se han generado credenciales en esta entrega. El repositorio permanece privado.

Al actualizar desde Fase 3, haz backup privado de SQLite y actualiza gateway/worker/CLI juntos. Para durante esa actualización solo los servicios de este paquete, `fmvoice.service` y `fmvoice-gateway.service`; no First Mate ni Herdr. Al abrir la base se aplica transaccionalmente la migración v2: añade un índice parcial de eventos hablables, sin alterar IDs, historial ni flags ntfy. El binario anterior rechaza la versión v2, por lo que no debe quedar un worker antiguo usando esa base. Después arranca los servicios actualizados; el worker reconcilia el turno existente según el contrato de recuperación. No se ha realizado despliegue en esta entrega.

## Contrato

Todas las rutas requieren `Authorization: Bearer <token privado>`. POST usa `Content-Type: application/json` (opcional `; charset=utf-8`) y `Content-Length`. Solo `/voice/events` admite query string, con los parámetros descritos abajo. No se admiten slash final, aliases, campos desconocidos ni cuerpos en GET. Las respuestas son JSON UTF-8, sin caché y con cierre de conexión. No hay CORS, páginas, redirecciones ni acceso a ficheros. «Público» describe el esquema permitido al cliente; nunca acceso anónimo.

| Método/ruta | Cuerpo | Resultado |
| --- | --- | --- |
| `GET /health` | ninguno | `200 {"status":"ok"}` si la base es accesible |
| `POST /jobs` | `request_id`, `prompt`; opcional `voice_session_id` | `202`, recibo durable inmediato |
| `GET /jobs/{id}` | ninguno | `200`, estado público del job |
| `GET /jobs/pending-input` | ninguno | `200`, `jobs` con preguntas y `has_more` |
| `GET /voice/events?after=0&limit=20` | ninguno | `200`, feed de voz con `events`, `next_cursor`, `has_more` |
| `POST /jobs/{id}/reply` | `request_id`, `prompt`, `input_revision` | `202`, continuación del mismo job/sesión |
| `POST /jobs/{id}/cancel` | `{}` | `202`, cancelación aplicada o intención durable |

`request_id` es obligatorio para crear y responder; UUID es la opción recomendada. Tanto este campo como `voice_session_id` admiten 1–200 caracteres `A–Z a–z 0–9 _ -`. El prompt debe ser texto no vacío. `input_revision` es el entero positivo devuelto junto a la pregunta; **no se calcula en el cliente**.

Ejemplo de cuerpo de envío (identificadores ilustrativos, ninguna credencial):

```json
{"request_id":"513adcfb-c431-4dd3-91bc-f94f972c3e32","prompt":"Revisa las pruebas"}
```

El recibo para los tres POST contiene exclusivamente:

```json
{"accepted":true,"id":"7d9884e8-90c7-4fd9-8ee1-c9a4aadca630","voice_session_id":"c438276f-aee9-4506-8c88-7b73281eb871","state":"queued","cancel_requested":false}
```

`accepted` significa commit confirmado. No implica claim, ejecución ni finalización. Un reintento puede devolver `running`, `waiting_for_input`, `completed`, `failed` o `cancelled`: sigue siendo el mismo recibo válido. Nunca espera a First Mate, consulta Herdr ni ejecuta un tick del manager.

Los GET de jobs devuelven únicamente `id`, `voice_session_id`, `state`, `created_at`, `updated_at`, `cancel_requested`, `spoken_response`, `question` y, mientras espera input, `input_revision`. No devuelven `request_id` original, prompt, `full_response`, errores internos, identidades, eventos de ejecución, razonamiento, herramientas, logs ni rutas. Los timestamps son segundos Unix. Solo la pregunta o `spoken_response` sirven para voz; los campos estructurados de voz mantienen el límite semántico descrito en [integración](integration.md): no existe un filtro que garantice el contenido de un campo válido generado por el modelo.

`pending-input` devuelve hasta 100 jobs, ordenados por creación/ID. `has_more=true` indica que la lista está truncada: jamás se interpreta una lista truncada como «solo existe una pregunta». Se puede seleccionar un elemento explícito de la lista visible; para acceder a los restantes hay que resolver/cancelar preguntas anteriores o usar la CLI administrativa. No hay selección automática por texto coincidente ni por «más reciente».

## Feed de voz v1: cursor y paginación sin confirmación remota

`GET /voice/events` acepta `after` (predeterminado `0`, entero entre `0` y `9007199254740991`) y `limit` (predeterminado `20`, entero entre `1` y `50`). Solo dígitos decimales canónicos: sin signo, ceros iniciales salvo `0`, fracciones, exponentes ni codificación porcentual. Cualquier orden de parámetros es válido; claves desconocidas, repetidas, vacías o fuera de rango dan `400/invalid_query`. Un cursor superior al último ID persistido da `409/cursor_ahead`, útil para detectar una base restaurada o configuración equivocada. El rango numérico mantiene enteros exactos en clientes JSON; si la base lo agotara, el feed falla sin omitir eventos.

Ejemplo, dos eventos cercanos (IDs ilustrativos):

```json
{
  "events": [
    {"event_id": 12, "job_id": "7d9884e8-90c7-4fd9-8ee1-c9a4aadca630", "event_type": "completed", "spoken_response": "Listo.", "at": 1789380000.0},
    {"event_id": 15, "job_id": "814a8d99-f3c7-4e4b-b15e-273eeea386c1", "event_type": "needs_input", "question": "¿Continuamos?", "at": 1789380000.0}
  ],
  "next_cursor": 15,
  "has_more": false
}
```

Cada evento contiene **exactamente cinco campos**: `event_id`, `job_id`, `event_type`, `at` y **uno** de `question` (solo `needs_input`) o `spoken_response` (`completed`, `failed`, `cancelled`). El texto tiene 1–900 caracteres y no es blanco. Solo se selecciona el canal `user` y esos cuatro tipos; nunca se serializa el payload entero ni se consulta la respuesta actual del job para sustituir el evento histórico. Un evento de voz corrupto produce `503/storage_unavailable`, sin filtrarlo ni saltarlo.

Los IDs proceden del `AUTOINCREMENT` existente, no de timestamps: son crecientes dentro de esta base, estables entre reinicios y pueden tener huecos. SQLite serializa las escrituras y confirma resultado/evento juntos. La selección usa `id > after`, orden ascendente y una fila extra para `has_more`; ese lookahead **no** se incluye en `next_cursor`. Los resultados confirmados durante o después de una página se recuperan en la siguiente consulta. `has_more=false` describe ese snapshot, no impide llegadas posteriores.

`next_cursor` es el último ID **devuelto**, o el `after` recibido cuando `events=[]`. No es una confirmación. GET no altera `notified`, los eventos, jobs ni ningún estado de escucha; un GET perdido o repetido vuelve a entregar los mismos elementos, más las nuevas llegadas que quepan. ntfy y cada dispositivo tienen progreso independiente. Guarda el cursor local solo tras pronunciar **cada elemento**; nunca copies `next_cursor` al empezar o tras leer únicamente el primero. Si se cae después del audio y antes del guardado, se repite ese audio: se prioriza repetición sobre pérdida.

Las preguntas permanecen en el historial aunque ya estén respondidas. Para responder usa `/jobs/pending-input` y la revisión vigente; no se responde directamente desde el feed. No hay purga automática ni ventana temporal de resultados. La garantía depende de conservar esta base y su historial. No borres eventos pendientes de lectores ni sustituyas SQLite silenciosamente. Al cambiar/restaurar la base, restablece conscientemente el cursor local a `0` para releer lo conservado: IDs de bases distintas no son comparables, incluso si el cursor cabe en ambas. La pérdida física de SQLite no puede recuperarse con un cursor.

## Reintentos, carreras y cancelación

Conserva el mismo `request_id` **y el mismo cuerpo** hasta recibir un recibo válido. La base conserva la idempotencia entre clientes, conexiones y reinicios: repetir un ID devuelve el job original aunque el texto cambie. Reutilizarlo para otra operación/job produce `409`. No lo regeneres tras timeout, `408`, `429` o `503`: el servidor pudo haber confirmado la escritura y perdido solo la respuesta de red. El rate limiting también afecta a reintentos.

Cada respuesta usa un UUID nuevo y la revisión de la pregunta seleccionada. La revisión se comprueba dentro de la transacción que encola la continuación. Una pregunta ya respondida/cancelada o sustituida produce `409`; vuelve a consultar y seleccionar, sin aplicar el dictado automáticamente a otra pregunta. Repetir el UUID de una respuesta ya aceptada sigue siendo idempotente incluso si después aparece otra pregunta. La CLI mantiene compatibilidad; no exige revisión.

Cancelar un job `running` solo registra `cancel_requested=true`: el worker reconcilia el turno según el contrato existente. La API no envía Escape ni libera la cola. Cancelar un estado terminal devuelve el estado existente. El endpoint no expone cancelación fuerte de trabajos delegados.

## Límites y errores

- Cuerpo máximo: 16 KiB de bytes JSON; además, el repositorio aplica 16 KiB al transcript envuelto. Un texto que cabe en HTTP puede fallar con `413` al añadir el envoltorio.
- Cabeceras, incluida la línea inicial: 8 KiB en total; máximo 32 cabeceras y 4 KiB por línea. Cabeceras duplicadas, controles, framing ambiguo, compresión, `Transfer-Encoding`, `Expect` y `Upgrade` se rechazan. JSON debe ser un objeto UTF-8, sin claves repetidas, constantes no JSON, tipos incorrectos o sustitutos Unicode aislados.
- Plazo absoluto de lectura de cabeceras y cuerpo: 3 s por defecto, incluso con goteo de bytes. SQLite espera como máximo 0,5 s por bloqueo; escritura al socket, 0,5 s. Son límites de transporte, no del trabajo. La velocidad móvil y el timeout propio de Shortcuts quedan fuera del control del servidor.
- Máximo 16 conexiones atendidas simultáneamente y backlog 16; saturación devuelve `503` cuando es posible. Rate limiting global de 60 peticiones por ventana fija de 60 s, incluidas autenticaciones fallidas; configurable. No depende de IPs que Serve podría agrupar. Es un límite básico en memoria: se reinicia con el servicio, una credencial comparte cuota y las peticiones malformadas se acotan por tamaño/plazo/concurrencia.
- Errores públicos: `400` formato/campos, `401` autenticación, `404` ruta/job, `405` método, `408` plazo, `409` conflicto, `413` tamaño, `415` tipo, `429` cuota, `431` cabeceras, `503` almacenamiento/saturación y `500` fallo genérico. El cuerpo es solo `{"error":"codigo_estable"}`; nunca incluye la excepción ni datos del request. `429/503` aconsejan `Retry-After: 60` (también si configuraste otra ventana).

No hay access log ni tracebacks de requests. Diagnóstico local: estado de ambas unidades, `fmvoice status`, `fmvoice health` y, con la privacidad apropiada, la CLI interna. Una caída de gateway deja jobs y outbox intactos. Para rotar el token, cambia el fichero privado, reinicia **solo** `fmvoice-gateway.service` y actualiza el iPhone; no hay que reiniciar worker, First Mate ni Herdr. Configura la retención y backups de SQLite como datos privados.
