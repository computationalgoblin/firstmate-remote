# Atajos de iOS de First Mate Remote, paso a paso

Manual para reconstruir **manualmente y desde cero** en Atajos de iOS el cliente de First Mate Remote. No presupone ningún archivo `.shortcut`.

> **Estado de la evidencia.** El recorrido de **«Leer First Mate»** —GET autenticado, locución, guardado de `voice-cursor.json` y segunda lectura sin repeticiones— está probado físicamente en el iPhone. También está probado que una petición puede llegar y producir una notificación ntfy. La pareja completa de **«First Mate Responder»** y **«First Mate Enviar Pendiente»** está contrastada con el contrato HTTP, pero no tiene una validación física limpia de extremo a extremo. Por eso este manual exige tipos explícitos y comprobación visual; donde la evidencia no fija cómo representa iOS un booleano, se indica exactamente qué observar.

## 1. Inventario y orden recomendado

Los **seis** atajos conocidos, con sus nombres exactos, son:

1. **First Mate Config** — configuración privada.
2. **First Mate UUID** — identificadores idempotentes.
3. **First Mate Enviar Pendiente** — POST común y confirmación del borrador.
4. **First Mate** — dicta y crea una petición.
5. **Leer First Mate** — consulta y pronuncia preguntas/resultados.
6. **First Mate Responder** — consulta preguntas pendientes, crea una respuesta y llama al envío común.

Constrúyelos en ese orden. No hace falta un séptimo atajo de notificaciones: **ntfy solo avisa**; no confirma escucha ni avanza el cursor. El lanzador con menú mencionado en otras recetas es opcional y no forma parte del inventario probado.

## 2. Requisitos previos y convenciones

### 2.1 Preparación

- iPhone conectado a la misma tailnet que el equipo donde está First Mate Remote.
- URL HTTPS privada de Tailscale Serve ya operativa y sin `/` final.
- Token Bearer del gateway de 32–256 caracteres `A–Z`, `a–z`, `0–9`, `_` o `-`.
- Aplicación ntfy configurada con el servidor, credencial de **lectura** y tema privados. El token del gateway y el de ntfy son secretos distintos.
- En Archivos, crea **En mi iPhone/FirstMate**. Usa esa ubicación local en todas las acciones; no iCloud, para no compartir cursores o borradores entre dispositivos.
- Activa Tailscale y concede a Atajos permisos de micrófono, dictado, red, archivos y voz cuando iOS los solicite.

Rutas utilizadas:

| Ruta local | Contenido |
| --- | --- |
| `En mi iPhone/FirstMate/pending.json` | Una petición o respuesta pendiente y, después de confirmarla, su recibo |
| `En mi iPhone/FirstMate/voice-cursor.json` | Último evento cuya locución terminó y cuyo guardado fue verificado |

No ejecutes simultáneamente dos atajos que escriban `pending.json`, ni dos lectores.

### 2.2 Cómo introducir los secretos sin ponerlos aquí

En el equipo servidor, abre **localmente** el fichero privado que configure `FMVOICE_API_TOKEN` (normalmente `~/.config/fmvoice/gateway.env`) con una aplicación que no sincronice ni comparta su contenido. Copia solo el valor situado después de `FMVOICE_API_TOKEN=` y pégalo directamente en **First Mate Config**. No lo pegues en este documento, chat, notas, capturas, portapapeles universal ni informes. Obtén la URL exacta mirando localmente la salida/configuración vigente de Tailscale Serve; tampoco la escribas en este manual.

Usa estos marcadores al construir:

- `<BASE_URL_HTTPS_PRIVADA>`: URL exacta de Serve, sin slash final, query ni fragmento.
- `<TOKEN_GATEWAY_PRIVADO>`: token, sin el prefijo `Bearer `.

### 2.3 Convenciones de Atajos

- Los nombres de acciones pueden variar ligeramente con la versión de iOS. Entre paréntesis se da a veces el nombre inglés.
- Una **variable mágica** es la salida de una acción. En cada receta se indica la acción productora. Una ficha de variable no es texto escrito a mano.
- En todas las condiciones, toca la variable izquierda y fija el **tipo indicado** antes de elegir el operador. Tras cerrar el editor, vuelve a abrir cada `Si` y comprueba que conserva izquierda, tipo, operador y, cuando corresponda, operando derecho.
- `no tiene valor` y `tiene valor` **no llevan operando derecho**.
- **Detener este atajo** es una cancelación local segura: termina sin POST cuando todavía no se ha guardado una operación, o conserva el borrador cuando ya existe.

## 3. «First Mate Config»

### Variables

| Variable mágica | Tipo | La produce |
| --- | --- | --- |
| `Diccionario` | Diccionario | Acción 1 |

### Acciones, en orden

1. **Diccionario** con dos pares:
   - `base_url`: tipo **Texto**, valor `<BASE_URL_HTTPS_PRIVADA>`.
   - `token`: tipo **Texto**, valor `<TOKEN_GATEWAY_PRIVADO>`.
2. **Detener y generar salida** con la variable mágica `Diccionario` de la acción 1.

No añadas Vista rápida, Copiar al portapapeles, Mostrar resultado, Leer texto ni registro.

### Comprobación manual no destructiva

Abre el editor, sin ejecutar, y confirma que hay exactamente dos claves, ambas de tipo **Texto**, que la URL no acaba en `/` y que el token no empieza por `Bearer `. Cierra el editor. No muestres la salida.

## 4. «First Mate UUID»

Genera UUID v4 con acciones integradas. Sirve para idempotencia, no para crear secretos.

### Variables

| Variable | Tipo | La produce |
| --- | --- | --- |
| `Hex` | Lista de Texto | Dividir texto, acción 2 |
| `Índice de repetición` | Número | Repetir, acción 3 |
| `Número aleatorio` | Número | Acciones 10 o 13 |
| `Elemento de la lista` | Texto | Acciones 11 o 14 |
| `Resultados de repetición` | Lista de Texto | Fin de Repetir |
| `Texto combinado` | Texto | Acción 14 |
| `Texto reemplazado` | Texto | Acción 15 |

### Acciones, en orden

