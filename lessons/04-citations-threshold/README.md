# Step 4: Citations and threshold

🇪🇸 [Leer en español](README.es.md)

The chat answers now. In this step we do two things: every answer says **where it came from**, and if nothing is relevant, it refuses **without even calling the LLM**.

## What you'll learn

- How to make answers **checkable**: each one says which file and section it came from.
- How to refuse **deterministically**: if nothing is relevant, the LLM isn't called.
- Why a small LLM on a CPU **isn't deterministic**, even with `temperature=0` and a fixed seed.

---

## Piece 1 of 6: citations the LLM doesn't make up

We could ask the LLM to cite its sources. But a 3B model easily invents or mangles labels.

So **citations come from the data, not from the LLM's text**: we cite the chunks we passed it, without repeats and sorted by score. They come from the `file` and `section` columns, so they can't be made up.

```
No, she has never used Kubernetes in production. [...]

Sources:
  - experience/northwind-payments.md § Senior Backend Engineer > Infrastructure
```

If the LLM refuses, there are no citations: there's no point showing sources for an "I don't have that information".

## Piece 2 of 6: the gate

```
question ──► search ──► does the top-1 reach the threshold?
                              │
                    no ───────┴─────── yes
                    │                   │
          fixed refusal,          only the chunks that reach it
          LLM not called          go to the LLM, and those are the citations
```

- If **no** chunk reaches the threshold → fixed refusal, and the LLM **isn't called**.
- If some do → **only those** go to the LLM. The rest are dropped.

## Piece 3 of 6: why refuse before the LLM

Refusing without calling the LLM has three advantages ([ADR-0006](../../docs/adr/0006-relevance-gate-before-llm.md)):

1. it's **deterministic**: the same question always gets the same refusal;
2. it's **free**: no 10 seconds of CPU (or cloud tokens to pay for);
3. it **can't be talked into anything** with a clever prompt. An "ignore your rules" doesn't pass the gate because it doesn't look like anything in the CV.

## Piece 4 of 6: where the threshold lives

The threshold is in `config/models.yaml`, **one per embedding model**, because each model has its own score range (step 1):

```yaml
embedding_models:
  bge-m3:
    dimension: 1024
    relevance_threshold: 0.42
```

In this step we started at **0.45**, by eye: step 2's answerable questions scored between 0.51 and 0.65, and the football one 0.41. Step 5 calibrated it with data and it ended up at **0.42**.

To try another value without editing the file:

```bash
RELEVANCE_THRESHOLD=0.5 make ask Q="..."
```

Or set it for yourself with a `RELEVANCE_THRESHOLD=0.40` line in your `.env`.

## Piece 5 of 6: which language to refuse in, without the LLM?

If we don't call the LLM, nobody knows the question's language. `detect_language()` (in `language.py`) is a tiny detector:

- it looks for Spanish marks and letters (`¿`, `¡`, `ñ`, accents);
- it counts frequent words in each language ("qué", "tiene" against "what", "has").

If it isn't sure (for example, with "Kubernetes?"), the refusal comes in both languages:

```
No tengo esa información. / I don't have that information.
```

## Piece 6 of 6: `DEBUG=1` now shows the gate

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

The ✓ marks which chunks passed the gate and reached the LLM. And at the bottom it tells you whether the LLM was called.

| File | What changed |
|------|--------------|
| `src/talk_to_my_cv/rag.py` | `answer()` applies the gate and returns `refused`, `citations`, `retrieved` and `context`. |
| `src/talk_to_my_cv/language.py` | `detect_language()`: `"es"`, `"en"` or `None`. |
| `src/talk_to_my_cv/embeddings.py` | `relevance_threshold(model)`: reads `config/models.yaml`; `RELEVANCE_THRESHOLD` overrides it. |
| `src/talk_to_my_cv/cli.py` | Shows the sources and, with `DEBUG=1`, the gate. |

---

## Check that it works

```bash
make check-04
```

It checks that:
- the Lumen question cites `Project Lumen`;
- the stack question cites `skills.md`;
- the football one is refused **without calling the LLM**, proven with a **spy** (a wrapper around the real model that records whether it was called);
- a Spanish question gets a Spanish answer.

### What was hard: language, and an LLM that isn't deterministic

The language test failed the first time. "¿Cuánto aceleró Project Lumen la conciliación?" got:

```
Project Lumen accelerated the nightly reconciliation run from 9 hours to 14 minutes.
```

