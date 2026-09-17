# PRD — Voice Remote para First Mate / Herder

**Versión:** 0.1  
**Estado:** MVP  
**Nota de implementación (Fase 2):** el contrato real y sus límites están en [docs/integration.md](integration.md); prevalecen sobre las APIs conceptuales de este documento. ntfy es el canal de notificaciones elegido.

**Plataforma cliente:** iPhone / iOS  
**Backend:** PC donde se ejecuta Herder  
**Agente principal:** `First Mate`

## 1. Objetivo

Construir una interfaz de voz extremadamente simple para poder comunicarse con el agente `First Mate` de Herder desde un iPhone mientras el usuario está andando, conduciendo tareas cotidianas o lejos del ordenador.

La interacción ideal debe ser:

**Pulsar → hablar → continuar con otra cosa → recibir respuesta por voz.**

El usuario no debe tener que interactuar con una terminal, leer logs ni mantener una sesión SSH abierta esperando a que Herder termine.

First Mate puede tardar desde segundos hasta un tiempo indeterminado y puede delegar trabajo a otros agentes. El sistema debe ser completamente asíncrono.

## 2. Caso de uso principal

El usuario lleva un auricular Bluetooth/AirPods conectado al iPhone.

Pulsa un botón físico o ejecuta un Shortcut.

El iPhone empieza a escuchar.

El usuario dice, por ejemplo:

> First Mate, revisa el proyecto y pide al agente de backend que implemente el endpoint que comentamos.

El audio se convierte a texto en el iPhone.

La petición se envía al ordenador.

El ordenador entrega el prompt a First Mate mediante Herder.

A partir de ese momento el usuario puede guardar el teléfono.

Herder puede ejecutar durante el tiempo que necesite.

No se debe enviar al iPhone el razonamiento interno, tool calls, logs, tokens intermedios, output de otros agentes ni verbose output del CLI.

Solo interesan determinados eventos semánticos:

| Evento | Comportamiento |
| --- | --- |
| `accepted` | Confirmación opcional: «Petición enviada» |
| `working` | No hacer nada |
| `needs_input` | Avisar al usuario por voz/notificación |
| `completed` | Leer la respuesta final |
| `failed` | Informar brevemente del error |
| `cancelled` | Informar de cancelación |

## 3. Principio fundamental

La ejecución de Herder y la conversación de voz deben estar desacopladas.

No implementar:

`iPhone -> SSH -> ejecutar Herder -> esperar 20 minutos -> devolver stdout`

Implementar:

```text
iPhone
   |
   | submit(prompt)
   v
Voice Gateway
   |
   | create job
   v
Job Manager
   |
   +----> Herder / First Mate
              |
              | trabajo arbitrariamente largo
              | otros agentes
              | herramientas
              v
         resultado/eventos
              |
              v
        Voice Gateway
              |
         push / polling
              v
            iPhone
              |
              v
          Text to Speech
```

Una petición debe convertirse inmediatamente en un `job`.

La vida de ese job no depende de que siga abierta una sesión SSH.

## 4. Alcance del MVP

Para la primera versión evitar desarrollar una aplicación iOS nativa salvo que sea necesario.

Utilizar:

```text
iPhone
→ iOS Shortcuts
→ Dictado
→ conexión segura con PC
→ servicio/wrapper de Herder
```

La primera versión debe poder iniciarse mediante:

- Shortcut desde pantalla.
- Siri.
- Action Button del iPhone, cuando esté disponible/configurado.
- Opcionalmente widget o Back Tap.

El audio de entrada utilizará el micrófono seleccionado por iOS, incluyendo AirPods.

La reproducción utilizará el dispositivo de audio activo de iOS.

## 5. Arquitectura propuesta

### 5.1 Componente iPhone

Crear un Shortcut denominado provisionalmente:

`First Mate`

Flujo:

```text
START
 ↓
Dictate Text
 ↓
¿Texto vacío?
 ├── Sí → END
 └── No
       ↓
Submit request
       ↓
Receive job_id
       ↓
Speak "Enviado"
       ↓
END
```

Este Shortcut NO espera a que termine First Mate.

La petición debe tardar idealmente menos de dos segundos en quedar aceptada por el PC.

## 6. Voice Gateway

Crear en el PC un pequeño servicio independiente de Herder.

Nombre provisional:

```text
firstmate-voice
```

Responsabilidades:

```text
Receive prompt
Generate job_id
Persist request
Launch Herder task
Monitor task
Extract semantic result
Persist state/result
Notify client
Expose job status
Handle follow-up input
```

No debe contener lógica específica del proyecto en el que esté trabajando First Mate.

## 7. Modelo de Job

Cada petición tendrá como mínimo:

```json
{
  "job_id": "uuid",
  "created_at": "ISO-8601",
  "status": "queued",
  "source": "iphone_voice",
  "agent": "first_mate",
  "prompt": "texto dictado",
  "session_id": null,
  "final_response": null,
  "input_request": null,
  "error": null
}
```

Estados válidos:

```text
queued
running
waiting_for_input
completed
failed
cancelled
```

Transiciones principales:

```text
queued
  ↓
running
  ├───────────────→ completed
  ├───────────────→ failed
  ├───────────────→ cancelled
  ↓
waiting_for_input
  ↓
running
```

Persistir los jobs para que sobrevivan a la desconexión del iPhone y, preferiblemente, al reinicio del servicio.

Para el MVP SQLite es suficiente.

## 8. Contrato con First Mate

Este punto es crítico.

El sistema NO debe intentar convertir todo el stdout de Herder en voz.

Debe existir una separación explícita entre:

```text
execution output
```

y:

```text
user-facing output
```

La integración con First Mate debe proporcionar al menos dos mecanismos semánticos.

### Resultado final

Cuando First Mate haya finalizado, debe existir un resultado equivalente a:

```json
{
  "type": "completed",
  "spoken_response": "He terminado. El endpoint está implementado y los tests pasan.",
  "full_response": "Respuesta más detallada opcional..."
}
```

`spoken_response` está optimizado para Text-to-Speech.

`full_response` puede contener la respuesta completa para consultarla posteriormente.

### Solicitud de intervención

Cuando First Mate no pueda continuar sin el usuario:

```json
{
  "type": "needs_input",
  "question": "Necesito saber si quieres mantener compatibilidad con la API antigua."
}
```

El sistema debe notificarlo inmediatamente.

## 9. Contrato de comportamiento para First Mate

Añadir a las instrucciones de sistema/contexto de First Mate una regla equivalente a:

```text
When processing requests originating from the voice interface:

Continue working autonomously whenever possible.

Do not expose chain-of-thought, internal reasoning, tool logs,
agent-to-agent communication or intermediate execution output
to the voice interface.

If user intervention is strictly required, emit a structured
needs_input event containing a concise question.

When the task finishes, emit a structured completed event.

The spoken_response field should normally be concise and suitable
for text-to-speech. State what was accomplished, important caveats,
and whether further user action is required.

Detailed technical information may be included separately in
full_response.
```

No depender únicamente de detectar frases en stdout si Herder ofrece una API/event system más fiable.

Prioridad de integración:

```text
Herder structured events/API
        ↓
Herder hooks/plugins
        ↓
machine-readable CLI output
        ↓
wrapper around CLI
        ↓
stdout parsing (último recurso)
```

## 10. Ejecución de Herder

Crear un adapter:

```text
HerderAdapter
```

El resto del sistema no debe conocer cómo se ejecuta Herder.

Interfaz conceptual:

```python
class HerderAdapter:
    async def submit(prompt, session_id=None) -> RunHandle:
        ...

    async def events(run_handle):
        ...

    async def send_input(run_handle, text):
        ...

    async def cancel(run_handle):
        ...
```

