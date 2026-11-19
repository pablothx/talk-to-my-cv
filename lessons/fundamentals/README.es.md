# Antes de empezar: los fundamentos

🇬🇧 [Read in English](README.md)

Esta lección no tiene código. Son las ideas que necesitás para que todo lo demás tenga sentido, explicadas de a una pieza por vez y desde cero. Si nunca tocaste IA, empezá acá. Si ya sabés qué es un embedding, podés saltar al [paso 0](../00-setup/README.es.md).

Tiempo: unos 30 minutos.

## Qué vas a aprender

- Qué es un LLM, por qué "alucina" y qué lo hace más o menos inteligente.
- Qué es **RAG** y qué problema resuelve.
- Qué son los **chunks**, los **embeddings** y la **similitud coseno**, sin fórmulas difíciles.
- Cómo encuentra un RAG los pedazos correctos, y por qué hace falta un **corte**.

---

## Pieza 1: un LLM no sabe nada de vos

Un LLM (ChatGPT, Claude, el `qwen2.5:3b` que usamos acá) aprendió leyendo internet. Sabe mucho del mundo, pero **no sabe nada de vos**.

Si le preguntás "¿en qué empresas trabajó Valentina Ríos?", pueden pasar dos cosas:

- te dice que no sabe, o
- **inventa** una respuesta que suena perfecta.

Lo segundo es lo peligroso, porque no te avisa que está inventando.

## Pieza 2: alucinar no es mentir

A eso de inventar se lo llama **alucinar**. Pero ojo: **alucinar no es mentir**.

- **Mentir** es decir algo falso *sabiendo* que es falso.
- **Alucinar** es decir algo falso *sin saberlo*. El modelo no tiene intención de engañar.

¿Por qué pasa? Porque un LLM, por dentro, hace una sola cosa: **predice la palabra más probable que sigue**, una tras otra.

Si le preguntás dónde trabajó alguien que no conoce, no busca en una base de datos: arma la respuesta que *suena* más probable. "Trabajó en Globant como..." suena perfecto para un ingeniero argentino, pero sale de la estadística, no de un dato.

> **Lo peligroso:** la respuesta inventada suena igual de segura que la verdadera. No hay ningún tono que las distinga.

## Pieza 3: qué son los parámetros

Un LLM es, en el fondo, una función gigante. Pensá en una simple:

```
y = a * x + b
```

`x` es la entrada e `y` la salida. **`a` y `b` son los parámetros**: los números que definen cómo la función transforma la entrada en salida.

Un LLM es lo mismo, pero con **miles de millones** de parámetros, organizados en matrices enormes:

- **Entrada:** tu pregunta, convertida en números.
- **Salida:** la probabilidad de cada palabra posible como la próxima.
- **Los parámetros:** deciden qué palabra sale más probable.

¿De dónde salen esos números? **Del entrenamiento:**

1. Arrancan al azar, y el modelo dice basura.
2. Le das un texto real ("El cielo es...") y le pedís que prediga la próxima palabra.
3. Si dijo "pizza" y era "azul", se ajustan un poquito los números para que "azul" sea más probable.
4. Repetís eso billones de veces, con todo internet.

Nadie escribió esos números a mano. Cuando hacés `ollama pull qwen2.5:3b` bajás un archivo de unos 2 GB: **ese archivo son los parámetros**. El modelo *es* ese archivo.

## Pieza 4: modelos chicos y modelos grandes

Todos los LLM funcionan igual por dentro: misma arquitectura (*transformer*) y mismo mecanismo (predecir la próxima palabra). Lo que cambia es:

1. **El tamaño.** El "3b" de `qwen2.5:3b` son 3 mil millones de parámetros. Los modelos grandes tienen cientos de miles de millones.
2. **Con qué se entrenó.** Más y mejor texto (libros, código, idiomas) da un modelo que sabe más.
3. **Cómo se lo "educó" después.** Se lo entrena con ejemplos de cómo comportarse: seguir instrucciones, decir "no sé", pensar paso a paso antes de responder.

Es como el cerebro de un chico y el de un adulto: mismas neuronas, mismo mecanismo, pero el adulto razona cosas que el chico no puede. Y algunas habilidades **aparecen solas** al crecer: nadie le programó a un modelo grande "cómo razonar".

| | Modelo chico (`qwen2.5:3b`) | Modelo grande |
|---|---|---|
| Sigue la consigna "respondé solo con esto" | A veces se le escapa | Casi siempre |
| Alucina | Más | Menos (pero no cero) |
| Corre en | Tu CPU, gratis | Servidores con GPU, pagando |
| Tiempo por respuesta | 10 a 30 segundos en CPU | Segundos |

