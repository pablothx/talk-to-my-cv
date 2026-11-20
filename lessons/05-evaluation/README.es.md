# Paso 5: Evaluación

🇬🇧 [Read in English](README.md)

Hasta acá probábamos "a mano": tres preguntas, parece que anda. En este paso medimos el chat con **números**, sobre 20 preguntas, y usamos esos números para elegir el umbral. Es lo que separa un experimento de un sistema en el que se puede confiar.

## Qué vas a aprender

- A medir un RAG con números en lugar de "probé tres preguntas y anduvo".
- Qué miden **hit@k**, **MRR**, **refusal accuracy** y **answer accuracy**.
- A calibrar el umbral con datos, y por qué el mejor umbral "en los papeles" no es el mejor en la práctica.
- Qué es **sobreajustar** y por qué nuestros números son optimistas.

---

## Pieza 1: por qué medir

Un LLM no es determinístico, y cada cambio (el prompt, el umbral, el modelo, cómo se corta el CV) puede arreglar una pregunta y romper otra. Sin una medición:

- no sabés si un cambio mejoró o empeoró;
- te quedás con la última impresión ("ayer anduvo");
- no podés comparar dos opciones con argumentos.

Una **eval** es un examen fijo: siempre las mismas preguntas, con lo que se espera de cada una.

## Pieza 2: las preguntas

`eval/questions.yaml` tiene 20 preguntas sobre Valentina, 10 en inglés y 10 en español. Hay cuatro tipos:

| Tipo | Cuántas | Qué se espera |
|------|--------:|---------------|
| `answerable` | 7 | Que responda, cite la sección correcta e incluya los datos clave. |
| `planted` | 5 | Lo mismo, con datos imposibles de adivinar ("14 minutes", "Golden Pigeon"). Prueba que la respuesta sale del documento y no de la memoria del modelo. |
| `negation` | 1 | Que responda "no", citando la fuente. Ni rechazar ni afirmar. |
| `unanswerable` | 7 | Que rechace. Incluye fuera de tema, datos privados y prompt injection. |

Una pregunta se ve así:

```yaml
- id: planted-lumen
  type: planted
  lang: en
  question: How much did Project Lumen speed up reconciliation?
  expected_sources:
    - file: experience/northwind-payments.md
      section: Senior Backend Engineer > Project Lumen
  expected_answer: From 9 hours to 14 minutes.
  must_contain: ["14 minutes"]
```

Qué es cada campo:

| Campo | Qué es | ¿Lo usa el código? |
|---|---|---|
| `id` | Un nombre corto para encontrarla en los resultados. | Solo para mostrar. |
| `type` | Uno de los cuatro tipos de arriba. Decide si tiene que responder o rechazar. | Sí |
| `lang` | El idioma de la pregunta: `es` o `en`. | Sí, con `check_language`. |
| `question` | La pregunta, tal cual se le hace al chat. | Sí |
| `expected_sources` | El archivo y la sección donde está la respuesta, exactamente como los arma el chunker. | Sí: para hit@5 y MRR. |
| `expected_answer` | La respuesta correcta, en palabras. | **No.** Es para que la lea una persona. |
| `must_contain` | Los datos clave que tienen que aparecer en la respuesta. Todos, sin importar mayúsculas. | Sí: para answer accuracy. |
| `check_language` | Si es `true`, la respuesta tiene que estar en el idioma de `lang`. Lo tienen 3 preguntas. | Sí |
| `forbid_unsupported_no` | Si es `true`, un "no" es alucinación: el CV no dice nada, así que lo único correcto es rechazar. Lo tienen Azure y JavaScript. | Sí |
| `trap` | Marca una trampa a propósito (pieza 3). | Sí: se reporta aparte. |

¿Por qué `must_contain` y no comparar con `expected_answer`? Porque el LLM redacta distinto cada vez: "de 9 horas a 14 minutos" y "bajó a 14 minutes" son las dos correctas. Comparar el texto entero fallaría siempre. Se piden solo los datos que no se pueden adivinar.

## Pieza 3: las trampas

Tres preguntas están marcadas como **trampas**, las que venimos persiguiendo:

- **JavaScript:** el CV no lo menciona. Lo correcto es rechazar; un "No" es alucinación.
- **CRM:** el CV dice "HubSpot", nunca "CRM". La búsqueda no lo encuentra.
- **Kubernetes:** el CV dice que *no* lo usó en producción. Lo correcto es "no", con cita.