1. **Texto**: `0123456789abcdef`.
2. **Dividir texto**, entrada = variable mágica `Texto` de la acción 1, separador **Cada carácter**; renombra su salida `Hex` (**Lista** de 16 textos).
3. **Repetir** 32 veces.
4. Dentro, **Si** `Índice de repetición` (**Número**) **es** `13` (**Número**).
5. Rama verdadera: **Texto** `4`.
6. Rama `Si no`: **Si** `Índice de repetición` (**Número**) **es** `17` (**Número**).
7. Rama verdadera de este segundo `Si`: **Número aleatorio** entre `9` y `12`.
8. **Obtener elemento de la lista** `Hex`, índice = variable mágica `Número aleatorio` de la acción 7.
9. Rama `Si no` del segundo `Si`: **Número aleatorio** entre `1` y `16`.
10. **Obtener elemento de la lista** `Hex`, índice = variable mágica `Número aleatorio` de la acción 9.
11. Cierra el segundo **Fin de Si**. Su salida por iteración debe ser el `Texto 4` o el `Elemento de la lista` elegido.
12. Cierra el primer **Fin de Si**.
13. Cierra **Fin de Repetir**.
14. **Combinar texto**, entrada `Resultados de repetición`, separador **Personalizado** vacío.
15. **Reemplazar texto** sobre la salida anterior, expresión regular activada, buscar `^(.{8})(.{4})(.{4})(.{4})(.{12})$`, reemplazar por `$1-$2-$3-$4-$5`.
16. **Detener y generar salida** con `Texto reemplazado` (**Texto**).

### Condiciones

| Izquierda | Tipo | Operador | Derecha |
| --- | --- | --- | --- |
| `Índice de repetición` | Número | es | Número `13` |
| `Índice de repetición` | Número | es | Número `17` |

### Comprobación manual no destructiva

Esta es la única comprobación que puede ejecutarse sin red ni ficheros: ejecuta dos veces y verifica visualmente, sin compartir el resultado, que ambos textos son distintos y cumplen `xxxxxxxx-xxxx-4xxx-[89ab]xxx-xxxxxxxxxxxx`. Elimina cualquier Vista rápida temporal al terminar.

## 5. Formatos durables

### 5.1 Petición nueva en `pending.json`

```json
{
  "kind": "request",
  "request_id": "UUID-generado-localmente",
  "prompt": "texto dictado",
  "acknowledged": false
}
```

Tipos: `kind`, `request_id` y `prompt` son **Texto**; `acknowledged` es **Booleano**.

### 5.2 Respuesta en `pending.json`

```json
{
  "kind": "reply",
  "request_id": "UUID-nuevo-para-la-respuesta",
  "prompt": "respuesta dictada",
  "job_id": "UUID-del-trabajo-seleccionado",
  "input_revision": 1,
  "acknowledged": false
}
```

`job_id` es **Texto** UUID; `input_revision` es **Número** entero positivo. `request_id` admite por contrato `[A-Za-z0-9_-]{1,200}`; este conjunto de atajos usa un UUID v4, pero **no** debes imponer que todo `request_id` sea UUID al leer un borrador existente.

Tras confirmación se conservan las mismas claves, se cambia `acknowledged` a **Booleano** `true` y se añade `receipt` de tipo **Diccionario**.

### 5.3 Cursor en `voice-cursor.json`

```json
{"base_url":"https://servidor-privado-ejemplo","after":0}
```

`base_url` es **Texto** y `after` es **Número** entero entre `0` y `9007199254740991`. No contiene token, voz, `has_more` ni pregunta.

## 6. «First Mate Enviar Pendiente»

Este auxiliar es el único que hace POST. Conserva siempre el mismo `request_id` y cuerpo al reintentar.

### Variables

| Variable | Tipo | Origen |
| --- | --- | --- |
| `ArchivoPendiente` | Archivo | Obtener archivo |
| `Borrador` | Diccionario | JSON de `ArchivoPendiente` |
| `Confirmado`, `Aceptado` | Booleano | `acknowledged`, `accepted` |
| `Kind`, `RequestID`, `Prompt`, `JobID` | Texto | campos del borrador |
| `Revision` | Número | `input_revision` |
| `Ruta`, `BaseURL`, `Token`, `Authorization` | Texto | ramas/configuración |
| `Config`, `Cuerpo`, `Recibo` | Diccionario | acciones Diccionario/respuesta |
| `Endpoint` | URL | acción URL |
| `ReceiptID`, `VoiceSessionID`, `Estado`, `ErrorPublico` | Texto | recibo |
| `EstadosValidos` | Lista | acción Lista |

### Acciones, en orden