Este tutorial usa el chico porque corre en cualquier compu y es gratis. Como se equivoca más, nos obliga a construir controles de verdad. **Si el sistema anda con un modelo chico, con uno grande anda mejor.**

## Pieza 5: RAG, un examen a libro abierto

La solución a "el modelo no sabe de vos" es simple: **antes de preguntarle al LLM, buscamos en tus documentos los pedazos que tienen que ver con la pregunta**, y se los pasamos con una consigna: *"respondé solo con esto"*.

Esa técnica se llama **RAG** (*Retrieval-Augmented Generation*):

- **Retrieval:** buscar los pedazos.
- **Augmented:** sumarlos a la pregunta.
- **Generation:** que el LLM escriba la respuesta.

Es como darle a alguien un examen a libro abierto, pero con la página ya marcada.

## Pieza 6: los chunks

Antes de poder buscar, cortamos el CV en pedazos. A cada pedazo se lo llama **chunk**. El CV de ejemplo de este tutorial (Valentina Ríos, una persona ficticia) queda en 19 chunks:

```
profile.md                       § Summary
profile.md                       § Languages
skills.md                        § Cloud
experience/northwind-payments.md § Senior Backend Engineer > Project Lumen
...
```

¿Por qué cortar, y no pasarle el CV entero?

1. **Precisión.** Un pedazo chico habla de una cosa. Un CV entero habla de todo a la vez, y su "significado" queda borroso.
2. **Citas.** Si la respuesta salió de "Project Lumen", el sistema te puede decir *de dónde* la sacó.
3. **Escala.** Un CV entra entero en un prompt, pero 500 manuales no. Hay que elegir.

Cortar **cubre todo el documento**: ninguna línea queda afuera. Pero ojo: **guardar todo no es usar todo**. En cada pregunta, el LLM ve solo los 5 chunks más parecidos. Si la respuesta está repartida en 15 chunks (por ejemplo, "¿cuántos años trabajó en total?"), puede contestar mal. Es una limitación propia de RAG.

## Pieza 7: buscar por significado, no por palabras

¿Cómo sabe el sistema qué chunks "tienen que ver" con la pregunta? La forma obvia es buscar palabras, como un Ctrl+F.

- Preguntás: *"¿Trabajó con la nube?"*
- El CV dice: *"Diseñé arquitecturas en AWS usando Lambda"*.

"Nube" no aparece en esa frase, así que Ctrl+F **no la encuentra**. Pero cualquiera sabe que AWS *es* la nube. Y si preguntás en español y el CV está en inglés, casi ninguna palabra coincide.

La solución es buscar por **significado**. Para eso, cada texto se convierte en una lista de números que representa lo que quiere decir. A esa lista se la llama **embedding**.

## Pieza 8: qué es un embedding

Un embedding es **una lista de números** (también se le dice *vector*). Para entenderlo, un ejemplo de juguete: describí cada texto con **3 puntajes** de 0 a 1.

| Texto | ¿Tecnología? | ¿Comida? | ¿Deporte? | El vector |
|---|---:|---:|---:|---|
| "trabajó con AWS" | 0.9 | 0.0 | 0.1 | `[0.9, 0.0, 0.1]` |
| "usó la nube de Amazon" | 0.8 | 0.1 | 0.0 | `[0.8, 0.1, 0.0]` |
| "receta de empanadas" | 0.0 | 0.9 | 0.1 | `[0.0, 0.9, 0.1]` |

Las dos primeras listas **se parecen** (alto en tecnología), así que significan algo parecido. La tercera es distinta.

En la realidad hay dos diferencias con el juguete:

1. No son 3 números: el modelo que usamos (`bge-m3`) da **1024**.
2. **Los números no tienen nombre.** No hay una posición que sea "tecnología": el modelo aprendió solo qué medir en cada lugar.

Por eso, si mirás un embedding, vas a ver `[-0.028, 0.012, -0.032, ...]` y no vas a entender nada. **Un embedding solo no significa nada; solo sirve para compararlo con otro.** Es como una coordenada GPS: `-34.6, -58.4` no te dice nada hasta que la comparás con otra.

## Pieza 9: comparar dos embeddings (el coseno)

Imaginá cada embedding como una **flecha** que sale del centro:

```
          ↑  "trabajó con la nube"
         ↗   "arquitecturas en AWS"
        /
  ─────●──────────→  "receta de empanadas"
```

"Nube" y "AWS" apuntan casi para el mismo lado; "empanadas", para otro. Para comparar, medimos el ángulo entre las flechas con la **similitud coseno**:

| Coseno | Significa |
|---|---|
| **1** | Misma dirección: mismo significado |
| **0** | Perpendiculares: nada que ver |
| **-1** | Opuestas (con texto casi no pasa) |