Fallan a propósito con búsqueda vectorial, así que se reportan aparte y no cuentan para los objetivos. Los pasos 6 y 7 muestran si se arreglan.

Un test valida el YAML en cada push: mínimos por tipo, los dos idiomas, y que cada fuente esperada exista de verdad en los chunks. Si alguien cambia un título del CV y rompe una pregunta, se entera.

## Pieza 4: las métricas de la búsqueda

Dos métricas miden **solo la búsqueda**, sin el LLM, sobre las preguntas que tienen respuesta:

**hit@5** (se lee "hit at five"): *hit* es "acierto" y *@5* es "mirando los primeros 5". Pregunta: ¿la sección correcta está entre los 5 chunks recuperados? Es sí o no por pregunta, y se promedia. 1.00 = siempre estuvo. Con hit@1 la pregunta sería "¿vino primero?".

**MRR** (*Mean Reciprocal Rank*, "rango recíproco promedio"): *rank* es el **puesto** en que vino el chunk correcto, *reciprocal* es el inverso (1 dividido el puesto) y *mean* es el promedio de todas las preguntas. Pregunta: ¿qué tan arriba vino?

| Posición del chunk correcto | Vale |
|---|---:|
| 1.º | 1 |
| 2.º | 0.5 |
| 3.º | 0.33 |
| no aparece | 0 |

Se promedia. Un MRR de 0.82 quiere decir que el correcto suele estar primero, y a veces segundo.

Un ejemplo con tres preguntas:

| Pregunta | Puesto del correcto | hit@5 | 1 / puesto |
|---|---:|:-:|---:|
| Lumen | 1.º | ✅ | 1.00 |
| Stack | 2.º | ✅ | 0.50 |
| Charla | 4.º | ✅ | 0.25 |
| **Resultado** | | **3/3 = 1.00** | **(1 + 0.5 + 0.25) / 3 = 0.58** |

hit@5 dice "lo encontró siempre"; MRR agrega "pero no siempre arriba".

No son inventos nuestros: son métricas clásicas de *information retrieval* (la disciplina de los buscadores). MRR viene de las competencias TREC de búsqueda de respuestas, de fines de los 90; hit@k también se llama *hit rate*, *recall@k* o *top-k accuracy*. Frameworks de RAG como LlamaIndex las traen de fábrica. Lo nuestro es solo la implementación.

## Pieza 5: las métricas del sistema completo

Dos métricas miden **todo**, con el LLM, sobre las 17 preguntas que no son trampa (las 3 trampas se reportan aparte):

**refusal accuracy:** ¿rechazó cuando debía, y respondió cuando debía? Un rechazo de más y una respuesta de más cuentan igual como error.

**answer accuracy:** ¿la respuesta es correcta del todo? No rechaza si tenía respuesta, dice "no" si es negación, incluye los datos clave (`must_contain`) y respeta el idioma.

La pareja importa: si la búsqueda anda (hit@5 = 1.00) pero el sistema falla, el problema está después de la búsqueda.

## Pieza 6: calibrar el umbral, primero sin LLM

`make eval-sweep` hace **una búsqueda por pregunta, sin LLM**, y prueba todos los umbrales entre 0.35 y 0.65. Para cada uno calcula cuántas preguntas sin respuesta rechazaría y cuántas con respuesta dejaría pasar. Tarda 9 segundos.

![Barrido del umbral](../../eval/results/threshold-sweep_bge-m3.png)

Si las dos curvas se separaran limpias, habría un umbral perfecto. No: hay preguntas con respuesta que puntúan **por debajo** de preguntas sin respuesta.

| Pregunta | Top-1 | ¿Tiene respuesta? |
|----------|------:|:-----------------:|
| ¿Trabajó con Azure? | 0.483 | no |
| ¿Dónde trabaja actualmente y qué rol tiene? | 0.466 | sí |
| ¿Cuánto cobra por mes? | 0.444 | no |
| How big is the team she leads? | 0.431 | sí |
| What did she study? | 0.414 | sí |

Ningún número separa los "sí" de los "no".

## Pieza 7: el mejor en los papeles no es el mejor

Mirando solo el corte, el mejor umbral es **0.49**: rechaza todas las preguntas sin respuesta, pero también 3 que sí tenían. Corrimos la eval completa, con el LLM, en los dos candidatos:

| Umbral | refusal accuracy | answer accuracy | hit@5 | MRR |
|---|---:|---:|---:|---:|
| 0.49 (el mejor "solo corte") | 0.82 | 0.76 | 1.00 | 0.82 |
| **0.42** | **0.88** | **0.82** | 1.00 | 0.82 |

**0.42 es mejor,** porque el corte no es el único que rechaza: con 0.42, "¿Cuánto cobra?" y "¿Trabajó con Azure?" pasan el corte, y **el LLM las rechaza bien**. Con 0.49, el corte rechaza preguntas buenas que el LLM nunca llega a ver.

> **Un rechazo de más no tiene arreglo; una respuesta de más todavía la puede rechazar el LLM.**

Por eso el barrido solo **propone** candidatos y la eval completa **decide** ([ADR-0009](../../docs/adr/0009-top1-gate-does-not-separate-alone.md)). Quedó `relevance_threshold: 0.42`.

## Pieza 8: no llegamos al objetivo, y está bien decirlo

El objetivo era refusal accuracy ≥ 0.9. Llegamos a **0.88**.

No lo vamos a "arreglar" tocando el CV o el prompt hasta que pase, porque eso sería hacer trampa con el examen (pieza 9). El paso 7 agrega una verificación después de la búsqueda.

## Pieza 9: el sobreajuste

Calibramos el umbral **con las mismas 20 preguntas** con las que después reportamos los resultados. Eso se llama **sobreajustar** (*overfitting*): elegimos lo que mejor funciona con *estas* preguntas, y nada garantiza que funcione igual con preguntas nuevas.

Es como estudiar con el examen ya resuelto: te va bien en ese examen, no necesariamente en otro.

Con 20 preguntas, mover una sola cambia las métricas un 5%. Por eso 0.88 es un número **optimista**. Lo correcto es separar las preguntas en dos grupos: uno para calibrar y otro, que nunca miraste, para reportar. Con 20 no alcanza para separar; con 100, sí.

Otra imagen: tirás un dardo, y **después** dibujás el blanco alrededor de donde cayó. El pleno es real, pero no prueba puntería.

Tres matices:

- **Más preguntas ayudan,** pero no reemplazan la separación: ajustar con 500 y reportar con las mismas 500 sigue siendo optimista, solo que menos.
- **El riesgo crece con cada perilla.** Acá ajustamos una sola (el umbral). Si además ajustás el prompt, `k`, los pesos del híbrido y el tamaño de chunk mirando las mismas preguntas, cada una suma un poco de "blanco dibujado".
- **Ni 500 preguntas sobre Valentina calibran tu CV.** Otro documento tiene otro estilo y otros scores. Con tu CV, escribí algunas preguntas propias y volvé a correr `make eval-sweep`.

## Pieza 10: dónde quedan los resultados

Cada corrida escribe dos archivos en `eval/results/`, y **se commitean**:

```
eval/results/2026-11-17_pgvector_vector_bge-m3.md     ← para leer
eval/results/2026-11-17_pgvector_vector_bge-m3.json   ← para comparar con código
```

El nombre dice fecha, store, modo y modelo. Así queda la historia: qué cambió y cuánto movió los números. Lo crudo (cada respuesta completa) va a `raw/`, que no se commitea.

La eval siempre corre contra el CV de ejemplo, en su propio esquema de Postgres (`eval`), sin importar tu `KB_DIR`: las preguntas son sobre Valentina, no sobre vos.

| Archivo | Qué hace |
|---------|----------|
| `src/talk_to_my_cv/evaluation.py` | Métricas, `grade()` (la nota de cada pregunta), `run_eval()`, reportes y `sweep()`. |
| `src/talk_to_my_cv/sweep_plot.py` | El gráfico del barrido. |
| `eval/questions.yaml` | Las 20 preguntas, cada trampa explicada en un comentario. |

---

## Cómo comprobar que anda

```bash
make check-05
make eval-sweep                      # 9 s, sin LLM
make eval                            # ~1.5 min con qwen2.5:3b en CPU
make eval THRESHOLD=0.49             # otro candidato
make eval MODE=hybrid                # pgvector no lo soporta: sale "skipped"
```

### Lo que nos costó

**1. Un bug que solo la eval podía encontrar.** "¿Dónde trabaja actualmente?" fallaba con "no se especifica su lugar de trabajo". El chunk no contiene la palabra "Northwind": la empresa solo está en el título del documento, que iba en el texto **embebido** pero no en el que recibía el **LLM**. La búsqueda lo encontraba y el LLM no podía leerlo. Ahora el LLM recibe lo mismo que vio el embedding. Ningún test anterior lo habría detectado.