Esto permitirá sustituir posteriormente SSH/CLI por API sin modificar el resto del sistema.

## 11. Conversaciones y contexto

Una petición de voz no tiene por qué ser una conversación nueva.

Debe existir el concepto:

```text
voice_session
```

Ejemplo:

```text
Usuario:
"First Mate, revisa por qué fallan los tests."

First Mate:
"Hay dos posibles soluciones. ¿Quieres mantener compatibilidad?"

Usuario:
"Sí, mantenla."

First Mate:
"Entendido."
```

La segunda respuesta debe enviarse al mismo run/session, no crear una tarea independiente.

Asociación:

```text
voice_session_id
       ↓
herder_session_id
       ↓
job/run
```

## 12. `needs_input`

Cuando First Mate necesite una decisión:

```text
First Mate
   ↓
needs_input
   ↓
PC
   ↓
iPhone notification
   ↓
"First Mate necesita tu atención:
¿mantengo compatibilidad con la API anterior?"
```

El usuario debe poder ejecutar el Shortcut y responder.

Idealmente el Shortcut podrá distinguir entre:

```text
new request
```

y:

```text
reply to pending question
```

Si existe exactamente una pregunta pendiente, interpretar el siguiente dictado como respuesta a esa pregunta.

Si existen varias tareas esperando input, pedir al usuario que seleccione una.

## 13. Output por voz

Nunca leer automáticamente respuestas extremadamente largas.

Generar dos versiones:

```text
spoken_response
full_response
```

Objetivo orientativo de `spoken_response`:

```text
20–60 segundos de audio máximo
```

Ejemplo:

> He terminado. El agente de backend ha añadido el endpoint y he corregido dos tests relacionados. Todos los tests pasan. Hay un cambio de esquema pendiente de aplicar en producción. Si quieres, puedo preparar también la migración.

La respuesta detallada queda almacenada.

## 14. Notificaciones

El diseño debe abstraer el canal de notificación.

Interfaz conceptual:

```python
Notifier.notify(
    event_type,
    job_id,
    title,
    message
)
```

Implementaciones posibles:

```text
iOS notification
Pushcut
Pushover
ntfy
APNs mediante aplicación propia
otro mecanismo
```

No acoplar Job Manager a un proveedor concreto.

Para el MVP seleccionar el mecanismo que requiera menos infraestructura.

## 15. Text-to-Speech

En primera versión, priorizar TTS del propio iPhone.

Cuando llegue una respuesta final, el sistema debe facilitar que iOS ejecute:

```text
Speak Text(spoken_response)
```

y utilice automáticamente los AirPods/auriculares conectados.

No sintetizar audio en el servidor salvo que posteriormente haya un motivo claro para hacerlo.

## 16. Seguridad

No exponer Herder directamente a Internet.

Preferencias de conectividad, por orden:

```text
Tailscale/WireGuard
        ↓
SSH
        ↓
HTTPS autenticado
```

Nunca:

```text
Herder CLI directamente expuesto públicamente
```

El servicio debe validar todas las entradas.

Si se utiliza HTTP:

```text
HTTPS
authentication token
rate limiting básico
request size limit
no shell interpolation
```

El prompt nunca debe concatenarse directamente en una shell command.

Incorrecto:

```python
os.system("herder ask " + prompt)
```

Correcto:

```python
subprocess.run(
    ["herder", "ask", "--agent", "first-mate", prompt],
    ...
)
```

o, preferiblemente, usar la API nativa de Herder.

## 17. Logging

Mantener dos canales completamente separados.

### Internal log

Puede contener:

```text
process lifecycle
timestamps
Herder events
errors
agent IDs
tool activity
debugging information
```

### User output

Solo:

```text
accepted
needs_input
completed
failed
cancelled
```

Nunca enviar automáticamente los logs internos al TTS.

## 18. Timeouts

No utilizar un timeout corto para la ejecución del agente.

Un job puede durar:

```text
10 segundos
10 minutos
2 horas
etc.
```

El sistema debe soportarlo.

Sí establecer timeouts para operaciones de transporte individuales, por ejemplo:

```text
HTTP request: pocos segundos
SSH submission: pocos segundos
```

pero no para la vida total del job.

## 19. Recuperación ante errores

Si el iPhone pierde cobertura después de mandar una orden, la tarea debe continuar.

Si se cierra el Shortcut, la tarea debe continuar.

Si Termius se cierra, la tarea debe continuar.

Si el usuario bloquea el iPhone, la tarea debe continuar.

Si los AirPods se desconectan, la respuesta debe seguir disponible como texto.

Si el proceso de Herder falla:

```json
{
  "type": "failed",
  "spoken_response": "La tarea ha fallado antes de terminar.",
  "error": "..."
}
```

No leer traces completos por voz.

## 20. CLI administrativa

Crear además una pequeña CLI local para depuración.

Ejemplo:

```bash
fmvoice submit "revisa los tests"

fmvoice jobs

fmvoice status <job-id>

fmvoice show <job-id>

fmvoice reply <job-id> "sí, mantenla"

fmvoice cancel <job-id>
```

Esto permitirá probar toda la arquitectura sin depender inicialmente del iPhone.

## 21. API conceptual

Aunque el MVP utilice SSH, diseñar internamente una API equivalente a:

```text
POST /jobs
GET  /jobs/{id}
POST /jobs/{id}/reply
POST /jobs/{id}/cancel
GET  /jobs/pending-input
```

Ejemplo:

```http
POST /jobs
```

```json
{
  "prompt": "Revisa si los tests del backend pasan.",
  "agent": "first_mate",
  "source": "iphone_voice"
}
```

Respuesta inmediata:

```json
{
  "job_id": "01abc...",
  "status": "queued"
}
```

No esperar a Herder.

## 22. Requisito importante: idempotencia

Una mala conexión móvil podría provocar que el Shortcut repita una petición.

Cada solicitud enviada desde el iPhone debe incluir:

```text
request_id
```

Si llega dos veces el mismo `request_id`, no ejecutar dos veces la tarea.

Ejemplo:

```json
{
  "request_id": "iphone-generated-uuid",
  "prompt": "..."
}
```

## 23. MVP funcional

Considerar la primera versión terminada cuando pueda realizarse de extremo a extremo esta prueba:

```text
1. PC tiene Herder abierto/disponible.

2. Usuario bloquea la pantalla del iPhone.

3. Usuario pulsa Action Button.

4. Dicta:
   "First Mate, comprueba los tests del proyecto."

5. iPhone confirma:
   "Enviado."

6. El usuario guarda el teléfono.

7. First Mate trabaja durante el tiempo necesario.

8. No se mantiene ninguna sesión interactiva abierta
   en el iPhone.

9. First Mate termina.

10. El usuario recibe una notificación.

11. El resultado conciso puede escucharse por los AirPods.

12. La respuesta completa queda almacenada.

13. Si First Mate requiere información en mitad del proceso,
    el usuario recibe una pregunta y puede responder por voz.

14. First Mate continúa la misma tarea después de recibirla.
```

## 24. Criterios de aceptación

| Requisito | Criterio |
| --- | --- |
| Dictado | Se puede crear una petición sin escribir |
| Envío | El usuario recibe confirmación rápidamente |
| Asincronía | Cerrar el cliente no cancela el trabajo |
| Duración | Una tarea larga sigue funcionando |
| First Mate | Todas las peticiones llegan al agente correcto |
| Delegación | First Mate puede utilizar sus agentes normalmente |
| Verbose output | Nunca se reproduce automáticamente |
| Chain-of-thought | Nunca se reproduce ni se expone |
| Blocking | First Mate puede solicitar input |
| Follow-up | El usuario puede responder por voz |
| Final | Se genera `spoken_response` |
| Audio | iOS puede reproducirlo por el dispositivo activo |
| Persistencia | Puede recuperarse una respuesta posteriormente |
| Duplicados | Un reintento no duplica una tarea |
| Seguridad | Herder no queda públicamente expuesto |

