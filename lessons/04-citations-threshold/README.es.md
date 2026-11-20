# Paso 4: Citas y umbral

🇬🇧 [Read in English](README.md)

El chat ya responde. Ahora hacemos dos cosas: que cada respuesta diga **de dónde salió**, y que, si no hay nada relevante, rechace **sin siquiera llamar al LLM**.

## Qué vas a aprender

- A hacer **verificables** las respuestas: cada una dice de qué archivo y sección salió.
- A rechazar de forma **determinística**: si nada es relevante, el LLM ni se llama.
- Por qué un LLM chico en CPU **no es determinístico**, aunque uses `temperature=0` y semilla fija.

---

## Pieza 1 de 6: citas que no inventa el LLM

Podríamos pedirle al LLM que cite sus fuentes. Pero un modelo de 3B inventa o deforma las etiquetas con facilidad.

Por eso **las citas salen de los datos, no del texto del LLM**: citamos los chunks que le pasamos, sin repetir y ordenados por score. Salen de las columnas `file` y `section`, así que no pueden estar inventadas.

```
No, nunca usó Kubernetes en producción. [...]

Sources:
  - experience/northwind-payments.md § Senior Backend Engineer > Infrastructure
```

Si el LLM rechaza, no hay citas: no tiene sentido mostrar fuentes de un "no tengo esa información".

## Pieza 2 de 6: el corte

```
pregunta ──► búsqueda ──► ¿el top-1 llega al umbral?
                              │
                    no ───────┴─────── sí
                    │                   │
          rechazo fijo,           solo los chunks que llegan
          sin llamar al LLM       van al LLM, y esos son las citas
```

- Si **ningún** chunk llega al umbral → rechazo fijo, y el LLM **no se llama**.
- Si alguno llega → **solo los que llegan** van al LLM. Los demás se descartan.

## Pieza 3 de 6: por qué rechazar antes del LLM

Rechazar sin llamar al LLM tiene tres ventajas ([ADR-0006](../../docs/adr/0006-relevance-gate-before-llm.md)):

1. es **determinístico**: la misma pregunta siempre da el mismo rechazo;
2. es **gratis**: no hay que esperar 10 segundos de CPU (ni pagar tokens en la nube);
3. **no se puede convencer** con un prompt ingenioso. Un "ignorá tus reglas" no pasa el corte porque no se parece a nada del CV.

## Pieza 4 de 6: dónde vive el umbral

El umbral está en `config/models.yaml`, **uno por modelo de embeddings**, porque cada modelo tiene su propio rango de scores (paso 1):

```yaml
embedding_models:
  bge-m3:
    dimension: 1024
    relevance_threshold: 0.42
```

En este paso arrancamos con **0.45**, a ojo: las preguntas con respuesta del paso 2 daban entre 0.51 y 0.65, y la del fútbol, 0.41. El paso 5 lo calibró con datos y quedó en **0.42**.

Para probar otro valor sin editar el archivo:

```bash
RELEVANCE_THRESHOLD=0.5 make ask Q="..."
```

O fijo para vos, con una línea `RELEVANCE_THRESHOLD=0.40` en tu `.env`.

## Pieza 5 de 6: ¿en qué idioma rechazar sin LLM?

Si no llamamos al LLM, nadie sabe en qué idioma vino la pregunta. `detect_language()` (en `language.py`) es un detector chiquito:

- mira signos y letras del español (`¿`, `¡`, `ñ`, acentos);
- cuenta palabras frecuentes de cada idioma ("qué", "tiene" contra "what", "has").

Si no está seguro (por ejemplo, con "Kubernetes?"), el rechazo sale en los dos idiomas:

```
No tengo esa información. / I don't have that information.
```

## Pieza 6 de 6: `DEBUG=1` ahora muestra el corte

```bash
make ask DEBUG=1 Q="¿Usó Kubernetes?"
```

