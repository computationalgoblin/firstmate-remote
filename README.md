# Firstmate Remote

> **EN** — Asynchronous voice remote for [First Mate](https://github.com/kunchenguid/firstmate), the open-source agent supervisor by [kunchenguid](https://github.com/kunchenguid) ([myfirstmate.io](https://myfirstmate.io)). Dictate a task from an iPhone Shortcut, hang up, get an ntfy push when the live First Mate session answers or needs input, and listen to the result later. Zero runtime dependencies, SQLite job queue, token-authenticated loopback HTTP gateway exposed through Tailscale Serve, systemd units and 57 offline tests. It is an independent companion project: it plugs into First Mate's voice-file contract and does not modify First Mate or [herdr](https://github.com/herdrdev/herdr).
>
> **ES** — Mando remoto de voz asíncrono para [First Mate](https://github.com/kunchenguid/firstmate), el supervisor de agentes de código abierto de kunchenguid. Proyecto independiente: se conecta al contrato de voz de First Mate sin modificarlo. Para ejecutarlo necesitas una instalación de First Mate con la extensión de voz activa.

Backend local asíncrono para enviar trabajos a la **sesión viva de First Mate**, cerrar el cliente y consultar o responder después. La Fase 4 del MVP añade un feed autenticado de voz a SQLite, cola serial, CLI, gateway, worker independiente y notificaciones ntfy. El iPhone dicta, recibe «Enviado» tras persistir el trabajo y termina. ntfy avisa; el usuario inicia **«Leer First Mate»** por Siri, Action Button o Atajos para escuchar resultados y preguntas sin conocer los IDs ni usar una terminal. No hay aplicación iOS nativa ni automatización `push → Speak Text`.

La integración utiliza el contrato real de la extensión de voz de First Mate:

```text
Shortcut → gateway HTTP ─┐
CLI ────────────────────┴→ SQLite → worker → state/voice/turns/<id>.request.json
                              ↓ extensión del primario vivo
                        .claimed.json → .answer.json | .error.json
                              ↓
                       SQLite: resultado + eventos → ntfy opcional
```

Herdr proporciona identidad, observación y cancelación mediante su socket Unix; nunca es el canal de contenido. No se modifican los núcleos de First Mate ni Herdr, ni se lanza otro primario. El [contrato de integración](docs/integration.md) concreta los cambios respecto a las APIs conceptuales del [PRD](docs/PRD.md).

## Instalación

Linux con Python 3.11 o posterior, SQLite y la extensión `fm-primary-voice.ts` v1 activa en el primario Pi. El paquete no tiene dependencias de ejecución externas.

```bash
python3 -m venv ~/.local/share/fmvoice/venv
~/.local/share/fmvoice/venv/bin/pip install .
mkdir -p ~/.config/fmvoice
cp config.example.toml ~/.config/fmvoice/config.toml
chmod 600 ~/.config/fmvoice/config.toml
```

Añade `~/.local/share/fmvoice/venv/bin` a tu `PATH`, o usa la ruta completa en los comandos siguientes. Rellena el TOML antes de arrancar. No se incluye ninguna ruta de sesión real ni tema de notificación.

## Configuración

| TOML | Variable que lo reemplaza | Uso |
| --- | --- | --- |
| `firstmate_home` | `FM_HOME` | Home cuyo primario tiene la extensión de voz activa |
| `database` | `FMVOICE_DATABASE` | SQLite local; una base por home |
| `herdr_socket` | `FMVOICE_HERDR_SOCKET` | Socket Unix explícito de la sesión Herdr |
| `herdr_session` | `FMVOICE_HERDR_SESSION` | Nombre de sesión registrado en la identidad |
| `herdr_pane` | `FMVOICE_HERDR_PANE` | Pane del primario, por ejemplo `w1:p1` |
| `transport_timeout` | — | Límite por intercambio RPC, por defecto 5 s |
| `claim_timeout` | — | Espera máxima de claim, por defecto 15 s |
| `poll_interval` | — | Sondeo del worker, por defecto 0,25 s |

`--config /ruta/config.toml` o `FMVOICE_CONFIG` selecciona el fichero. Las rutas relativas se resuelven respecto al directorio del proceso; usa rutas absolutas o `~` para un servicio. Todos los clientes y el worker deben usar la misma configuración.

El socket explícito determina el destino; `herdr_session` etiqueta la identidad persistida, no selecciona un destino alternativo. La salud verifica que socket y pane coincidan con `HERDR_SOCKET_PATH` y `HERDR_PANE_ID` del PID de `state/voice/binding.json`, que el PID siga vivo y que `agent.get` dé una identidad de conversación. No se usa `HERDR_SESSION` ambiental como aislamiento. Consulta los valores de tu instalación con las herramientas administrativas autorizadas; en un laboratorio, exclusivamente mediante el helper descrito más abajo.

## Arranque y parada

Para observar el worker en primer plano:

```bash
fmvoice worker
```

Para que sobreviva a cerrar una terminal, instala el servicio de usuario incluido:

```bash
mkdir -p ~/.config/systemd/user
cp config/fmvoice.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now fmvoice.service
fmvoice health
```

La unidad presupone las rutas de instalación anteriores. Modifica `ExecStart` si instalaste en otra ubicación. Para que el servicio de usuario sobreviva también al cierre de **todas** las sesiones del usuario, configura `loginctl enable-linger "$USER"` si la política de la máquina lo permite. First Mate y Herdr deben seguir vivos por sus propios medios.

```bash
systemctl --user stop fmvoice.service
systemctl --user start fmvoice.service
journalctl --user -u fmvoice.service -n 100
```

Parar el worker no cancela el turno del primario. Al arrancar, vuelve a observar los IDs persistidos y sus ficheros. No hay timeout de duración total del job. Los envíos realizados con el worker parado quedan en cola.

## iPhone y gateway HTTP

`fmvoice gateway` ejecuta el servicio de envío en `127.0.0.1:8765`, con Bearer obligatorio desde `FMVOICE_API_TOKEN`. Reutiliza SQLite y no depende del turno ni del transporte Herdr para confirmar. Mantén el worker en ejecución para procesar la cola y publicar por ntfy.

- [Despliegue, contrato HTTP, seguridad y operación](docs/http-api.md): servicio `config/fmvoice-gateway.service`, token privado, HTTPS con Tailscale Serve y límites.
- [Construcción exacta de los atajos en iPhone](docs/ios-shortcut.md): «First Mate», «Leer First Mate» y «First Mate Responder»; cursor durable después de cada lectura, paginación, reintentos, Action Button, Siri y pruebas manuales.

`GET /voice/events?after=0&limit=20` ofrece solo eventos hablables en orden de ID, con `next_cursor` y `has_more`. Repetir GET no consume nada: el Shortcut guarda cada `event_id` **después** de terminar «Leer texto». Si se interrumpe antes de guardarlo, lo repetirá. El feed conserva preguntas históricas; para contestar se consultan las pendientes con «First Mate Responder» y se elige explícitamente si hay varias. No depende de que ntfy haya entregado el aviso. Announce Notifications es una mejora opcional pendiente de prueba física, igual que bloqueo y ruta de audio.

No se publica un `.shortcut` sin verificar. La validación en iPhone/AirPods y la configuración de Tailscale/ntfy del dispositivo quedan como pasos de instalación; la suite prueba el transporte con dobles locales.

## CLI

Todos los comandos devuelven JSON; un error de comando sale por stderr con código 1.

```bash
fmvoice submit 'Revisa los tests' --request-id movil-001
fmvoice jobs
fmvoice status <job-id>
fmvoice show <job-id>
fmvoice reply <job-id> 'Sí, mantén compatibilidad' --request-id movil-002
fmvoice cancel <job-id>
fmvoice status
fmvoice health
```

Conserva el `request_id` al reintentar. Repetirlo devuelve el mismo job, incluso si cambió el texto enviado. Sin `--request-id`, la CLI genera uno; repetir el comando sin conservarlo crea otro trabajo. `reply` también es idempotente y conserva el job y su `voice_session_id`. Para agrupar nuevos trabajos puedes pasar `submit --voice-session-id <id>`.

Los estados son `queued`, `running`, `waiting_for_input`, `completed`, `failed` y `cancelled`. Una respuesta a una pregunta pasa de `waiting_for_input` a `queued` y después a `running`, respetando la cola. `accepted` significa persistido en SQLite; el claim real se registra por separado. Un job `completed` representa la vuelta final del primario: **no certifica que todas las tareas que haya delegado hayan terminado**.

`cancel` sobre un job en cola o esperando input es inmediato. Sobre uno en ejecución registra una solicitud durable; el estado sigue `running` con `cancel_requested=1` hasta retirar el fichero pendiente o recibir el resultado de la extensión tras Escape. Esto evita liberar la cola mientras el turno sigue en vuelo. Cancelar un job terminal no hace nada.

## ntfy

El proveedor de notificaciones elegido es **ntfy**. La implementación es opcional y consume el outbox de eventos persistido, fuera del Job Manager. Configura localmente:

```toml
[notifications]
provider = "ntfy"
enabled = true
server = "https://tu-servidor-ntfy"
topic_env = "FMVOICE_NTFY_TOPIC"
token_env = "FMVOICE_NTFY_TOKEN"
timeout = 5
click = "" # Opcional: "", URL fija de Leer o "auto".
```

Guarda las variables con tus valores reales en `~/.config/fmvoice/notifications.env` con permisos `600`; la unidad systemd lo carga. En primer plano, expórtalas en el entorno. Para un servidor sin autenticación, configura `token_env = ""`. Nunca versiones ese fichero ni el tema.

Se publica por HTTPS con el [formato JSON oficial de ntfy](https://docs.ntfy.sh/publish/#publish-as-json). Solo se envían pregunta o `spoken_response` para `needs_input`, `completed`, `failed` y `cancelled`. No se envían prompts, respuesta detallada, errores técnicos ni logs. No se siguen redirecciones con credenciales. Los fallos del proveedor se reintentan cada 5 s sin modificar el job; tras un crash puede repetirse una notificación (entrega al menos una vez). Activar ntfy más tarde entrega también los eventos pendientes existentes. La configuración del cliente iOS se describe en el flujo de Shortcuts; no se añaden APNs ni reproducción automática del resultado.

Cada aviso lleva título, prioridad y etiqueta fijos según el tipo: `needs_input` → «First Mate pregunta» (prioridad 4), `completed` → «First Mate: listo» (3), `failed` → «First Mate: error» (4) y `cancelled` → «First Mate: cancelado» (2). Dependen solo del tipo de evento, nunca del contenido.

Para abrir un atajo **al tocar** el aviso, `click` admite exactamente `""`, `"shortcuts://run-shortcut?name=Leer%20First%20Mate"` (siempre Leer) o `"auto"` (las preguntas abren «First Mate Responder»; el resto, «Leer First Mate»). Se rechazan otros destinos, parámetros, tipos y claves desconocidas. La URL es fija: no lleva token, job, pregunta ni texto hablado. Mantén el valor vacío hasta validar el enlace en tu iPhone; tocar puede requerir desbloqueo. Consulta [Click action de ntfy](https://docs.ntfy.sh/publish/#click-action) y el [esquema URL de Apple](https://support.apple.com/guide/shortcuts/apd624386f42/ios).

## Seguridad y depuración

- Gateway TCP exclusivamente en loopback, token obligatorio y HTTPS privado mediante Tailscale Serve. No expone Herdr a Internet. La CLI administrativa sigue siendo local y tiene una superficie más amplia que la API pública.
- Los prompts se escriben como JSON atómico, nunca como comandos de shell. El límite es 16 KiB **incluido el envoltorio**, compatible con el contrato v1.
- SQLite, sus eventos y los turnos contienen información privada. Usa almacenamiento local privado; el worker/CLI aplica `umask 077` y los ficheros nuevos se crean con permisos restrictivos. No compartas la base ni los backups.
- `show` permite consultar por separado `spoken_response`, `full_response`, `question` y `error`. Solo `spoken_response` o la pregunta deben usarse como voz; no leas en voz alta el JSON completo.
- `fmvoice show <job-id> --internal` añade diagnósticos de transporte, prompts envueltos e identidades. Es una superficie administrativa privada, no una salida para TTS. No recoge pantallas, tool calls ni transcripciones de Pi.
- Si la respuesta final no cumple el esquema de voz, el job falla con una frase genérica. El texto bruto permanece únicamente en el fichero de la extensión; no se convierte mediante heurísticas en voz.
- Para investigar un job parado, consulta `status`, `health`, eventos internos y los ficheros de **ese ID** en `state/voice/turns`. Salud temporalmente inaccesible conserva el turno activo. `blocked` o `idle` de Herdr nunca se interpretan como `needs_input`.
- Un `fmvoice-worker.lock` estático es normal: la exclusión se basa en `flock`, no en la presencia del fichero. Mantiene además la asociación home/base incluso con el worker parado. No lo borres con un worker activo. Para cambiar de base, para el servicio, reconcilia los turnos pendientes, migra la base con backup y actualiza esa asociación conscientemente.

Consulta [recuperación y límites del contrato](docs/integration.md#recuperación-y-cancelación) antes de intervenir en un turno incierto. Esta fase no añade un comando de reenvío automático: la incertidumbre no debe duplicar acciones del usuario.

## Pruebas

```bash
python3 -m unittest discover -v
```

La suite determinista usa directorios temporales, sockets Unix falsos y una extensión de voz simulada. Prueba estados, transiciones, concurrencia de la cola, idempotencia, preguntas/respuestas, errores, cancelación, transporte, outbox y recuperación. La prueba entre procesos lanza CLI, worker y doble de extensión con configuración temporal: termina el cliente, reinicia el worker con un turno reclamado y consulta el resultado después. Otra prueba entre procesos termina el cliente HTTP mientras el worker mantiene el job reclamado, y obtiene el resultado tras liberar el doble. También se prueban autenticación, límites, rate limiting, validación estricta y redacción de campos privados. No usa red externa, modelo ni sesión real.

La prueba viva está fuera del descubrimiento normal, omite la ejecución salvo opt-in y solo verifica salud/esquema del plano de control:

```bash
export HERDR_LAB_HELPER=/ruta/al/fm-herdr-lab.sh-autorizado
FMVOICE_LIVE_HERDR=1 tests/live-herdr.sh
```

El helper genera una sesión `fm-lab-*`, instala teardown con tripwire y añade `--session` al final de cada llamada. Nunca apunta a `default`; no lanza Pi ni envía un prompt. Las pruebas reales de contenido de Pi pertenecen al spike previo; aquí se preserva su contrato con dobles deterministas.