**2. La instrucción de idioma traduce nombres propios.** "¿Dio alguna charla?" respondió con la charla "Tu libro de transacciones es un flujo". El título real es "Your ledger is a stream". Es efecto de la instrucción de idioma del paso 4. **No lo arreglamos a propósito**: ajustar el prompt mirando esta pregunta sería sobreajustar.

**3. El evaluador también se equivoca.** Para JavaScript, el modelo respondió "No, the CONTEXT does not mention any experience with JavaScript.". Está mal (no es el rechazo fijo), pero nuestra regla la clasifica como alucinación, y no lo es: admite que no sabe. Un evaluador basado en reglas tiene límites.

**4. Una corrida no alcanza.** Ollama en CPU no es determinístico (paso 4). Antes de creerle a una diferencia chica entre dos corridas, repetila.

## Para jugar

1. **Probá el sobreajuste vos.** Escribí 5 preguntas nuevas sobre Valentina en `eval/questions.yaml` (3 con respuesta y 2 sin), sin mirar los scores antes. Corré `make eval-sweep` y `make eval`. ¿Se sostienen el umbral y las métricas?
2. **Arreglá la trampa de CRM.** Cambiá "HubSpot" por "HubSpot (CRM)" en `kb.example/experience/northwind-payments.md`, re-ingestá y corré la eval. ¿Es trampa? Sí, si lo hacés mirando la pregunta; no, si es una regla general para escribir CVs ("Herramienta (categoría)").
3. **Probá con otro modelo.** Cambiá `LLM_MODEL` (por ejemplo `qwen2.5:7b`, si te da la RAM) y compará los resúmenes de `eval/results/`.

---

## Preguntas frecuentes

<details>
<summary><b>¿Puedo evaluar con mi propio CV?</b></summary>

Hoy la eval corre siempre sobre el CV de ejemplo, porque las preguntas son sobre Valentina. Para el tuyo, tendrías que escribir tu propio archivo de preguntas (con secciones que existan en tus chunks) y apuntar la eval a tu `kb/`. Es la mejor forma de calibrar el umbral para tu CV.
</details>

<details>
<summary><b>¿Por qué no usar otro LLM como juez de las respuestas?</b></summary>

Se puede, y en la industria es común ("LLM-as-judge"). Pero con un modelo de 3B el juez se equivoca mucho (lo medimos en el paso 7). Las reglas fijas (`must_contain`, el rechazo exacto, el idioma) son más limitadas pero repetibles. Con un modelo grande en la nube, un juez valdría la pena.
</details>

---

## ✋ Repaso

**1. hit@5 = 1.00 y answer accuracy = 0.82. ¿Dónde están los errores?**

<details><summary>Ver respuesta</summary>

Después de la búsqueda: el chunk correcto siempre estuvo entre los 5, así que falla el corte (rechaza de más) o el LLM (responde mal con buen contexto).
</details>

**2. El chunk correcto aparece segundo en una pregunta y primero en otra. ¿Cuánto da el MRR de esas dos?**

<details><summary>Ver respuesta</summary>

(0.5 + 1) / 2 = 0.75.
</details>

**3. ¿Por qué ganó 0.42 si el barrido decía que el mejor era 0.49?**

<details><summary>Ver respuesta</summary>

Porque el barrido solo mira el corte, y el LLM también rechaza. Con 0.42 pasan algunas preguntas sin respuesta, pero el LLM las rechaza bien; con 0.49 se pierden preguntas buenas que nadie puede recuperar.
</details>

**4. ¿Qué es sobreajustar, en una frase?**

<details><summary>Ver respuesta</summary>

Elegir lo que mejor funciona con las mismas preguntas con las que después medís: los números salen optimistas y nada garantiza que se repitan con preguntas nuevas.
</details>

**5. 🧪 Probalo:** corré `make eval-sweep` y abrí `eval/results/threshold-sweep_bge-m3.png`. ¿Ves algún umbral que separe perfecto?

<details><summary>Ver respuesta</summary>

No: las curvas se superponen. Hay preguntas con respuesta que puntúan menos que preguntas sin respuesta. Ningún umbral solo las separa.
</details>

---

[← Paso 4](../04-citations-threshold/README.es.md) · [Índice](../../README.es.md) · [Siguiente: Paso 6, búsqueda híbrida →](../06-hybrid-search/README.es.md)