1. **Obtener archivo de carpeta**: carpeta fija `En mi iPhone/FirstMate`, ruta literal `pending.json`; error si falta activado.
2. **Definir variable** `ArchivoPendiente` (**Archivo**) con la salida de 1.
3. **Obtener diccionario de la entrada** desde `ArchivoPendiente`.
4. **Definir variable** `Borrador` (**Diccionario**) con la salida de 3.
5. **Obtener valor del diccionario** `acknowledged` en `Borrador` → `Confirmado` (**Booleano**).
6. **Si** `Confirmado` (**Booleano**) **es verdadero**; dentro, **Detener este atajo**; **Fin de Si**.
7. Obtener `kind` de `Borrador`; **Definir variable** `Kind` (**Texto**).
8. Obtener `request_id`; **Definir variable** `RequestID` (**Texto**).
9. Obtener `prompt`; **Definir variable** `Prompt` (**Texto**).
10. **Coincidir texto** en `RequestID` con `^[A-Za-z0-9_-]{1,200}$`.
11. **Contar** coincidencias → `CoincidenciasRequestID` (**Número**).
12. **Si** `CoincidenciasRequestID` (**Número**) **no es** `1` (**Número**): **Mostrar aviso** `Borrador inválido`; **Detener este atajo**; **Fin de Si**.
13. **Si** `Prompt` (**Texto**) **no tiene valor**: mismo aviso y detener; **Fin de Si**.
14. **Si** `Kind` (**Texto**) **es** `reply` (**Texto literal**).
15. En esa rama, obtener `job_id` de `Borrador` → `JobID` (**Texto**).
16. Obtener `input_revision` → `Revision` (**Número**).
17. **Coincidir texto** en `JobID` con `^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$`.
18. **Contar** coincidencias → `CoincidenciasJobID` (**Número**).
19. **Si** `CoincidenciasJobID` (**Número**) **no es** `1`: aviso `Borrador inválido`, detener; **Fin de Si**.
20. **Redondear número** `Revision` a unidades → `RevisionRedondeada` (**Número**).
21. **Si** `Revision` (**Número**) **es menor que** `1`: aviso y detener; **Fin de Si**.
22. **Si** `Revision` (**Número**) **no es** `RevisionRedondeada` (**Número**): aviso y detener; **Fin de Si**.
23. **Texto** formado por literal `/jobs/`, ficha `JobID`, literal `/reply`.
24. **Definir variable** `Ruta` (**Texto**) con la salida de 23.
25. Rama **Si no** de 14: **Si** `Kind` (**Texto**) **es** `request` (**Texto literal**).
26. Rama verdadera: **Texto** `/jobs`; definir `Ruta` (**Texto**).
27. Rama `Si no`: **Mostrar aviso** `Borrador inválido`; **Detener este atajo**.
28. Cierra ambos **Fin de Si**.
29. **Ejecutar atajo** `First Mate Config`; definir `Config` (**Diccionario**).
30. Obtener `base_url` de `Config` → `BaseURL` (**Texto**).
31. Obtener `token` de `Config` → `Token` (**Texto**).
32. **Si** `BaseURL` (**Texto**) **no tiene valor**: mostrar `Revisa la configuración privada de First Mate`, detener; **Fin de Si**.
33. **Si** `Token` (**Texto**) **no tiene valor**: mismo mensaje, detener; **Fin de Si**.
34. **Texto**: ficha `BaseURL` seguida inmediatamente de ficha `Ruta`; definir `TextoEndpoint` (**Texto**).
35. **URL** desde `TextoEndpoint`; definir `Endpoint` (**URL**).
36. **Texto**: literal `Bearer `, con espacio final, seguido de ficha `Token`.
37. **Definir variable** `Authorization` (**Texto**) usando **la variable mágica Texto de la acción 36**, no `Token`.
38. **Si** `Kind` (**Texto**) **es** `reply`.
39. Rama reply: **Obtener contenido de URL** `Endpoint`: método **POST**, cabeceras `Authorization` = variable `Authorization`, `Content-Type` = `application/json`; cuerpo **JSON** con `request_id` (**Texto**, `RequestID`), `prompt` (**Texto**, `Prompt`) e `input_revision` (**Número**, `Revision`).
40. Rama `Si no` (request): otra acción **Obtener contenido de URL** con el mismo método/cabeceras y cuerpo JSON con solo `request_id` (**Texto**) y `prompt` (**Texto**). No envíes campos vacíos.
41. Cierra **Fin de Si**. La variable mágica resultante es la respuesta de la rama ejecutada.
42. **Obtener diccionario de la entrada** desde esa respuesta → `Recibo` (**Diccionario**).
43. Extrae `error` → `ErrorPublico` (**Texto o sin valor**).
44. **Si** `ErrorPublico` (**Texto**) **tiene valor**: **Mostrar aviso** `No se confirmó el envío; conserva el borrador y reintenta`; detener; **Fin de Si**.
45. Extrae `accepted` → `Aceptado` (**Booleano**).
46. **Si** `Aceptado` (**Booleano**) **es verdadero**: deja la rama verdadera vacía; en **Si no**, muestra el aviso anterior y detén; **Fin de Si**. Esta forma evita depender del operador “no es verdadero”.
47. Extrae `id` → `ReceiptID` (**Texto**).
48. **Coincidir texto** en `ReceiptID` con el patrón UUID de la acción 17; contar → `CoincidenciasReceiptID` (**Número**).
49. **Si** `CoincidenciasReceiptID` (**Número**) **no es** `1`: aviso y detener; **Fin de Si**.
50. Extrae `voice_session_id` → `VoiceSessionID` (**Texto**).
51. **Si** `VoiceSessionID` (**Texto**) **no tiene valor**: aviso y detener; **Fin de Si**.
52. Extrae `state` → `Estado` (**Texto**).
53. **Lista** `queued`, `running`, `waiting_for_input`, `completed`, `failed`, `cancelled` → `EstadosValidos` (**Lista**).
54. **Si** `EstadosValidos` (**Lista**) **contiene** `Estado` (**Texto**): deja la rama verdadera vacía; en **Si no**, aviso y detener; **Fin de Si**.
55. **Si** `Kind` (**Texto**) **es** `reply`.
56. Dentro, **Si** `ReceiptID` (**Texto**) **no es** `JobID` (**Texto**): aviso y detener; **Fin de Si**.
57. Cierra **Fin de Si** exterior.
58. **Establecer valor del diccionario** en `Borrador`: clave `acknowledged`, valor **Booleano verdadero**; vuelve a definir `Borrador` con el diccionario resultante.
59. **Establecer valor del diccionario** en `Borrador`: clave `receipt`, valor `Recibo` (**Diccionario**); vuelve a definir `Borrador`.
60. **Obtener texto de la entrada** desde `Borrador` → JSON (**Texto**).
61. **Definir nombre** `pending.json` sobre ese texto.
62. **Guardar archivo** en carpeta fija `En mi iPhone/FirstMate`, preguntar ubicación desactivado, sobrescribir activado.
63. **Leer texto** literal `Enviado`.
64. **Detener este atajo**.

### Condiciones

Todas las condiciones están descritas en los pasos anteriores. Revisa especialmente `Kind Texto es reply`, `Kind Texto es request`, `Aceptado Booleano es verdadero` y `ReceiptID Texto no es JobID Texto`. Ninguna debe aparecer como “tiene valor”.

### Errores y cancelación segura

- Si la red/HTTP detiene Atajos, no marques el borrador ni digas «Enviado»; reintenta más tarde con el mismo archivo.
- Un `409` de reply puede significar revisión obsoleta. **No** cambies la revisión ni apliques el texto a otra pregunta. Conserva el archivo hasta decidir archivarlo fuera de `pending.json`.
- No hay evidencia de un atajo iOS de cancelación en el inventario. El contrato ofrece `POST /jobs/{id}/cancel` con cuerpo `{}`, pero construirlo sin una selección inequívoca podría cancelar el trabajo equivocado. Para este manual, cancelación segura significa **Detener este atajo** antes de enviar y conservar un borrador incierto. No inventes un atajo de cancelación.

### Comprobación manual no destructiva

Sin ejecutar, recorre el editor y confirma: dos POST separados; reply contiene tres campos y request dos; `Authorization` nace del **Texto** `Bearer ` + `Token`; `Enviado` está después de validar y guardar; ninguna URL procede del dictado; ninguna rama de error borra `pending.json`.

## 7. «First Mate»

### Variables