¿Por qué el coseno y no el seno? Porque con el coseno **más alto = más parecido**. El seno da 0 tanto para "idénticos" como para "opuestos", así que no los distingue.

Y se calcula fácil, sin medir ningún ángulo: multiplicás las dos listas posición por posición, sumás, y dividís por el largo de cada flecha. Son solo sumas y multiplicaciones.

Con 1024 números es lo mismo, solo que no lo podemos dibujar.

## Pieza 10: dos modelos distintos

En este proyecto hay **dos modelos**, y cada uno hace una sola cosa:

| Modelo | Qué hace | Entra | Sale |
|---|---|---|---|
| `bge-m3` | Convierte texto en números | "trabajó con AWS" | 1024 números |
| `qwen2.5:3b` | Escribe la respuesta | pregunta + chunks | "Valentina trabajó con AWS en..." |

El primero no sabe escribir; el segundo no sabe buscar. Los dos corren en **Ollama**, un programa que sirve modelos en tu máquina.

Elegimos `bge-m3` porque es **multilingüe**: entiende que "¿qué idiomas habla?" y "Languages: Spanish, English" significan lo mismo. En la nube hay otros (en AWS, Amazon Titan o Cohere), y cada uno da una cantidad distinta de números.

> **Una regla de oro:** la pregunta y los chunks tienen que pasar por **el mismo** modelo de embeddings. Cada modelo tiene su propio "idioma de números", y comparar vectores de dos modelos distintos es como comparar coordenadas GPS con direcciones postales.

## Pieza 11: la búsqueda

Cuando hacés una pregunta:

1. La pregunta se convierte en un embedding.
2. Se calcula el coseno contra **cada** chunk guardado.
3. Se ordenan de mayor a menor y se quedan los **5 primeros** (el *top-5*).

Esto es real, contra el CV de Valentina:

```
How much did Project Lumen speed up reconciliation?
  0.65  experience/northwind-payments.md § Senior Backend Engineer > Project Lumen   ← ✓
  0.33  experience/northwind-payments.md § Senior Backend Engineer
  0.32  experience/brightcart.md § Backend Developer > Hackathon
  0.30  experience/brightcart.md § Backend Developer > Database work
  0.27  profile.md § Summary

¿Sabe cocinar empanadas?
  0.39  skills.md § Languages
  0.38  profile.md § Languages
  0.37  skills.md § Cloud
  0.34  skills.md § Data and messaging
  0.33  profile.md § Summary
```

Tres cosas para mirar:

1. **Funciona:** para Project Lumen, el chunk correcto sale primero y lejos del resto.
2. **Los números son bajos.** No esperes 0.9: entre una pregunta corta y un pedazo de CV, 0.6 ya es "muy relacionado".
3. **La búsqueda siempre trae 5, aunque no tengan nada que ver.** El CV no habla de empanadas y aun así devolvió 5 chunks. La búsqueda no sabe decir "no hay nada": solo sabe decir "esto es lo *menos lejano*".

## Pieza 12: el corte

El punto 3 es un problema: si esos 5 chunks de "empanadas" llegan al LLM, puede inventar algo. Por eso hay un **corte** (el *umbral de relevancia*):

> Si el chunk más parecido no llega a **0.42**, el sistema responde "No tengo esa información" **sin llamar al LLM**.

Para empanadas, el mejor saca 0.39: se rechaza. Para Project Lumen, 0.65: pasa.

El corte es un **compromiso**:

- Si lo subís, rechaza más basura, pero también más preguntas buenas.
- Si lo bajás, responde más, pero deja pasar más basura.

**No existe un número perfecto: hay que medirlo con preguntas reales.** Eso lo hacemos en el paso 5. Y el 0.42 se calibró para el CV de ejemplo: con tu CV puede hacer falta otro valor.

## El mapa de lo que viene

```
INGESTA (una vez)
  tu CV ──► cortar en chunks ──► embeddings (bge-m3) ──► Postgres
                 paso 2               paso 1               paso 2

CADA PREGUNTA
  pregunta ──► embedding ──► top-5 ──► corte ──► LLM (qwen) ──► respuesta + citas
                 paso 1      paso 2    paso 4     paso 3           paso 4

  + medir todo (paso 5) · buscar también por palabras (paso 6)
  + verificar la respuesta (paso 7) · una página web (paso 8)
```

---

## Preguntas frecuentes

<details>
<summary><b>Si le cargo la Biblia y pregunto por "el profeta Marcos", pero mi Biblia no tiene ese libro, ¿qué contesta?</b></summary>

Depende de tres filtros, en orden:

1. **La búsqueda siempre trae algo:** los 5 pedazos que más se parecen a "profeta Marcos", seguramente sobre otros profetas.
2. **El corte:** en la Biblia hay mucho de profetas, así que lo más probable es que pase.
3. **El LLM con "respondé solo con esto":** acá está el riesgo. Un modelo grande *conoce* la Biblia de memoria. Puede portarse bien ("el texto no habla de un profeta Marcos"; hasta te puede corregir que Marcos fue evangelista, no profeta) o **filtrar lo que sabe** y contarte el Evangelio de Marcos como si viniera de tu texto. Un modelo chico lo hace mucho más.

Por eso existe el paso 7: antes de escribir la respuesta, el código revisa que los nombres por los que se pregunta ("Marcos") aparezcan literalmente en los pedazos recuperados. Si no aparecen, rechaza. Y una trampa extra: "Marcos" sí aparece en Hechos ("Juan Marcos"). Si ese pedazo viene en la búsqueda, el nombre está, y la respuesta va a hablar de *ese* Marcos.

Un modelo más grande alucina menos, pero no cero. Por eso el sistema no confía en el modelo: pone controles en código (el corte y la verificación) antes de dejarlo escribir.
</details>

<details>
<summary><b>Si algún día la IA supiera todo de todos, ¿RAG quedaría obsoleto?</b></summary>

Parcialmente. Hay cosas que ningún modelo puede saber desde su entrenamiento:

1. **Datos privados:** tu CV o los contratos de tu empresa nunca van a estar en el entrenamiento, y no querés que estén.
2. **Datos que cambian:** reentrenar un modelo cuesta millones; actualizar una fila en Postgres, un segundo.
3. **Citas:** en un banco o un hospital no alcanza "lo sé"; hace falta "lo dice este documento". Un modelo no puede señalar de dónde aprendió algo.
4. **Permisos:** con RAG filtrás qué documentos ve cada usuario. Lo que un modelo aprendió, lo sabe para todos.
5. **Olvidar:** borrar un dato de RAG es borrar una fila. De un modelo entrenado no se puede "despegar".

Lo que sí cambia: los modelos nuevos leen muchísimo texto de una vez, y un CV de 2 páginas ya entra entero en el prompt. Para documentos chicos, cortar y buscar hace menos falta. Para mucho volumen, sigue haciendo falta. La idea de fondo (darle al modelo los datos correctos al momento de la pregunta, y poder verificar de dónde salió la respuesta) no se vuelve obsoleta.
</details>

<details>
<summary><b>¿Los embeddings son siempre de 1024 números?</b></summary>

No, depende del modelo. `bge-m3` da 1024; Amazon Titan Text Embeddings V2 da 1024 por defecto (o 256 y 512 si los pedís); OpenAI `text-embedding-3-small` da 1536. Si cambiás de modelo, hay que volver a embeber todo. El paso 2 muestra cómo el proyecto te frena si te olvidás.
</details>

---

## ✋ Repaso

**1. ¿Por qué un LLM puede contestar algo falso con total seguridad?**

<details><summary>Ver respuesta</summary>

Porque no busca datos: predice la palabra más probable que sigue. Una respuesta inventada puede ser muy "probable" y sonar perfecta. No miente (no sabe que es falso): alucina.
</details>

**2. ¿Qué es lo que bajás cuando hacés `ollama pull qwen2.5:3b`?**

<details><summary>Ver respuesta</summary>

Los parámetros: unos 3 mil millones de números que salieron del entrenamiento. El modelo *es* ese archivo.
</details>

**3. ¿Qué significa cada número de un embedding?**

<details><summary>Ver respuesta</summary>

Nada, por sí solo. El significado está repartido entre todos los números, de una forma que nadie diseñó. Un embedding solo sirve para compararlo con otro.
</details>

**4. Preguntás algo que el CV no menciona. ¿Cuántos chunks trae la búsqueda?**

<details><summary>Ver respuesta</summary>

Cinco. La búsqueda siempre devuelve los 5 más parecidos, aunque no tengan nada que ver. Por eso hace falta el corte.
</details>

**5. ¿Qué pasa si embebés la pregunta con un modelo y los chunks con otro?**

<details><summary>Ver respuesta</summary>

Las búsquedas dan basura sin ningún error visible: cada modelo tiene su propio "idioma de números" y los vectores no son comparables.
</details>

**6. Si subís el umbral de 0.42 a 0.55, ¿qué ganás y qué perdés?**

<details><summary>Ver respuesta</summary>

Ganás: rechaza más preguntas sin respuesta. Perdés: también rechaza preguntas que sí tenían respuesta pero puntuaban entre 0.42 y 0.55. No hay número perfecto: se mide (paso 5).
</details>

---

[Índice](../../README.es.md) · [Siguiente: Paso 0, setup →](../00-setup/README.es.md)
