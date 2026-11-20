# Paso 8: API y página web

🇬🇧 [Read in English](README.md)

Hasta acá el chat vivía en la terminal. En este paso lo convertimos en una **API HTTP** y una **página web**, y lo metemos en un contenedor. Con eso, cualquier otro programa (un bot de Slack, tu web personal) puede usarlo.

## Qué vas a aprender

- A exponer el RAG como una **API** con FastAPI, y a testearla sin modelos reales.
- Por qué la respuesta de un LLM es **entrada no confiable** para tu página, y cómo mostrarla sin riesgo.
- A correr la API en un **contenedor** que usa el Ollama de tu máquina, y el detalle de Linux que lo rompe.

---

## Pieza 1 de 7: la API en una línea

```bash
make serve
```

Levanta la API en http://localhost:8000. Desde otra terminal:

```bash
curl -s localhost:8000/api/ask -H 'content-type: application/json' \
  -d '{"question": "How much did Project Lumen speed up reconciliation?"}'
```

```json
{"answer": "Project Lumen sped up reconciliation from 9 hours to 14 minutes.",
 "refused": false,
 "citations": ["experience/northwind-payments.md § Senior Backend Engineer > Project Lumen"]}
```

Y si abrís http://localhost:8000 en el navegador, hay una página con un formulario.

## Pieza 2 de 7: los endpoints

| Ruta | Qué hace |
|---|---|
| `POST /api/ask` | JSON in, JSON out. Para otros programas. |
| `GET /` | La página con el formulario. |
| `POST /` | La página con la respuesta. |
| `GET /health` | Dice `ok` si el proceso está vivo. |

La API valida la pregunta **antes** de llamar a cualquier modelo: vacía o con más de 500 caracteres devuelve **422** (error de validación). Un rechazo es una respuesta normal (**200**, `"refused": true`), no un error.

## Pieza 3 de 7: inyectar la función, no los modelos

La API no sabe nada de embeddings, stores ni LLMs. Recibe **una sola función**:

```python
create_app(ask)  # ask: pregunta → Answer
```

- En producción, `ask` es el pipeline o el grafo, armado desde `.env` (`ENGINE` sigue eligiendo).
- En los tests, es un fake de tres líneas.

Así los tests de la API corren en milisegundos y en GitHub, sin Ollama. Es la misma idea del paso 0: **inyectar lo que viene de afuera**.

## Pieza 4 de 7: un riesgo nuevo, XSS

En el paso 3 vimos la prompt injection: alguien escribe instrucciones para el modelo en la pregunta. Ahora hay un riesgo nuevo.

Si la página mostrara la respuesta como HTML, alcanzaría con convencer al modelo de escribir `<script>...</script>` para **ejecutar código en el navegador de quien lee la página**. Eso es **XSS** (*cross-site scripting*).

Y es peor: la página muestra la pregunta otra vez, así que ni siquiera hace falta engañar al modelo. Alcanza con escribir el `<script>` en la pregunta.

> **La respuesta de un LLM es entrada no confiable**, igual que lo que escribe un usuario.

## Pieza 5 de 7: dos defensas

Cada una alcanza sola, y tenemos las dos:

1. **Todo lo dinámico pasa por `html.escape`:** la pregunta, la respuesta y las citas. `<script>` se muestra como texto: `&lt;script&gt;`.
2. **La página no tiene JavaScript**, y se lo dice al navegador con un header `Content-Security-Policy: script-src 'none'`. Aunque un escape fallara, el navegador no ejecutaría ningún script.

Sin JavaScript, el formulario hace un POST común y el servidor devuelve la página con la respuesta. Es menos lindo que un chat que escribe palabra por palabra, pero no hay nada que inyectar.

## Pieza 6 de 7: la API en un contenedor

Hasta acá todo el Python corría en tu máquina. La API es el primer contenedor de la app:

```bash
make api-up      # construye la imagen y la levanta en http://localhost:8000
make api-down
```

- La imagen (`Dockerfile`) usa Python 3.12 *slim*, instala las dependencias exactas de `uv.lock` y corre con un usuario sin privilegios.
- `.dockerignore` es una **lista de lo permitido**: solo entra el código, la configuración y las dependencias. **`.env` y `kb/` (tus datos reales) nunca entran a la imagen.**
- Adentro de Docker, la API le habla a Postgres y OpenSearch por nombre de servicio (`postgres`, `opensearch`), y a Ollama, que corre en tu máquina, por `host.docker.internal`.

## Pieza 7 de 7: el problema de Linux

En macOS y Windows (Docker Desktop), `host.docker.internal` anda solo. **En Linux, no:** apunta a la IP de la red de Docker (172.17.0.1), y Ollama escucha solo en `127.0.0.1`. La conexión se rechaza.

| Opción | Problema |
|---|---|
| Que Ollama escuche en todas las IPs (`OLLAMA_HOST=0.0.0.0`) | Necesita sudo, y Ollama, que no tiene contraseña, queda abierto a tu red local. |
| `network_mode: host` en la API | Cambia todas las direcciones, y en Docker Desktop se comporta distinto. |
| **Un puente con socat** | Un contenedor chiquito escucha en `172.17.0.1:11434` y reenvía a `127.0.0.1:11434`. Sin sudo, y solo los contenedores llegan. |