Repeating it with **the same input, `temperature=0` and a fixed seed**, it came out in Spanish. Ollama on a CPU **isn't deterministic**: the state of its cache and the order of operations change the result. That's why **a single run proves nothing**.

To measure it, we ran 3 Spanish questions per fresh process, three times:

| Prompt | Answers in Spanish |
|--------|-------------------:|
| The original ("answer in the same language as the question") | 7 of 9 |
| + at the end: "The question is in Spanish. Write your whole answer in Spanish, even if the CONTEXT is in another language." | **9 of 9** |

A small model tends to answer in the context's language, and our context is in English. Since `detect_language()` already knows the question's language, we say it explicitly and **at the end** of the prompt, where it weighs the most. It's a measured improvement, not a guarantee: 9 of 9 is a small sample.

## Play with it

1. **The JavaScript trap, now with citations.** Try `make ask DEBUG=1 Q="Has she worked with JavaScript?"`:

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

   It's worse than in step 3: the hallucination ("No", when the CV says nothing about JavaScript) now **comes with 4 sources** and looks backed up.

   > **A citation is not a guarantee.** We cite what the LLM **read**. That doesn't prove what the LLM **claims**: none of those 4 chunks says she didn't use JavaScript. A citation tells you where to look, not that the answer is true.

2. **Move the threshold.** Try the JavaScript one with `RELEVANCE_THRESHOLD=0.5` (refuses without calling the LLM) and then "¿Usó Kubernetes?" with `RELEVANCE_THRESHOLD=0.52` (also refuses, and that one had an answer). That's the dilemma step 5 settles with data.

3. **Try the language detector.** Ask a single off-topic word, like "Pizza?". It doesn't pass the gate, the detector can't tell the language, and the refusal comes in both. Then try "Netflix?": it barely passes the gate (0.474, against "Data and messaging"), so it calls the LLM, which refuses on its own, in English. A tech word looks like the CV even when it's unrelated.

---

## FAQ

<details>
<summary><b>How is the threshold value chosen?</b></summary>

Not by eye: it's measured. You write questions, mark which have an answer and which must be refused, try many thresholds and keep the one that gets the most right. That's step 5. And 0.42 was calibrated for the example CV: your CV may need another value. A perfectly valid question may score 0.416 and be refused by a hair.
</details>

<details>
<summary><b>What if I had a million mixed CVs (cooks, firefighters, developers)?</b></summary>

The gate alone stops working, for two reasons:

1. **There's always something similar.** If you ask "can Valentina cook?", among a million CVs there's a cook with a 0.80 chunk. It passes the gate, but it's someone else. You have to **filter by person first** (with the metadata), and only then search and gate.
2. **One number doesn't fit all.** CVs from different fields score differently.

The industry adds per-document-type thresholds, a **reranker** (a second, slower and more precise model that rereads the top 20 or 50 and gives a more reliable score) and checks before answering (step 7). The threshold works well only for a small, uniform document, like a CV.
</details>

---

## ✋ Review

**1. Why doesn't the LLM write the citations?**

<details><summary>Show answer</summary>

Because a small model invents or mangles labels. Citations come from the `file` and `section` columns of the chunks it was given: they can't be made up.
</details>

**2. What three advantages does refusing before calling the LLM have?**

<details><summary>Show answer</summary>

It's deterministic (always the same refusal), it's free (no CPU or tokens spent) and it can't be talked into anything with a clever prompt.
</details>

**3. An answer comes with 4 citations. Does that prove it's true?**

<details><summary>Show answer</summary>

No. Citations say what the LLM read, not that what it claims is in those chunks. The JavaScript trap answers "No" with 4 citations, and none of them says anything about JavaScript.
</details>

**4. 🧪 Try it:** `RELEVANCE_THRESHOLD=0.52 make ask DEBUG=1 Q="¿Usó Kubernetes?"`. What happens, and why is it a problem?

<details><summary>Show answer</summary>

It refuses without calling the LLM, because the best chunk scores 0.514. But that question had an answer ("not in production"). Raising the threshold refuses junk, but also good questions.
</details>

**5. Same question, `temperature=0`, fixed seed: once in English, once in Spanish. Is it a bug?**

<details><summary>Show answer</summary>

No: Ollama on a CPU isn't 100% deterministic. That's why a single run proves nothing, tests never compare exact text and step 5's evaluation measures over many questions.
</details>

---

[← Step 3](../03-first-rag/README.md) · [Index](../../README.md) · [Next: Step 5, evaluation →](../05-evaluation/README.md)
