# Step 4: Citations and threshold

🇪🇸 [Leer en español](README.es.md)

## What you'll learn

- How to make answers **checkable**: every answer says which file and section it came from.
- How to refuse **deterministically**: if nothing is relevant, the LLM isn't even called.
- Why a small LLM on a CPU is **not deterministic**, even with `temperature=0` and a `seed`.

## The concept

### Citations the LLM doesn't invent

In step 3, every chunk reached the prompt with its `[file § section]` label. We could ask the LLM to cite, but a 3B-parameter model easily invents or mangles labels. So **citations come from the metadata, not from the LLM's text**: we cite the chunks we passed to it, without duplicates and ordered by score.

```
No, nunca ha utilizado Kubernetes en producción. [...]

Sources:
  - experience/northwind-payments.md § Senior Backend Engineer > Infrastructure
```

(The answer means "No, she has never used Kubernetes in production.")

If the LLM refuses, there are no citations: there's no point showing sources for an "I don't have that information".

### The relevance threshold

```
question ──► search ──► does the top-1 pass the threshold?
                              │
                    no ───────┴─────── yes
                    │                   │
          fixed refusal,           only the chunks that pass
          LLM never called         go to the LLM, and those are the citations
```

Refusing without calling the LLM has three advantages ([ADR-0006](../../docs/adr/0006-relevance-gate-before-llm.md)):

- it's **deterministic**: the same question always gets the same refusal;
- it's **free**: no waiting 10 seconds of CPU;
- it **can't be talked around** by a clever prompt.

The threshold lives in `config/models.yaml`, **one per embedding model**: in step 1 we saw that each model has its own score range. For `bge-m3` we start at **0.45**, a provisional value based on step 2's measurements: answerable questions scored between 0.51 and 0.65, the football one 0.41. Step 5 calibrates it with data. To try another value without editing the file: `RELEVANCE_THRESHOLD=0.5 make ask Q="..."`.

### Which language to refuse in, without the LLM?

If we don't call the LLM, nothing knows which language the question was in. `detect_language()` is a tiny detector: it looks at `¿`, `¡`, accents, `ñ` and frequent words. When it isn't sure (for example, with "Kubernetes?"), the refusal comes out in both languages:

```
No tengo esa información. / I don't have that information.
```

## The code

| File | What changed |
|------|--------------|
| `src/talk_to_my_cv/rag.py` | `answer()` applies the threshold and returns `refused`, `citations`, `retrieved` and `context`. |
| `src/talk_to_my_cv/language.py` | `detect_language()`: `"es"`, `"en"` or `None`. |
| `src/talk_to_my_cv/embeddings.py` | `relevance_threshold(model)`: reads `config/models.yaml`; `RELEVANCE_THRESHOLD` overrides it. |
| `src/talk_to_my_cv/cli.py` | Prints the sources. With `DEBUG=1`, also which chunks passed the threshold (✓) and whether the LLM was called. |

## Check that it works

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

`make check-04` checks that:
- the Lumen question cites `Project Lumen`;
- the stack question cites `skills.md`;
- the football question is refused **without calling the LLM**, proven with a spy wrapped around the real model;
- a Spanish question gets a Spanish answer.

### What was hard: the language, and an LLM that isn't deterministic

The language test failed the first time. The question "¿Cuánto aceleró Project Lumen la conciliación?" ("How much did Project Lumen speed up reconciliation?") got this answer:

```
Project Lumen accelerated the nightly reconciliation run from 9 hours to 14 minutes.
```

Running it again with **the same input, `temperature=0` and a fixed `seed`**, the answer came out in Spanish. Ollama on a CPU is **not deterministic**: the state of its cache and the order of operations change the result. That's why this project's tests never compare exact text ([ADR-0008](../../docs/adr/0008-tests-against-nondeterministic-llms.md)), and why **a single run proves nothing**.

To measure it properly, we ran the full pipeline in fresh processes, 3 Spanish questions per process:

| Prompt | Answers in Spanish |
|--------|-------------------:|
| The original ("answer in the same language as the question") | 7 of 9 |
| + at the end: "The question is in Spanish. Write your whole answer in Spanish, even if the CONTEXT is in another language." | **9 of 9** |

A small model tends to answer in the language of the context, and our context is in English. Since `detect_language()` already knows the question's language, we state it explicitly, and **last** in the prompt, where it weighs most. With that, the test passes reliably. It's a measured improvement, not a guarantee: 9 of 9 is a small sample, and step 5 will measure it across every question.

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

   It's worse than in step 3: the hallucination ("No", when the KB says nothing about JavaScript) now **comes with 4 sources** and looks backed up. As we saw in step 2, the top-1 (0.499) sits right next to Kubernetes' (0.514), so the threshold can't separate them.

   > **A citation is not a guarantee.** We cite the chunks that passed the threshold, that is, what the LLM **read**. That doesn't prove what the LLM **claims**: none of those 4 chunks says she never used JavaScript. A citation tells you where to look, not that the answer is true.

   Step 5 will measure this. In `eval/questions.yaml`, the `trap-javascript` question has `forbid_unsupported_no: true`: the only correct result is the refusal, and a "No" counts as a hallucination, with or without citations.

2. **Move the threshold.** Try the JavaScript question with `RELEVANCE_THRESHOLD=0.5` (it refuses without calling the LLM), then "¿Usó Kubernetes?" with `RELEVANCE_THRESHOLD=0.52` (it also refuses, and that one did have an answer). That's the dilemma step 5 settles with data.

3. **Try the language detector.** Ask a single off-topic word, like "Pizza?" or "Messi?". It doesn't pass the threshold, the detector can't tell the language, and the refusal comes out in both. Then try "Netflix?": it barely passes the threshold (0.474, against "Data and messaging"), so it does call the LLM, which refuses on its own, in English. A tech word looks like the KB even when it has nothing to do with it.
