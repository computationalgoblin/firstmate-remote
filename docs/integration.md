# Integración de Fase 2

## Evidencia y alcance

La implementación sigue el informe autorizado del spike `spike-integracion-herdr`, fechado el 14 de septiembre de 2026, y la cabecera y comportamiento de `.pi/extensions/fm-primary-voice.ts` del home inspeccionado. El spike observó Herdr 0.8.2, protocolo 20. Sus rutas privadas no se incorporan como valores predeterminados al paquete.

Se volvió a verificar en laboratorio el esquema real de `agent.get {target}` y `agent.send_keys {target, keys: ["esc"]}`. La API es JSON por líneas sobre socket Unix, con `id`, `method`, `params` y respuesta `result` o `error`. El cliente implementado no necesita `agent.prompt`, parsing de stdout ni una API conceptual `herder ask`.

La extensión v1 consume exactamente:

```json
{"version": 1, "id": "fmr-<uuid>", "transcript": "<instrucción de voz y petición>", "requestedAt": 0}
```

`requestedAt` usa segundos Unix. El request se publica mediante fichero temporal, fsync y renombrado atómico. La extensión reclama con `.request.json → .claimed.json` y publica `{version, id, answer}` o `{version, id, error}`. El adaptador solo lee los resultados causales finales de esta extensión; no accede al transcript de Pi ni a la pantalla.

La respuesta del agente debe incluir un objeto JSON (solo o en el último bloque `json`):

```json
{
  "spoken_response": "Resultado breve para leer en voz alta.",
  "full_response": "Detalle final para el usuario.",
  "needs_input": false,
  "question": ""
}
```

`needs_input` debe ser booleano; si es true, `question` debe contener una pregunta de hasta 900 caracteres. `spoken_response` debe tener de 1 a 900 caracteres. Un formato inválido falla de forma explícita. El envoltorio pide trabajar autónomamente y excluir razonamiento, logs y salida de herramientas. El esquema y la selección causal son la frontera del canal; no existe un filtro semántico que pueda garantizar lo que un modelo escriba dentro de un campo válido.

## Componentes

| Módulo | Responsabilidad |
| --- | --- |
| `domain.py` | Estados, transiciones y validación de respuestas de voz |
| `schema.sql`, `repository.py` | Migración v1, jobs, turnos, eventos y outbox en SQLite |
| `manager.py` | Cola serial, entrega, observación y reconciliación |
| `herder/adapter.py` | Contrato de ficheros, identidad, claim y retirada atómica |
| `herder/herdr.py` | RPC asíncrono real con límite por intercambio |
| `worker.py` | Bucle independiente, señales y exclusión por home |
| `notifications/` | Interfaz Notifier, outbox y proveedor ntfy |
| `cli.py` | Clientes locales breves sobre SQLite |

La CLI confirma el commit sin esperar a Herdr. `BEGIN IMMEDIATE`, restricciones únicas e índices serializan escrituras y reintentos; estados y eventos se confirman juntos. La migración usa `PRAGMA user_version` y transacción, rechaza versiones desconocidas y fija la base a un home canónico. Un lock de sistema operativo por home impide workers simultáneos incluso si sus clientes eligieron bases distintas.

Los turnos conservan su resultado individual al responder a una pregunta. Los eventos distinguen explícitamente `channel=user` de `channel=internal`. El outbox consulta exclusivamente eventos de usuario y selecciona únicamente los campos de voz; ningún fallo de ntfy altera el estado del trabajo.

## Recuperación y cancelación

1. El turno y su ID quedan en SQLite antes de publicar el request. La identidad de la sesión se fija antes de entregar; todos los reintentos del cliente vuelven al job original.
2. Al reiniciar el worker, un turno con request/claim/resultado se observa por el mismo ID. Nunca se genera otro ID para recuperarlo. Los resultados disponibles se procesan incluso si Herdr está temporalmente inaccesible.
3. Si el proceso murió entre persistir la intención de entrega y publicar, y no quedan ficheros, la entrega es **incierta**: se marca `failed` sin reenviar. Es preferible una intervención manual a duplicar una acción. Lo mismo sucede si se perdieron o purgaron todos los ficheros de un turno entregado.
4. El timeout de claim retira el request mediante un rename que compite atómicamente con el claim de la extensión. Si ganó la extensión, sigue observando. Después del claim no hay límite de duración del job.
5. Una cancelación puede retirar un request sin tocar Herdr. Si ya está reclamado, comprueba identidad, registra durablemente la intención de Escape y utiliza `agent.send_keys`. No da por cancelado el turno ni libera la cola hasta obtener un resultado.
6. Escape no es una operación idempotente del contrato. Si el worker cae o se pierde la respuesta RPC después de registrar el intento, **no repite Escape** automáticamente. Queda pendiente hasta que la extensión publique un resultado. `cancel_sent=1` significa intento registrado, no confirmación del agente. Una nueva llamada CLI `cancel` no fuerza otro Escape; el operador debe reconciliar el primario.
7. Si la identidad cambia, el job falla y no se envía Escape a la nueva conversación. Una respuesta a una pregunta también exige la identidad anterior. Si el binding o transporte no está disponible, se conserva el turno mientras se recupera la salud.

El contrato de la extensión admite un solo turno en vuelo. El gateway respeta solicitudes/claims visibles de otros clientes, incluidos los del push-to-talk de escritorio. Una carrera entre clientes que no comparten nuestro lock sigue teniendo como árbitro a la extensión, que rechaza la segunda petición con un error explícito. No se sobrescriben ni eliminan turnos ajenos.

La extensión puede barrer ficheros de más de 24 horas. Un claim residual tras cambiar de sesión puede mantener la cola detenida: inspecciónalo con el primario antes de archivarlo manualmente, para evitar ignorar un turno aún activo. El worker no elimina claims de otros procesos ni adivina que están terminados. Tampoco elimina automáticamente los resultados; aplica tu política de retención y backups sobre información privada.

Estas restricciones se manejan sin ampliar el contrato. No se implementa ejecución exactamente una vez ante pérdida externa de todos los registros, ni cancelación fuerte de tareas delegadas: Escape interrumpe el turno del primario. Si se necesitara una garantía mayor, haría falta elevar el cambio del contrato de First Mate/Herdr.

## Siguiente fase

La elección ntfy está registrada y el proveedor mínimo funciona como consumidor desacoplado. Quedan fuera el Shortcut de iOS, HTTP/autenticación remota, TTS, APNs y observación de tareas delegadas.

`waiting_for_input` proviene únicamente de `needs_input=true` en la respuesta estructurada. Herdr solo informa estados operativos; `idle` y `blocked` no permiten deducir una pregunta. La correlación futura de decisiones/resultados delegados debe consultar los registros durables de First Mate (`home-summary.json`, holds, decisiones y estados de tareas), tal como recomienda el spike, sin convertir sus logs en voz.