| Variable | Tipo | Origen |
| --- | --- | --- |
| `ArchivoPendiente` | Archivo o sin valor | lectura de `pending.json` |
| `Borrador`, `NuevoBorrador` | Diccionario | JSON/acción Diccionario |
| `Confirmado` | Booleano | `acknowledged` |
| `RequestID` | Texto | First Mate UUID |
| `Dictado`, `Prompt` | Texto | Dictar/Reemplazar texto |

### Acciones, en orden

1. **Obtener archivo de carpeta** `En mi iPhone/FirstMate/pending.json`, error si falta desactivado → `ArchivoPendiente` (**Archivo o sin valor**).
2. **Si** `ArchivoPendiente` (**Archivo**) **tiene valor**.
3. Dentro: **Obtener diccionario de la entrada** → `Borrador` (**Diccionario**).
4. Obtener `acknowledged` → `Confirmado` (**Booleano**).
5. **Si** `Confirmado` (**Booleano**) **es verdadero**: deja esta rama sin menú.
6. Rama **Si no**: **Elegir del menú** con `Reintentar pendiente` y `Salir`.
7. `Reintentar pendiente`: **Ejecutar atajo** `First Mate Enviar Pendiente`; **Detener este atajo**.
8. `Salir`: **Detener este atajo**.
9. Cierra menú y ambos **Fin de Si**. Un JSON inválido debe producir el error nativo, no tratarse como ausencia.
10. **Ejecutar atajo** `First Mate UUID` una sola vez → definir `RequestID` (**Texto**).
11. **Dictar texto**, idioma español, finalizar **Al tocar** → `Dictado` (**Texto**). No uses “al dejar de hablar”: la configuración fijada para este recorrido es “Al tocar”.
12. **Reemplazar texto** sobre `Dictado`, expresión regular activada, buscar `^\s+|\s+$`, reemplazo vacío → `Prompt` (**Texto**).
13. **Si** `Prompt` (**Texto**) **no tiene valor**: **Detener este atajo**; **Fin de Si**.
14. **Diccionario** → `NuevoBorrador`:
    - `kind`: **Texto** `request`;
    - `request_id`: **Texto** ficha `RequestID`;
    - `prompt`: **Texto** ficha `Prompt`;
    - `acknowledged`: **Booleano** falso.
15. **Obtener texto de la entrada** desde `NuevoBorrador`.
16. **Definir nombre** `pending.json`.
17. **Guardar archivo** en carpeta fija `En mi iPhone/FirstMate`, preguntar desactivado, sobrescribir activado.
18. **Ejecutar atajo** `First Mate Enviar Pendiente`.
19. **Detener este atajo**.

### Comprobación manual no destructiva

Sin dictar ni ejecutar, verifica que el guardado está **antes** de ejecutar el auxiliar, que `First Mate UUID` aparece una sola vez y que la condición vacía es `Prompt` **Texto**, operador `no tiene valor`, sin derecha. Para comprobar cancelación sin alterar archivos, abre `Dictar texto` y confirma que iOS ofrece cancelar; no inicies el atajo.

## 8. «Leer First Mate»

Esta es la variante físicamente probada en el iPhone. Evita expresiones regulares al convertir el cursor. `Authorization` enlaza al Texto compuesto, los literales de reemplazo no llevan acentos graves y la verificación usa la carpeta fija `FirstMate`, no la salida de Guardar archivo.

### Variables

| Variable | Tipo |
| --- | --- |
| `Config`, `Guardado`, `Pagina`, `CursorTemporal`, `CursorGuardado`, `CursorVerificado` | Diccionario |
| `BaseURL`, `Token`, `Authorization`, `BaseGuardada`, `CursorJSON`, `CursorSinInicio`, `CursorURL`, `TextoURL`, `TipoEvento`, `Voz`, `BaseVerificada` | Texto |
| `ArchivoCursor`, `ArchivoCursorVerificado` | Archivo o sin valor / Archivo |
| `Cursor`, `Leidos`, `CursorPeticion`, `NumeroEventos`, `Candidato`, `AfterVerificado` | Número |
| `Endpoint` | URL |
| `Eventos` | Lista |
| `HayMas` | Booleano JSON; en el iPhone probado, Número `0`/`1` tras `+ 0` |
| `Elemento repetido` | Diccionario |

### Acciones, en orden

