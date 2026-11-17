# Paso 4: Citas y umbral

🇬🇧 [Read in English](README.md)

## Qué vas a aprender

- A hacer **verificables** las respuestas: cada respuesta dice de qué archivo y sección salió.
- A rechazar de forma **determinística**: si nada es relevante, el LLM ni se llama.
- Por qué un LLM chico en CPU **no es determinístico**, aunque uses `temperature=0` y `seed`.

## El concepto

### Citas que no inventa el LLM

En el paso 3, cada chunk llegaba al prompt con su etiqueta `[archivo § sección]`. Podríamos pedirle al LLM que cite, pero un modelo de 3B parámetros inventa o deforma las etiquetas con facilidad. Por eso **las citas salen de la metadata, no del texto del LLM**: citamos los chunks que le pasamos, sin duplicados y ordenados por score.

```
No, nunca ha utilizado Kubernetes en producción. [...]

Sources:
  - experience/northwind-payments.md § Senior Backend Engineer > Infrastructure
```

Si el LLM rechaza, no hay citas: no tiene sentido mostrar fuentes de un "no tengo esa información".

### El umbral de relevancia

```
pregunta ──► búsqueda ──► ¿el top-1 supera el umbral?
                              │
                    no ───────┴─────── sí
                    │                   │
          rechazo fijo,           solo los chunks que lo superan
          sin llamar al LLM       van al LLM, y esos son las citas
```

Rechazar sin llamar al LLM tiene tres ventajas ([ADR-0006](../../docs/adr/0006-relevance-gate-before-llm.md)):

- es **determinístico**: la misma pregunta siempre da el mismo rechazo;
- es **gratis**: no hay que esperar 10 segundos de CPU;
- **no se puede convencer** con un prompt ingenioso.

El umbral vive en `config/models.yaml`, **uno por modelo de embeddings**: en el paso 1 vimos que cada modelo tiene su propio rango de scores. Para `bge-m3` empezamos con **0.45**, un valor provisorio que sale de lo medido en el paso 2: las preguntas con respuesta dieron entre 0.51 y 0.65, y la de fútbol, 0.41. El paso 5 lo calibra con datos. Para probar otro valor sin editar el archivo: `RELEVANCE_THRESHOLD=0.5 make ask Q="..."`.

### ¿En qué idioma rechazar sin LLM?

Si no llamamos al LLM, nadie sabe en qué idioma vino la pregunta. `detect_language()` es un detector chico: mira `¿`, `¡`, acentos, `ñ` y palabras frecuentes. Si no está segura (por ejemplo, con "Kubernetes?"), el rechazo sale en los dos idiomas:

```
No tengo esa información. / I don't have that information.
```

## El código

| Archivo | Qué cambió |
|---------|------------|
| `src/talk_to_my_cv/rag.py` | `answer()` aplica el umbral y devuelve `refused`, `citations`, `retrieved` y `context`. |
| `src/talk_to_my_cv/language.py` | `detect_language()`: `"es"`, `"en"` o `None`. |
| `src/talk_to_my_cv/embeddings.py` | `relevance_threshold(model)`: lee `config/models.yaml`; `RELEVANCE_THRESHOLD` lo pisa. |
| `src/talk_to_my_cv/cli.py` | Muestra las fuentes. Con `DEBUG=1`, también qué chunks pasaron el umbral (✓) y si se llamó al LLM. |

## Cómo comprobar que anda

```bash
make check-04
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

`make check-04` comprueba:
- la pregunta de Lumen cita `Project Lumen`;
- la pregunta de stack cita `skills.md`;
- la del fútbol se rechaza **sin llamar al LLM**, comprobado con un espía sobre el modelo real;
- una pregunta en español recibe respuesta en español.

### Lo que nos costó: el idioma, y un LLM que no es determinístico

El test de idioma falló la primera vez. La pregunta "¿Cuánto aceleró Project Lumen la conciliación?" recibió esta respuesta:

```
Project Lumen accelerated the nightly reconciliation run from 9 hours to 14 minutes.
```

Al repetirla con **la misma entrada, `temperature=0` y `seed` fijo**, salió en español. Ollama en CPU **no es determinístico**: el estado de su caché y el orden de las operaciones cambian el resultado. Por eso los tests de este proyecto no comparan textos exactos ([ADR-0008](../../docs/adr/0008-tests-against-nondeterministic-llms.md)), y por eso **una sola corrida no prueba nada**.

Para medirlo de verdad, corrimos el pipeline completo en procesos nuevos, 3 preguntas en español por proceso:

| Prompt | Respuestas en español |
|--------|----------------------:|
| El original ("answer in the same language as the question") | 7 de 9 |
| + al final: "The question is in Spanish. Write your whole answer in Spanish, even if the CONTEXT is in another language." | **9 de 9** |

Un modelo chico tiende a contestar en el idioma del contexto, y nuestro contexto está en inglés. Como `detect_language()` ya sabe el idioma de la pregunta, se lo decimos explícitamente y **al final** del prompt, donde más pesa. Con eso el test pasa de forma estable. Es una mejora medida, no una garantía: 9 de 9 es una muestra chica, y el paso 5 lo va a medir con todas las preguntas.

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

   Es peor que en el paso 3: la alucinación ("No", cuando la KB no dice nada sobre JavaScript) ahora **viene con 4 fuentes** y parece respaldada. Las citas dicen qué leyó el LLM, no que lo que dice sea verdad. Como vimos en el paso 2, el top-1 (0.499) está casi pegado al de Kubernetes (0.514), así que el umbral no puede separarlas. El paso 5 lo va a medir.

2. **Mové el umbral.** Probá la pregunta de JavaScript con `RELEVANCE_THRESHOLD=0.5` (rechaza sin llamar al LLM) y después "¿Usó Kubernetes?" con `RELEVANCE_THRESHOLD=0.52` (también rechaza, y esa sí tenía respuesta). Ese es el dilema que el paso 5 resuelve con datos.

3. **Probá el detector de idioma.** Preguntá una sola palabra fuera de tema, como "Pizza?" o "Messi?". No pasa el umbral, el detector no puede saber el idioma, y el rechazo sale en los dos. Después probá "Netflix?": pasa el umbral por poco (0.474, contra "Data and messaging"), así que sí llama al LLM, que rechaza solo y en inglés. Una palabra de tecnología se parece a la KB aunque no tenga nada que ver.
