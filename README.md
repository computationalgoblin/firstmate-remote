# Firstmate Remote

Firstmate Remote es una interfaz de voz asíncrona para comunicarse con **First Mate** desde un iPhone sin mantener abierta una terminal ni esperar a que termine el trabajo.

El MVP utilizará iOS Shortcuts para dictar una petición y enviarla de forma segura al PC. Un gateway persistirá la solicitud como un trabajo independiente, la entregará a First Mate mediante un adaptador desacoplado de Herder y notificará al iPhone únicamente los resultados relevantes: aceptación, petición de información, finalización, error o cancelación.

## Principios del proyecto

- Pulsar, hablar y guardar el teléfono.
- Ejecución completamente asíncrona y persistente.
- Resultados concisos preparados para voz, separados de logs y detalles técnicos.
- Continuación de una misma conversación cuando First Mate necesita información.
- Idempotencia mediante `request_id` para evitar trabajos duplicados.
- Herder nunca se expone directamente a Internet.
- CLI administrativa antes de desarrollar una aplicación iOS nativa.
- Integración con Herder aislada detrás de `HerderAdapter`.

## Arquitectura inicial

```text
iPhone / iOS Shortcuts
        ↓
Voice Gateway + Job Manager
        ↓
HerderAdapter → First Mate
        ↓
Eventos semánticos y resultado persistido
        ↓
Notificación + Text-to-Speech en iOS
```

## Estado

El proyecto está en fase de definición del MVP. La primera tarea será investigar la interfaz real de Herder y construir un pequeño spike que envíe una petición a First Mate y produzca eventos estructurados.

Consulta el [PRD completo](docs/PRD.md) para conocer el alcance, la arquitectura propuesta, las fases y los criterios de aceptación.