Elegimos el puente ([ADR-0012](../../docs/adr/0012-api-container-reaches-native-ollama-through-a-bridge.md)). `make api-up` lo agrega solo en Linux.

| Archivo | Qué hace |
|---------|----------|
| `src/talk_to_my_cv/api.py` | `create_app(ask)`: los endpoints, la página y el manejo de errores. |
| `src/talk_to_my_cv/engines.py` | `build_ask(settings)`: arma `ask` con los modelos, el store y el motor de `.env`. |
| `Dockerfile`, `.dockerignore` | La imagen de la API. |
| `compose.yaml` | Los servicios `api` (perfil `api`) y `ollama-bridge` (perfil `bridge`). |

---

## Cómo comprobar que anda

```bash
make check-08        # pasos 0 a 8; levanta el contenedor
make serve           # o sin Docker: la API en tu máquina
make api-up          # la API en un contenedor
```

Abrí http://localhost:8000 y preguntá. Después probá escribir `<script>alert(1)</script>` como pregunta: tiene que aparecer como texto.

### Lo que nos costó

**El contenedor arrancaba sano y respondía 500.** `/health` decía `ok`, pero cada pregunta fallaba con `Failed to connect to Ollama`: el problema de Linux de arriba. `/health` solo dice que el proceso vive, no que sus dependencias anden. Ahora ese error es un **503** con una pista (`OLLAMA_HOST`), en la API y en la página.

## Para jugar

1. **Rompé una defensa por vez.** En `render_page()` (`api.py`), sacá el `escape()` de la pregunta y preguntá `</textarea><h1>hola</h1>`: el título aparece en la página. Ahora preguntá `</textarea><script>alert(1)</script>`: ¿se ejecuta? No debería, porque la CSP lo frena. Sacá también el header CSP y volvé a probar. Al terminar, volvé a poner las dos defensas.
2. **Usá la API desde otro programa.** Escribí un script que lea preguntas de un archivo, llame a `/api/ask` y guarde las respuestas. Es la base de un bot de Slack o de un widget en tu web.
3. **Cambiá el motor.** Poné `ENGINE=graph` en `.env`, corré `make api-up` de nuevo y preguntá "Has she worked with JavaScript?". Compará la respuesta y el tiempo con `ENGINE=pipeline`.

## Limitaciones conocidas

- **Sin streaming:** la página espera la respuesta entera (10 a 30 segundos en CPU), sin indicador de progreso, porque no tiene JavaScript.
- **Sin autenticación ni límite de pedidos.** Está bien en tu máquina; publicarla así deja que cualquiera use tu CPU (o tu cuenta de Groq). Para publicarla, ver la [guía de producción en AWS](../../docs/produccion-en-aws.md).
- **Una respuesta a la vez:** FastAPI atiende varias preguntas juntas, pero Ollama en CPU genera una por vez, así que las demás esperan.

---

## ✋ Repaso

**1. ¿Por qué `create_app` recibe una función y no los modelos?**

<details><summary>Ver respuesta</summary>

Para que la API no dependa de Ollama ni de la base: en los tests le pasás un fake y corren en milisegundos, en GitHub. En producción le pasás el pipeline o el grafo.
</details>

**2. ¿Por qué la respuesta del LLM se trata como entrada no confiable?**

<details><summary>Ver respuesta</summary>

Porque alguien puede convencer al modelo de escribir HTML o `<script>`. Si la página lo mostrara tal cual, ejecutaría código en el navegador de quien la lee (XSS).
</details>

**3. 🧪 Probalo:** con `make serve`, preguntá `<script>alert(1)</script>` en la página. ¿Qué esperás ver?

<details><summary>Ver respuesta</summary>

El texto `<script>alert(1)</script>` tal cual, sin ninguna alerta. El escape lo convierte en texto, y aunque fallara, la CSP `script-src 'none'` impediría ejecutarlo.
</details>

**4. `/health` dice `ok` pero todas las preguntas fallan. ¿Cómo puede ser?**

<details><summary>Ver respuesta</summary>

`/health` solo dice que el proceso de la API está vivo, no que Ollama o la base respondan. En Linux, el contenedor no llegaba a Ollama. Ahora ese caso devuelve un 503 con una pista.
</details>

**5. ¿Por qué `.dockerignore` es una lista de lo permitido y no de lo prohibido?**

<details><summary>Ver respuesta</summary>

Porque si mañana alguien agrega un archivo sensible (otro `.env`, un CV), con una lista de prohibidos entraría a la imagen sin que nadie se dé cuenta. Con una lista de permitidos, solo entra lo que se nombró a propósito.
</details>

---

[← Paso 7](../07-langgraph/README.es.md) · [Índice](../../README.es.md) · [Bonus: producción en AWS →](../../docs/produccion-en-aws.md)