## 25. Fases de implementación

### Fase 1 — Spike de integración Herder

Investigar exactamente cómo lanzar una petición a First Mate de forma programática y determinar cómo detectar:

```text
started
completed
needs_input
failed
```

No desarrollar todavía iOS.

Producir un pequeño script:

```bash
./test_firstmate.py "haz X"
```

que permita recibir un resultado estructurado.

### Fase 2 — Job Manager

Implementar:

```text
SQLite
job lifecycle
HerderAdapter
background execution
CLI
```

Demostrar que un proceso cliente puede enviar una tarea, terminar y consultar el resultado posteriormente.

### Fase 3 — iPhone Shortcut

Implementar:

```text
Dictate Text
Submit
confirmation
```

Validar funcionamiento usando AirPods.

### Fase 4 — Completion notifications

Añadir:

```text
completed
failed
```

y reproducción de `spoken_response`.

### Fase 5 — Interactive blocking

Añadir:

```text
needs_input
reply
resume
```

### Fase 6 — UX avanzada

Posteriormente estudiar:

```text
app iOS nativa
push mediante APNs
Live Activities
Apple Watch
botón dedicado
streaming
historial
varios proyectos
varios agentes
```

## 26. Estructura de proyecto sugerida

```text
firstmate-voice/
│
├── README.md
├── pyproject.toml
├── config.example.yaml
│
├── firstmate_voice/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   │
│   ├── jobs/
│   │   ├── manager.py
│   │   ├── models.py
│   │   └── repository.py
│   │
│   ├── herder/
│   │   ├── adapter.py
│   │   └── events.py
│   │
│   ├── notifications/
│   │   ├── base.py
│   │   └── ...
│   │
│   ├── api/
│   │   └── ...
│   │
│   └── db/
│       └── ...
│
└── tests/
    ├── test_jobs.py
    ├── test_herder_adapter.py
    └── test_idempotency.py
```

Python es una elección razonable para el gateway si no existe una restricción tecnológica previa. Si el ecosistema de Herder está implementado en otro lenguaje, priorizar ese lenguaje para reducir integración innecesaria.

## 27. Restricciones de implementación para los agentes

Los agentes de código deben seguir estas reglas:

1. **Investigar primero la interfaz real de Herder.** No inventar comandos o APIs.
2. Mantener `HerderAdapter` desacoplado del Job Manager.
3. No interpretar chain-of-thought ni intentar extraerlo.
4. No utilizar stdout completo como respuesta de voz.
5. Toda tarea debe tener `job_id`.
6. Toda petición del cliente debe tener `request_id`.
7. Las tareas deben sobrevivir a la desconexión del cliente.
8. El resultado completo y el resultado hablado deben almacenarse separadamente.
9. Implementar primero una CLI para probar el backend antes del Shortcut de iOS.
10. Añadir tests al menos para estado de jobs, idempotencia, `needs_input`, finalización, error y cancelación.
11. No hacer cambios en Herder core salvo que sean estrictamente necesarios. Preferir adapter/plugin/hook.
12. Documentar cómo arrancar, parar, configurar y depurar el servicio.

## 28. Dirección futura

El MVP debe diseñarse pensando en que posteriormente la experiencia pueda convertirse en:

```text
AirPods
   ↓
iPhone / Apple Watch
   ↓
"First Mate..."
   ↓
agente trabajando en segundo plano
   ↓
"Ya está. He hecho X, Y y Z."
```

El objetivo final no es «usar Herder desde una terminal móvil».

El objetivo final es convertir **First Mate en un asistente remoto de voz**, mientras Herder y los demás agentes continúan funcionando como infraestructura de ejecución detrás de él.