```
── retrieved (threshold 0.45; ✓ = sent to the LLM) ──
  ✓ 0.514  experience/northwind-payments.md § Senior Backend Engineer > Infrastructure
    0.431  profile.md § Summary
    ...
── answer (10.4s, LLM called) ──
No, nunca ha utilizado Kubernetes en producción. [...]

Sources:
  - experience/northwind-payments.md § Senior Backend Engineer > Infrastructure
```

El ✓ marca qué chunks pasaron el corte y llegaron al LLM. Y abajo te dice si el LLM se llamó o no.

| Archivo | Qué cambió |
|---------|------------|
| `src/talk_to_my_cv/rag.py` | `answer()` aplica el corte y devuelve `refused`, `citations`, `retrieved` y `context`. |
| `src/talk_to_my_cv/language.py` | `detect_language()`: `"es"`, `"en"` o `None`. |
| `src/talk_to_my_cv/embeddings.py` | `relevance_threshold(model)`: lee `config/models.yaml`; `RELEVANCE_THRESHOLD` lo pisa. |
| `src/talk_to_my_cv/cli.py` | Muestra las fuentes, y con `DEBUG=1`, el corte. |

---

## Cómo comprobar que anda

```bash
make check-04
```

Comprueba:
- la pregunta de Lumen cita `Project Lumen`;
- la pregunta de stack cita `skills.md`;
- la del fútbol se rechaza **sin llamar al LLM**, comprobado con un **espía** (un envoltorio sobre el modelo real que anota si lo llamaron);
- una pregunta en español recibe respuesta en español.

### Lo que nos costó: el idioma, y un LLM que no es determinístico

El test de idioma falló la primera vez. "¿Cuánto aceleró Project Lumen la conciliación?" recibió:

```
Project Lumen accelerated the nightly reconciliation run from 9 hours to 14 minutes.
```

Al repetirla con **la misma entrada, `temperature=0` y semilla fija**, salió en español. Ollama en CPU **no es determinístico**: el estado de su caché y el orden de las operaciones cambian el resultado. Por eso **una sola corrida no prueba nada**.

Para medirlo, corrimos 3 preguntas en español por proceso nuevo, tres veces:

| Prompt | Respuestas en español |
|--------|----------------------:|
| El original ("answer in the same language as the question") | 7 de 9 |
| + al final: "The question is in Spanish. Write your whole answer in Spanish, even if the CONTEXT is in another language." | **9 de 9** |

Un modelo chico tiende a contestar en el idioma del contexto, y nuestro contexto está en inglés. Como `detect_language()` ya sabe el idioma de la pregunta, se lo decimos explícitamente y **al final** del prompt, donde más pesa. Es una mejora medida, no una garantía: 9 de 9 es una muestra chica.

## Para jugar

1. **La trampa de JavaScript, ahora con citas.** Probá `make ask DEBUG=1 Q="Has she worked with JavaScript?"`:

   ```
   ── retrieved (threshold 0.45; ✓ = sent to the LLM) ──
     ✓ 0.499  profile.md § Summary
     ✓ 0.492  experience/brightcart.md § Backend Developer
     ✓ 0.469  profile.md § Valentina Ríos
     ✓ 0.456  experience/northwind-payments.md § Senior Backend Engineer > Infrastructure
       0.449  profile.md § Contact
   ── answer (3.3s, LLM called) ──
   No

   Sources:
     - profile.md § Summary
     ...
   ```

   Es peor que en el paso 3: la alucinación ("No", cuando el CV no dice nada de JavaScript) ahora **viene con 4 fuentes** y parece respaldada.

   > **Una cita no es una garantía.** Citamos lo que el LLM **leyó**. Eso no prueba lo que el LLM **afirma**: ninguno de esos 4 chunks dice que no haya usado JavaScript. Una cita te dice dónde mirar, no que la respuesta sea verdad.

