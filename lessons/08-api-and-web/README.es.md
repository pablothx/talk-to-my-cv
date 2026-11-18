# Paso 8: API y página web

🇬🇧 [Read in English](README.md)

## Qué vas a aprender

- A exponer el RAG como una **API HTTP** con FastAPI, y a testearla sin modelos reales.
- Por qué la respuesta de un LLM es **entrada no confiable** para tu página, y cómo mostrarla sin riesgo.
- A correr la API en un **contenedor** que usa el Ollama de tu máquina, y el detalle de Linux que lo rompe.

## El concepto

### Inyectar la función, no los modelos

La API no sabe nada de embeddings, stores ni LLMs. Recibe una sola función:

```python
create_app(ask)  # ask: pregunta → Answer
```

En producción, `ask` es el pipeline o el grafo del paso 7, armado desde `.env` (`ENGINE` sigue eligiendo). En los tests, es un fake de tres líneas. Así los tests de la API corren en milisegundos y en CI, sin Ollama.

### La respuesta del LLM es entrada no confiable

En el paso 3 vimos el prompt injection: alguien escribe en la pregunta instrucciones para el modelo. Ahora hay un riesgo nuevo. Si la página mostrara la respuesta como HTML, alcanzaría con convencer al modelo de escribir `<script>...</script>` para ejecutar código en el navegador de quien lee la página. Eso es **XSS** (*cross-site scripting*).

Además, la página muestra la pregunta otra vez, así que ni siquiera hace falta engañar al modelo: alcanza con escribir el `<script>` en la pregunta.

Dos defensas, y cada una alcanza sola:

1. **Todo lo dinámico pasa por `html.escape`**: la pregunta, la respuesta y las citas. `<script>` se muestra como texto: `&lt;script&gt;`.
2. **La página no tiene JavaScript**, y se lo dice al navegador con un header `Content-Security-Policy: script-src 'none'`. Aunque un escape fallara, el navegador no ejecutaría el script.

Sin JavaScript, el formulario hace un POST común y el servidor devuelve la página con la respuesta. Es menos lindo que un chat que escribe palabra por palabra, pero no hay nada que inyectar.

### El contenedor y el Ollama de tu máquina

Hasta acá todo el Python corría en tu máquina ([ADR-0001](../../docs/adr/0001-python-on-host-infra-in-compose.md)). La API es el primer contenedor de la app, y le habla a los stores por nombre de servicio (`postgres`, `opensearch`) y a Ollama, que corre nativo, por `host.docker.internal`.

En macOS y Windows (Docker Desktop) eso anda solo. **En Linux, no:** `host.docker.internal` apunta a la IP de `docker0` (172.17.0.1), y Ollama escucha solo en `127.0.0.1`. La conexión se rechaza.

| Opción | Problema |
|---|---|
| `OLLAMA_HOST=0.0.0.0` en el servicio de Ollama (lo que dice su FAQ) | Necesita sudo, y Ollama, que no tiene autenticación, queda abierto a tu red local. |
| `network_mode: host` en la API | Cambia todas las direcciones, y en Docker Desktop se comporta distinto. |
| **Un puente con socat** | Un contenedor chiquito escucha en `172.17.0.1:11434` y reenvía a `127.0.0.1:11434`. Sin sudo, y solo los contenedores llegan. |

Elegimos el puente ([ADR-0012](../../docs/adr/0012-api-container-reaches-native-ollama-through-a-bridge.md)). `make api-up` lo agrega solo en Linux.

## El código

| Archivo | Qué hace |
|---------|----------|
| `src/talk_to_my_cv/api.py` | `create_app(ask)`: `POST /api/ask` (JSON), `GET /` y `POST /` (la página), `GET /health`. Si no llega a Ollama, devuelve un 503 que explica qué revisar. |
| `src/talk_to_my_cv/engines.py` | `build_ask(settings)`: arma `ask` con los modelos, el store y el motor de `.env`. |
| `Dockerfile`, `.dockerignore` | La imagen de la API. `.dockerignore` es una lista de lo permitido: `.env` y `kb/` (tus datos reales) nunca entran a la imagen. |
| `compose.yaml` | Los servicios `api` (perfil `api`) y `ollama-bridge` (perfil `bridge`). |

La API valida la pregunta antes de llamar a cualquier modelo: vacía o con más de 500 caracteres devuelve 422. Un rechazo es una respuesta normal (200, `"refused": true`), no un error.

```bash
curl -s localhost:8000/api/ask -H 'content-type: application/json' \
  -d '{"question": "How much did Project Lumen speed up reconciliation?"}'
```

```json
{"answer": "Project Lumen sped up reconciliation from 9 hours to 14 minutes.",
 "refused": false,
 "citations": ["experience/northwind-payments.md § Senior Backend Engineer > Project Lumen"]}
```

## Cómo comprobar que anda

```bash
make check-08        # pasos 0 a 8; levanta el contenedor
make serve           # o sin Docker: la API en tu máquina, http://localhost:8000
make api-up          # la API en un contenedor, http://localhost:8000
make api-down
```

Abrí http://localhost:8000 y preguntá. Después probá escribir `<script>alert(1)</script>` como pregunta: tiene que aparecer como texto.

### Lo que nos costó

**El contenedor arrancaba sano y respondía 500.** `/health` decía `ok`, pero cada pregunta fallaba con `Failed to connect to Ollama`: es el problema de Linux de arriba. `/health` solo dice que el proceso vive, no que sus dependencias anden. Ahora ese error es un 503 con una pista (`OLLAMA_HOST`), en la API y en la página.

## Para jugar

1. **Rompé una defensa por vez.** En `render_page()` (`api.py`), sacá el `escape()` de la pregunta y preguntá `</textarea><h1>hola</h1>`: el título aparece en la página. Ahora preguntá `</textarea><script>alert(1)</script>`: ¿se ejecuta? No debería, porque la CSP lo frena. Sacá también el header CSP y volvé a probar. Al terminar, volvé a poner las dos defensas.
2. **Usá la API desde otro programa.** Escribí un script que lea preguntas de un archivo, llame a `/api/ask` y guarde las respuestas. Es la base de un bot de Slack o de un widget en tu web personal.
3. **Cambiá el motor.** Poné `ENGINE=graph` en `.env`, corré `make api-up` de nuevo y preguntá "Has she worked with JavaScript?". Compará la respuesta y el tiempo con `ENGINE=pipeline`.

## Limitaciones conocidas

- **Sin streaming:** la página espera la respuesta entera (10 a 30 segundos en CPU), sin indicador de progreso, porque no tiene JavaScript.
- **Sin autenticación ni límite de pedidos.** Está bien en tu máquina; publicarla así deja que cualquiera use tu CPU (o tu cuenta de Groq). En AWS, ver [docs/produccion-en-aws.md](../../docs/produccion-en-aws.md).
- **Una pregunta a la vez por proceso:** FastAPI atiende varias, pero Ollama en CPU genera una respuesta por vez, así que las demás esperan.