1. Ejecuta `First Mate Config` → `Config` (**Diccionario**).
2. Obtén `base_url`, conviértelo con **Obtener texto de la entrada** → `BaseURL` (**Texto**).
3. Obtén `token`, conviértelo a texto → `Token` (**Texto**).
4. **Texto** `Bearer ` + ficha `Token`.
5. Define `Authorization` (**Texto**) con **la salida de la acción 4**, no con `Token`.
6. **Si** `BaseURL` (**Texto**) **no tiene valor**: leer `Revisa la configuración privada de First Mate`; detener; **Fin de Si**.
7. **Si** `Token` (**Texto**) **no tiene valor**: misma frase y detener; **Fin de Si**.
8. **Obtener archivo de carpeta** fija `En mi iPhone/FirstMate`, ruta `voice-cursor.json`, error si falta desactivado → `ArchivoCursor`.
9. **Si** `ArchivoCursor` (**Archivo**) **no tiene valor**.
10. Rama verdadera: **Número** `0`; definir `Cursor` (**Número**).
11. Rama `Si no`: obtener diccionario desde `ArchivoCursor` → `Guardado` (**Diccionario**).
12. Obtener `base_url`, convertir a texto → `BaseGuardada` (**Texto**).
13. Obtener `after`, **Calcular** `+ 0` → `Cursor` (**Número**).
14. **Si** `BaseGuardada` (**Texto**) **no es** `BaseURL` (**Texto**): leer `Revisa el cursor y la base de First Mate`; detener; **Fin de Si**.
15. Cierra **Fin de Si** de archivo.
16. **Número** `0`; definir `Leidos` (**Número**).
17. **Repetir** 10 veces. Todo hasta la acción 60 queda dentro.
18. Definir `CursorPeticion` (**Número**) con `Cursor`.
19. **Diccionario** `after` (**Número**) = `CursorPeticion` → `CursorTemporal`.
20. **Obtener texto de la entrada** desde `CursorTemporal` → `CursorJSON` (**Texto**).
21. **Reemplazar texto**, expresión regular desactivada, buscar literalmente `{"after":`, reemplazo vacío, entrada `CursorJSON` → `CursorSinInicio` (**Texto**). **No incluyas acentos graves**.
22. **Reemplazar texto**, expresión regular desactivada, buscar literalmente `}`, reemplazo vacío, entrada `CursorSinInicio` → `CursorURL` (**Texto**). **No incluyas acentos graves**.
23. **Si** `CursorURL` (**Texto**) **no tiene valor**: leer `Respuesta de First Mate inválida; no se avanzó la lectura`; detener; **Fin de Si**.
24. **Texto** formado por `BaseURL`, literal `/voice/events?after=`, `CursorURL`, literal `&limit=5` → `TextoURL` (**Texto**).
25. **URL** desde `TextoURL` → `Endpoint` (**URL**).
26. **Obtener contenido de URL** `Endpoint`: método **GET**, cabecera `Authorization` = variable `Authorization`, sin cuerpo y sin `Content-Type`.
27. **Obtener diccionario de la entrada** → `Pagina` (**Diccionario**).
28. Obtener `error` → `ErrorPublico` (**Texto o sin valor**).
29. **Si** `ErrorPublico` (**Texto**) **tiene valor**: no leas el valor. Según el caso conocido, lee una de estas frases y detén: `Revisa el token privado de First Mate` para autenticación; `First Mate no está disponible. Reintenta más tarde` para indisponibilidad/cuota; `Revisa el cursor y la base de First Mate` para cursor adelantado; si iOS no permite distinguir el código con seguridad, usa `Respuesta de First Mate inválida; no se avanzó la lectura`; **Fin de Si**.
30. Obtener `events` → `Eventos` (**Lista**).
31. Obtener `has_more`; **Calcular** `+ 0` → `HayMas` (**Número 0 o 1 en el iPhone probado**).
32. **Contar** `Eventos` → `NumeroEventos` (**Número**).
33. **Si** `NumeroEventos` (**Número**) **es** `0` (**Número**).
34. Dentro, **Si** `Leidos` (**Número**) **es** `0`: **Leer texto** `No hay respuestas nuevas`; **Fin de Si**.
35. **Detener este atajo**; cierra **Fin de Si** exterior.
36. **Repetir con cada elemento** de `Eventos`; la variable mágica `Elemento repetido` debe ser **Diccionario**.
37. Obtener `event_type` de `Elemento repetido`, convertir a texto → `TipoEvento` (**Texto**).
38. **Si** `TipoEvento` (**Texto**) **es** `needs_input` (**Texto literal**).
39. Rama verdadera: obtener `question`, convertir a texto → `Voz` (**Texto**).
40. Rama `Si no`: obtener `spoken_response`, convertir a texto → `Voz` (**Texto**).
41. Cierra **Fin de Si**.
42. **Si** `Voz` (**Texto**) **no tiene valor**: leer `Respuesta de First Mate inválida; no se avanzó la lectura`; detener; **Fin de Si**.
43. **Leer texto** `Voz`, idioma español, **Esperar hasta que termine** activado.
44. Solo ahora, obtener `event_id` de `Elemento repetido`; **Calcular** `+ 0` → `Candidato` (**Número**).
45. **Diccionario** `base_url` (**Texto**) = `BaseURL`, `after` (**Número**) = `Candidato` → `CursorGuardado`.
46. **Obtener texto de la entrada** desde `CursorGuardado`.
47. **Definir nombre** `voice-cursor.json`.
48. **Guardar archivo** en carpeta fija `En mi iPhone/FirstMate`, preguntar desactivado, sobrescribir activado.
49. **Obtener archivo de carpeta** usando otra vez la **carpeta fija** `En mi iPhone/FirstMate` y ruta literal `voice-cursor.json` → `ArchivoCursorVerificado`. No uses `Archivo guardado` como carpeta.
50. Obtener diccionario → `CursorVerificado`.
51. Obtener `base_url`, convertir a texto → `BaseVerificada` (**Texto**).
52. Obtener `after`, calcular `+ 0` → `AfterVerificado` (**Número**).
53. **Si** `BaseVerificada` (**Texto**) **no es** `BaseURL` (**Texto**): leer `No se pudo guardar el progreso de lectura`; detener; **Fin de Si**.
54. **Si** `AfterVerificado` (**Número**) **no es** `Candidato` (**Número**): misma frase y detener; **Fin de Si**.
55. Definir `Cursor` (**Número**) con `Candidato`.
56. **Calcular** `Leidos + 1`; volver a definir `Leidos` (**Número**).
57. Cierra **Fin de Repetir con cada elemento**.
58. **Si** `HayMas` (**Número**) **es** `0` (**Número**): detener; **Fin de Si**.
59. Cierra **Fin de Repetir** de diez páginas.
60. Fuera del bucle: **Leer texto** `Quedan respuestas. Vuelve a ejecutar Leer First Mate para continuar`.
61. **Detener este atajo**.

### Validación estricta recomendada antes de hablar

La receta físicamente probada anterior verificó el recorrido, pero la UI de ese iPhone convirtió `has_more` a 0/1. Para reforzarla sin inventar el tipo que muestre otra versión, observa **sin ejecutar red** cómo presenta iOS los tipos de un Diccionario local de ejemplo:

- Si `Obtener tipo` llama **Booleano** a `true/false`, exige `has_more` **Booleano** y no lo conviertas.
- Si lo llama **Número**, serializa `Pagina` y exige que el JSON contenga `"has_more":true` o `"has_more":false`, nunca los textos `"true"`/`"false"`; solo después usa `+ 0`.

Antes de `Leer texto`, valida además el contrato de [la API](http-api.md): página con exactamente `events`, `next_cursor`, `has_more`; 0–5 eventos; cada evento con `event_id`, `job_id`, `event_type`, `at` y exactamente `question` o `spoken_response`; IDs crecientes; voz no blanca de 1–900 caracteres. Si no puedes construir honestamente una comprobación de tipo en tu versión, **no conviertas ni aceptes el dato**: detén y observa en el editor qué etiqueta de tipo ofrece iOS para el Diccionario local, sin llamar al servidor.

### Comprobación manual no destructiva