2. **Mové el umbral.** Probá la de JavaScript con `RELEVANCE_THRESHOLD=0.5` (rechaza sin llamar al LLM) y después "¿Usó Kubernetes?" con `RELEVANCE_THRESHOLD=0.52` (también rechaza, y esa sí tenía respuesta). Ese es el dilema que el paso 5 resuelve con datos.

3. **Probá el detector de idioma.** Preguntá una sola palabra fuera de tema, como "Pizza?". No pasa el corte, el detector no sabe el idioma, y el rechazo sale en los dos. Después probá "Netflix?": pasa el corte por poco (0.474, contra "Data and messaging"), así que llama al LLM, que rechaza solo y en inglés. Una palabra de tecnología se parece al CV aunque no tenga nada que ver.

---

## Preguntas frecuentes

<details>
<summary><b>¿Cómo se elige el valor del umbral?</b></summary>

No a ojo: se mide. Armás preguntas, anotás cuáles tienen respuesta y cuáles hay que rechazar, probás muchos umbrales y te quedás con el que más acierta. Es el paso 5. Y el 0.42 se calibró para el CV de ejemplo: con tu CV puede hacer falta otro valor. Una pregunta perfectamente válida puede quedar en 0.416 y rechazarse por poco.
</details>

<details>
<summary><b>¿Y si tuviera un millón de CVs mezclados (cocineros, bomberos, developers)?</b></summary>

El corte solo deja de servir, por dos razones:

1. **Siempre hay algo parecido.** Si preguntás "¿Valentina sabe cocinar?", entre un millón de CVs hay un cocinero con un chunk de 0.80. Pasa el corte, pero es de otra persona. Hay que **filtrar por persona primero** (con la metadata) y recién después buscar y cortar.
2. **Un solo número no sirve para todos.** CVs de rubros distintos dan scores distintos.

En la industria se suman umbrales por tipo de documento, un **reranker** (un segundo modelo, más lento y preciso, que relee los mejores 20 o 50 y da un score más confiable) y verificaciones antes de responder (paso 7). El umbral solo funciona bien para un documento chico y homogéneo, como un CV.
</details>

---

## ✋ Repaso

**1. ¿Por qué las citas no las escribe el LLM?**

<details><summary>Ver respuesta</summary>

Porque un modelo chico inventa o deforma etiquetas. Las citas salen de las columnas `file` y `section` de los chunks que se le pasaron: no pueden ser inventadas.
</details>

**2. ¿Qué tres ventajas tiene rechazar antes de llamar al LLM?**

<details><summary>Ver respuesta</summary>

Es determinístico (siempre el mismo rechazo), es gratis (no gasta CPU ni tokens) y no se puede convencer con un prompt ingenioso.
</details>

**3. Una respuesta trae 4 citas. ¿Eso prueba que es verdad?**

<details><summary>Ver respuesta</summary>

No. Las citas dicen qué leyó el LLM, no que lo que afirma esté en esos chunks. La trampa de JavaScript responde "No" con 4 citas, y ninguna dice nada de JavaScript.
</details>

**4. 🧪 Probalo:** `RELEVANCE_THRESHOLD=0.52 make ask DEBUG=1 Q="¿Usó Kubernetes?"`. ¿Qué pasa y por qué es un problema?

<details><summary>Ver respuesta</summary>

Rechaza sin llamar al LLM, porque el mejor chunk da 0.514. Pero esa pregunta tenía respuesta ("no en producción"). Subir el umbral rechaza basura, pero también preguntas buenas.
</details>

**5. Misma pregunta, `temperature=0`, semilla fija: una vez en inglés y otra en español. ¿Es un bug?**

<details><summary>Ver respuesta</summary>

No: Ollama en CPU no es 100% determinístico. Por eso una sola corrida no prueba nada, los tests nunca comparan texto exacto y la evaluación del paso 5 mide sobre muchas preguntas.
</details>

---

[← Paso 3](../03-first-rag/README.es.md) · [Índice](../../README.es.md) · [Siguiente: Paso 5, evaluación →](../05-evaluation/README.es.md)