Sin ejecutar, revisa los tres puntos físicamente demostrados: acción 5 enlaza al Texto compuesto; acciones 21–22 no contienen `` ` ``; acción 49 usa la carpeta fija. Confirma también que Guardar está después de `Leer texto`. No borres ni restablezcas el cursor para comprobarlo.

## 9. «First Mate Responder»

### Variables

| Variable | Tipo | Origen |
| --- | --- | --- |
| `ArchivoPendiente` | Archivo o sin valor | `pending.json` |
| `Borrador`, `Config`, `RespuestaGET`, `Seleccionado`, `Mapa`, `NuevoBorrador` | Diccionario |
| `Confirmado`, `HayMas` | Booleano (con la salvedad de representación JSON explicada abajo) |
| `BaseURL`, `Token`, `Authorization`, `ErrorPublico`, `IDElemento`, `PreguntaElemento`, `EstadoElemento`, `Etiqueta`, `JobID`, `Pregunta`, `Estado`, `ReplyID`, `Dictado`, `Prompt` | Texto |
| `Trabajos`, `Opciones` | Lista |
| `NecesitaSeleccion` | Número (`0` o `1`) |
| `Cantidad`, `RevisionElemento`, `Revision` | Número |
| `Endpoint` | URL |
| `Elemento repetido` | Diccionario |

### Acciones, en orden

1. Obtener `En mi iPhone/FirstMate/pending.json`, error si falta desactivado → `ArchivoPendiente` (**Archivo o sin valor**).
2. **Si** `ArchivoPendiente` (**Archivo**) **tiene valor**.
3. Obtener diccionario → `Borrador`; obtener `acknowledged` → `Confirmado` (**Booleano**).
4. **Si** `Confirmado` (**Booleano**) **es verdadero**: deja la rama verdadera vacía.
5. Rama `Si no`: menú `Reintentar pendiente` / `Salir`.
6. Reintentar: ejecutar `First Mate Enviar Pendiente` y detener. Salir: detener.
7. Cierra menú y ambos **Fin de Si**.
8. Ejecutar `First Mate Config` → `Config` (**Diccionario**).
9. Extraer `base_url` → `BaseURL` (**Texto**) y `token` → `Token` (**Texto**).
10. **Texto** `Bearer ` + ficha `Token` → `Authorization` (**Texto**). La variable debe proceder de esta acción Texto.
11. **Texto** `BaseURL` + literal `/jobs/pending-input`; **URL** → `Endpoint`.
12. **Obtener contenido de URL** `Endpoint`: método **GET**, cabecera `Authorization` = `Authorization`, sin cuerpo.
13. Obtener diccionario → `RespuestaGET`.
14. Obtener `error` → `ErrorPublico` (**Texto o sin valor**).
15. **Si** `ErrorPublico` (**Texto**) **tiene valor**: leer `No se pudieron consultar las preguntas`; detener; **Fin de Si**. El operador correcto es “tiene valor”.
16. Obtener `jobs` → `Trabajos` (**Lista esperada**).
17. **Obtener tipo** de `Trabajos` → `TipoTrabajos` (**Texto**).
18. **Si** `TipoTrabajos` (**Texto**) **no es** `Lista` (**Texto literal que muestre iOS para una lista**): leer `Respuesta de First Mate inválida`; detener; **Fin de Si**.
19. Obtener `has_more` → `HayMas` (**Booleano esperado**).
20. **Obtener tipo** → `TipoHayMas` (**Texto**).
21. Valida el booleano como se explica en la sección del lector: si iOS lo presenta como Número, confirma en el JSON serializado que es `true|false`, no texto. Ante cualquier duda: leer `Respuesta de First Mate inválida` y detener.
22. **Contar** `Trabajos` → `Cantidad` (**Número**).
23. **Si** `Cantidad` (**Número**) **es** `0`.
24. Dentro: **Si** `HayMas` (**Booleano**) **es verdadero**: leer `Respuesta de First Mate inválida`; detener.
25. Rama `Si no`: leer `No hay preguntas pendientes`; detener. Cierra ambos `Si`.
26. **Número** `0`; define `NecesitaSeleccion` (**Número**).
27. **Si** `Cantidad` (**Número**) **es** `1` (**Número**).
28. Dentro: **Si** `HayMas` (**Booleano**) **es verdadero**: crea **Número** `1` y vuelve a definir `NecesitaSeleccion` (**Número**); en `Si no`, **Obtener primer elemento de la lista** → `Seleccionado` (**Diccionario**). Cierra ambos `Si`.
29. **Si** `Cantidad` (**Número**) **es mayor que** `1` (**Número**): crea **Número** `1` y vuelve a definir `NecesitaSeleccion` (**Número**); **Fin de Si**.
30. **Si** `NecesitaSeleccion` (**Número**) **es** `1` (**Número**). Todo el bloque de selección siguiente va dentro y se construye una sola vez.
31. **Lista** vacía → `Opciones`; **Diccionario** vacío → `Mapa`.
32. **Si** `HayMas` (**Booleano**) **es verdadero**: leer `Se muestran las primeras 100; elige una explícitamente`; **Fin de Si**.
33. **Repetir con cada elemento** de `Trabajos`; fija `Elemento repetido` como **Diccionario**.
34. Obtener `id` → `IDElemento` (**Texto**).
35. Obtener `question`, recortar con `^\s+|\s+$` → `PreguntaElemento` (**Texto**).
36. Obtener `input_revision` → `RevisionElemento` (**Número**).
37. Obtener `state` → `EstadoElemento` (**Texto**).
38. Coincidir `IDElemento` con patrón UUID; contar → `CoincidenciasIDElemento` (**Número**).
39. **Si** `CoincidenciasIDElemento` (**Número**) **no es** `1`: leer `Respuesta de First Mate inválida`; detener; **Fin de Si**.
40. **Si** `PreguntaElemento` (**Texto**) **no tiene valor**: misma frase y detener; **Fin de Si**.
41. Redondear `RevisionElemento` a unidades → `RevisionElementoRedondeada`.
42. **Si** `RevisionElemento` (**Número**) **es menor que** `1`: misma frase y detener; **Fin de Si**.
43. **Si** `RevisionElemento` (**Número**) **no es** `RevisionElementoRedondeada` (**Número**): misma frase y detener; **Fin de Si**.
44. **Si** `EstadoElemento` (**Texto**) **no es** `waiting_for_input` (**Texto literal**): misma frase y detener; **Fin de Si**. El operando derecho es obligatorio y no puede quedar vacío.
45. **Texto** con ficha `Índice de repetición`, literal ` · `, ficha `PreguntaElemento`, literal ` · `, ficha `IDElemento` completo → `Etiqueta` (**Texto**). Comprueba visualmente las tres fichas.
46. **Añadir a variable** `Opciones` la `Etiqueta`.
47. **Establecer valor del diccionario** en `Mapa`: clave `Etiqueta`, valor **la variable mágica `Elemento repetido` de tipo Diccionario**, no un texto ni una salida vacía; vuelve a definir `Mapa`.
48. Cierra **Fin de Repetir**.
49. **Elegir de la lista** `Opciones`, selección múltiple desactivada → `EtiquetaElegida` (**Texto**).
50. **Si** `EtiquetaElegida` (**Texto**) **no tiene valor**: detener; **Fin de Si**. Cancelar no selecciona el primero.
51. Obtener de `Mapa` la clave `EtiquetaElegida` → `Seleccionado` (**Diccionario**).
52. Cierra **Fin de Si** de `NecesitaSeleccion`.
53. Tras converger la rama única y la de selección, extrae de `Seleccionado`: `id` → `JobID` (**Texto**), `question` recortada → `Pregunta` (**Texto**), `input_revision` → `Revision` (**Número**), `state` → `Estado` (**Texto**).
54. Coincidir `JobID` con UUID; contar → `CoincidenciasJobID`.
55. **Si** `CoincidenciasJobID` (**Número**) **no es** `1`: leer `Respuesta de First Mate inválida`; detener; **Fin de Si**.
56. **Si** `Pregunta` (**Texto**) **no tiene valor**: leer la misma frase; detener; **Fin de Si**. Esta condición es exactamente `no tiene valor`, **sin operando derecho**.
57. Redondear `Revision` → `RevisionRedondeada`.
58. **Si** `Revision` (**Número**) **es menor que** `1`: error y detener; **Fin de Si**.
59. **Si** `Revision` (**Número**) **no es** `RevisionRedondeada` (**Número**): error y detener; **Fin de Si**.
60. **Si** `Estado` (**Texto**) **no es** `waiting_for_input` (**Texto literal**): error y detener; **Fin de Si**.
61. **Leer texto** usando **solo** `Pregunta`.
62. **Ejecutar atajo** `First Mate UUID` una vez → `ReplyID` (**Texto**).
63. **Dictar texto**, idioma español, finalizar **Al tocar** → `Dictado` (**Texto**). No cambies esta modalidad.
64. **Reemplazar texto** en `Dictado`, regex `^\s+|\s+$`, reemplazo vacío → `Prompt` (**Texto**).
65. **Si** `Prompt` (**Texto**) **no tiene valor**: detener; **Fin de Si**.
66. **Diccionario** → `NuevoBorrador`:
    - `kind`: **Texto** `reply`;
    - `request_id`: **Texto** `ReplyID`;
    - `prompt`: **Texto** `Prompt`;
    - `job_id`: **Texto** `JobID`;
    - `input_revision`: **Número** `Revision`;
    - `acknowledged`: **Booleano** falso.
67. **Obtener texto de la entrada** desde `NuevoBorrador`.
68. **Definir nombre** `pending.json`.
69. **Guardar archivo** en carpeta fija `En mi iPhone/FirstMate`, preguntar desactivado, sobrescribir activado.
70. **Ejecutar atajo**: vuelve a elegir manualmente en el selector el auxiliar definitivo **First Mate Enviar Pendiente**. No confíes en un enlace heredado de una copia renombrada.
71. **Detener este atajo**.

### Comprobación manual no destructiva

Sin ejecutar ni consultar preguntas, revisa visualmente:

- `ErrorPublico Texto tiene valor`;
- `EstadoElemento Texto no es waiting_for_input` y `Estado Texto no es waiting_for_input`, ambos con derecha presente;
- la etiqueta contiene índice, pregunta e ID;
- `Mapa` recibe `Elemento repetido` de tipo **Diccionario**;
- `Pregunta Texto no tiene valor` no lleva derecha;
- dictado termina `Al tocar`;
- el archivo se guarda antes de invocar el auxiliar;
- la última acción está enlazada a la tarjeta actual de **First Mate Enviar Pendiente**.

No ejecutes una pregunta real para verificar el montaje.

## 10. Métodos, URL, cabeceras y JSON

| Atajo | Método y URL | Cabeceras | Cuerpo |
| --- | --- | --- | --- |
| First Mate Enviar Pendiente, request | `POST <BASE_URL>/jobs` | `Authorization: Bearer <TOKEN>`; `Content-Type: application/json` | `request_id` Texto, `prompt` Texto |
| First Mate Enviar Pendiente, reply | `POST <BASE_URL>/jobs/{job_id}/reply` | las mismas | `request_id` Texto, `prompt` Texto, `input_revision` Número |
| Leer First Mate | `GET <BASE_URL>/voice/events?after={entero}&limit=5` | solo `Authorization: Bearer <TOKEN>` | ninguno |
| First Mate Responder | `GET <BASE_URL>/jobs/pending-input` | solo `Authorization: Bearer <TOKEN>` | ninguno |

No pongas token en URL. No sigas redirecciones ni URLs procedentes de dictado, pregunta o ntfy. Los GET no llevan cuerpo.

Recibo POST esperado:

```json
{
  "accepted": true,
  "id": "UUID-del-job",
  "voice_session_id": "identificador-de-sesion",
  "state": "queued",
  "cancel_requested": false
}
```

Estados admitidos: `queued`, `running`, `waiting_for_input`, `completed`, `failed`, `cancelled`.

## 11. Mensajes visibles y hablados

Usa exactamente estos textos; nunca concatentes JSON, token, URL, ID, cuerpo de error o diagnóstico:

- `Enviado`
- `Borrador inválido`
- `No se confirmó el envío; conserva el borrador y reintenta`
- `Revisa la configuración privada de First Mate`
- `No hay respuestas nuevas`
- `Respuesta de First Mate inválida; no se avanzó la lectura`
- `No se pudo guardar el progreso de lectura`
- `Quedan respuestas. Vuelve a ejecutar Leer First Mate para continuar`
- `No se pudieron consultar las preguntas`
- `Respuesta de First Mate inválida`
- `No hay preguntas pendientes`
- `Se muestran las primeras 100; elige una explícitamente`
- `Revisa el token privado de First Mate`
- `First Mate no está disponible. Reintenta más tarde`
- `Revisa el cursor y la base de First Mate`

El contenido dinámico hablado se limita a `question` o `spoken_response`.

## 12. Notificaciones ntfy

ntfy no es un atajo. Su función es avisar de `needs_input`, `completed`, `failed` o `cancelled`; después el capitán inicia **Leer First Mate** o **First Mate Responder**. La entrega del aviso no modifica `pending.json` ni `voice-cursor.json`.

La apertura al tocar solo admite, si se configura y se valida físicamente:

```text
shortcuts://run-shortcut?name=Leer%20First%20Mate
```

Mantenerla desactivada es la opción segura hasta probarla. La llegada de un push no ejecuta automáticamente Atajos. Anunciar notificaciones, pantalla bloqueada, Focus, AirPods y ruta de audio siguen dependiendo del dispositivo y no se consideran probados por este manual.

## 13. Dependencias

| Atajo | Depende de | Lee | Escribe | Red |
| --- | --- | --- | --- | --- |
| First Mate Config | secretos introducidos localmente | — | — | — |
| First Mate UUID | — | — | — | — |
| First Mate Enviar Pendiente | Config | `pending.json` | `pending.json` confirmado | POST `/jobs` o `/reply` |
| First Mate | UUID, Enviar Pendiente | `pending.json` | `pending.json` request | indirecta por auxiliar |
| Leer First Mate | Config | `voice-cursor.json` | `voice-cursor.json` | GET `/voice/events` |
| First Mate Responder | Config, UUID, Enviar Pendiente | `pending.json` | `pending.json` reply | GET `/jobs/pending-input`, luego POST indirecto |
| ntfy (no es atajo) | servidor/worker | feed propio de ntfy | no toca archivos de Atajos | push independiente |

## 14. Lista de verificación de extremo a extremo, sin preguntas reales

Esta lista es una **revisión de construcción**. No pide ejecutar trabajos ni contestar preguntas reales.

### Configuración y privacidad

- [ ] Existen exactamente los seis atajos con los nombres indicados.
- [ ] Existe `En mi iPhone/FirstMate` y no se comparte por iCloud.
- [ ] Solo **First Mate Config** contiene la URL y token reales.
- [ ] No hay Vista rápida, portapapeles, avisos ni voz sobre secretos/JSON.
- [ ] Todos los ficheros usan carpeta fija `FirstMate` y nombres literales correctos.

### Identidad y borrador

- [ ] UUID fija versión 4 en posición 13 y variante `[89ab]` en posición 17.
- [ ] First Mate genera un ID una vez, recorta el dictado y guarda antes del POST.
- [ ] Responder genera un ID una vez después de seleccionar la pregunta.
- [ ] Un borrador sin confirmar ofrece solo reintentar o salir y nunca se sobrescribe.
- [ ] Sender acepta `request_id` `[A-Za-z0-9_-]{1,200}` y exige UUID solo para `job_id`/`ReceiptID`.
- [ ] Request y reply tienen cuerpos JSON separados y tipados.

### Autenticación y recibo

- [ ] Cada `Authorization` procede de la acción **Texto** `Bearer ` + `Token`, no de `Token` solo.
- [ ] Los GET no tienen cuerpo ni `Content-Type`.
- [ ] El POST usa `Content-Type: application/json`.
- [ ] `Enviado` aparece únicamente tras `accepted=true`, recibo válido y guardado confirmado.
- [ ] Reply exige `ReceiptID = JobID`.
- [ ] Todos los `Si` conservan izquierda, tipo, operador y derecha exigida al reabrir el editor.

### Lectura

- [ ] La URL contiene `after` decimal y `limit=5`; los reemplazos no contienen acentos graves.
- [ ] Solo se pronuncia `question` para `needs_input`; para terminales, `spoken_response`.
- [ ] `Leer texto` espera hasta terminar.
- [ ] El cursor se guarda después de hablar cada elemento, nunca antes.
- [ ] La verificación relee `FirstMate/voice-cursor.json` desde la carpeta fija.
- [ ] Una página vacía no cambia el cursor.
- [ ] ntfy no modifica el cursor.

### Respuesta

- [ ] `jobs` es Lista y `has_more` es booleano JSON antes de usarlos.
- [ ] Con `has_more=true` nunca se selecciona automáticamente el único elemento visible.
- [ ] Cada opción contiene índice, pregunta e ID completo.
- [ ] Cancelar la lista detiene; no usa el primer elemento.
- [ ] `Mapa` guarda el Diccionario `Elemento repetido`.
- [ ] Seleccionado exige UUID, pregunta no vacía, revisión entera positiva y estado exacto.
- [ ] Solo se pronuncia `question`.
- [ ] Reply conserva `job_id` y `input_revision`; no crea otro `/jobs`.

### Fallos y cancelación

- [ ] Timeout conserva `pending.json` y el mismo `request_id`.
- [ ] Un conflicto de reply no altera revisión ni cambia de pregunta.
- [ ] Dictado vacío detiene antes de escribir o enviar.
- [ ] Un error de lectura no avanza cursor.
- [ ] No existe un atajo de cancelación improvisado; detener localmente no se presenta como cancelación remota.
- [ ] No se ejecutan pruebas contra preguntas reales para validar esta construcción.

## 15. Incertidumbres que deben observarse sin enviar nada

1. **Representación de booleanos JSON.** Según versión de iOS, `Obtener tipo` puede mostrar Booleano o Número. Crea un Diccionario local temporal con un booleano, serialízalo y observa la etiqueta de tipo y el JSON, sin red. Exige JSON `true/false`; no aceptes texto o 0/1 de origen desconocido.
2. **Nombres localizados de tipos.** Si `Obtener tipo` devuelve una etiqueta distinta de `Lista`/`Booleano`, usa exactamente la etiqueta que iOS muestre para una Lista/Booleano local creado en Atajos; no adivines ni hagas GET.
3. **Persistencia de condiciones.** La construcción manual debe revisarse reabriendo cada tarjeta `Si`; si iOS no conserva una ficha o un operando derecho, corrígelo antes de cualquier ejecución.
4. **Notificaciones bloqueadas y audio.** Focus, bloqueo, AirPods, llamadas y Anunciar notificaciones no están físicamente fijados de forma general. Obsérvalos después, con contenido sintético, sin asumir que un aviso confirma escucha.

## Referencias del repositorio

- [Contrato y receta iPhone](ios-shortcut.md)
- [Detalle de First Mate Responder](ios-shortcut-responder.md)
- [Contrato HTTP](http-api.md)
- [Arquitectura de integración](integration.md)
- [README](../README.md)
