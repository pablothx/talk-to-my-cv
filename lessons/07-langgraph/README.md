# Step 7: LangGraph and verification

🇪🇸 [Leer en español](README.es.md)

## What you'll learn

- How to write the RAG flow as a **graph** with LangGraph: nodes, state and conditional routing.
- How to add a **verification** step before answering, and why a small model is a poor judge.
- A pattern that works well with small models: **the LLM extracts, code decides**.
- How to **reformulate** the question so keyword search understands questions in Spanish.

## The concept

### From a function to a graph

Up to step 6, `answer()` was a top-to-bottom function: search, gate, ask the LLM. Every new step (reformulate, verify) adds an `if`, and the function gets hard to read and to test.

LangGraph writes it as a graph: each **node** is a function that reads the **state** and returns what changes, and **conditional edges** decide which node runs next.

```
   [reformulate] → retrieve → gate ─┬─ nothing above the threshold ─────────→ refuse
                                    └─ verify ─┬─ a name is missing ────────→ refuse
                                               └─ otherwise → answer with citations
```

`reformulate` only runs in `keyword` and `hybrid` modes (see why below).

### The verification that didn't work

[ADR-0009](../../docs/adr/0009-top1-gate-does-not-separate-alone.md) called for an LLM verification step after search. The obvious idea is to ask it: "does this CONTEXT answer the QUESTION? Reply YES or NO".

We tried it with `qwen2.5:3b` on 6 questions with a known answer, using three different prompts:

| Question | Expected | Prompt A | Prompt B | Prompt C |
|---|:-:|:-:|:-:|:-:|
| How much did Project Lumen speed up reconciliation? | YES | ✓ | ✓ | ✗ |
| Has she used Kubernetes in production? | YES | ✗ | ✗ | ✗ |
| Has she worked with JavaScript? | NO | ✓ | ✓ | ✓ |
| ¿Trabajó con Azure? *(Did she work with Azure?)* | NO | ✓ | ✓ | ✓ |
| ¿Dónde trabaja actualmente y qué rol tiene? *(Where does she work now, and in what role?)* | YES | ✗ | ✗ | ✗ |
| What is her tech stack? | YES | ✓ | ✓ | ✓ |

When in doubt, the model says NO. As a verifier, it would refuse questions that do have an answer. **A 3B model is a poor judge.**

### The LLM extracts, code decides

The same model is good at a smaller task: **extracting** the specific name the question asks about.

| Question | The LLM extracts |
|---|---|
| Has she worked with JavaScript? | `JavaScript` |
| ¿Trabajó con Azure? | `Azure` |
| ¿Usó Kubernetes? *(Did she use Kubernetes?)* | `Kubernetes` |
| What is her tech stack? | `NONE` |
| ¿Dónde estudió? *(Where did she study?)* | `NONE` |

Then **code** checks whether that name appears in the chunks that passed the gate: whole word, ignoring case and accents. "Java" doesn't count as "JavaScript". If it's missing, it refuses without writing an answer. If the question is general (`NONE`), it lets step 4's answer prompt decide.

It's the signal we found in step 6 ("none of the question's words is in the KB"), but now it works in **any** store and mode, pgvector included, and with questions in Spanish, because the extractor writes names in English ([ADR-0011](../../docs/adr/0011-verify-by-extracting-names-not-by-judging.md)).

> **The pattern:** don't ask a small model to judge. Ask it to extract something specific, and do the comparison in code, which doesn't make mistakes and can't be talked around.

### Reformulating for keyword search

BM25 doesn't translate: "¿Qué idiomas habla?" ("What languages does she speak?") shares no words with "Spanish, English, Esperanto". In `keyword` and `hybrid` modes, the graph first asks the LLM to rewrite the question as English keywords, and those are the BM25 query.

The **vector** still comes from the original question. That way the threshold calibrated in step 5 still holds, because it was calibrated on questions, not keywords. In `vector` mode there's nothing to reformulate, and the node doesn't run.

## The code

| File | What it does |
|------|--------------|
| `src/talk_to_my_cv/graph.py` | The graph: the `reformulate`, `retrieve`, `verify`, `generate` and `refuse` nodes; `parse_terms()` and `mentions()`, and `answer_with_graph()`. |
| `src/talk_to_my_cv/rag.py` | Step 3's pipeline, unchanged. `Answer` gains `verified` and `query`. |
| `src/talk_to_my_cv/cli.py` | `ENGINE=pipeline` or `ENGINE=graph` picks which one to use. |

`answer_with_graph()` takes the same arguments and returns the same `Answer` as `answer()`. So the chat, the eval and the tests don't know which one they're using. The pipeline stays as lessons 3 to 6 wrote it.

```bash
ENGINE=graph            # in .env; pipeline is the default
```

The unit tests cover every path through the graph with a `ScriptedChatModel` that replies in order: the gate refuses without calling the LLM, a missing name refuses without writing an answer, `NONE` lets the prompt decide, and reformulating changes the BM25 query but not the vector.

## Check that it works

```bash
make check-07
ENGINE=graph make ask DEBUG=1 Q="Has she worked with JavaScript?"
ENGINE=graph make ask DEBUG=1 Q="Has she used Kubernetes in production?"
make eval ENGINE=graph                                   # ~1.5 min on a CPU
make eval ENGINE=graph STORE=opensearch MODE=keyword     # ~2 min
```

With `DEBUG=1` you see the reformulated query (if any) and whether the question's names were in the context.

## The results

The same 20 questions, threshold 0.42:

| Store · mode | Engine | hit@5 | MRR | refusal acc. | answer acc. | Time |
|---|---|---:|---:|---:|---:|---:|
| pgvector · vector | pipeline | 1.00 | 0.82 | 0.88 | 0.82 | ~1:30 |
| pgvector · vector | **graph** | 1.00 | 0.82 | 0.88 | 0.82 | 1:35 |
| opensearch · hybrid | pipeline | 1.00 | 0.86 | 0.88 | 0.82 | — |
| opensearch · hybrid | **graph** | 1.00 | 0.86 | 0.88 | 0.82 | 2:02 |
| opensearch · keyword | pipeline | 0.64 | 0.52 | 0.71 | 0.71 | — |
| opensearch · keyword | **graph** | **0.82** | **0.77** | **0.82** | **0.76** | 1:55 |

The traps:

| Trap | pipeline | graph |
|---|:-:|:-:|
| JavaScript (must refuse) | ✗ says "No" | **✓ refuses** |
| CRM / HubSpot (must answer) | ✗ | ✗ |
| Kubernetes (must say "no") | ✓ | ✓ |

What to look at:

1. **JavaScript is fixed in every store and mode.** The extractor pulls out `JavaScript`, code doesn't find it in the context, and it refuses. Before, only step 6's keyword mode managed that.
2. **Azure is now refused by a rule, not by luck.** The pipeline refused it too, but because the LLM decided to, and that doesn't always happen (step 4). Now code refuses it, the same way every time.
3. **The metrics on the scored questions don't change.** The ones that fail, fail for another reason: in `degree` the chunk with the answer doesn't pass the gate (0.41); in `team-size` the only chunk that passes is `Contact`, which says nothing about the team; and `talk` translates the talk's title (step 5). Verification can't add what search didn't bring.
4. **Reformulating rescues keyword search:** hit@5 goes from 0.64 to 0.82 and MRR from 0.52 to 0.77, because Spanish questions reach BM25 in English.
5. **It's cheap.** Extracting a name generates very few tokens: on a CPU, the graph takes about as long as the pipeline.

**CRM still isn't fixed,** and now it's refused on purpose: the extractor pulls out `CRM` and the KB never names it. The fix is still writing "HubSpot (CRM)" in the KB.

**The refusal accuracy ≥ 0.9 target is still not met (0.88).** The two remaining errors are extra refusals (`team-size` and `degree`), and in both the chunk with the answer doesn't clear the threshold. Lowering the threshold now that there's verification is tempting, but it would be calibrated on the same 20 questions (step 5).

## Play with it

1. **Try the judge.** In `graph.py`, change `verify` to ask the LLM "does the CONTEXT answer the QUESTION? YES or NO" and use the reply directly. Run `make eval ENGINE=graph`. How many answerable questions does it refuse? If you have a Groq key, try it with `LLM_PROVIDER=groq`: does a 70B model judge better?
2. **Lower the threshold.** Now that verification catches missing names, try `make eval ENGINE=graph THRESHOLD=0.40`. Are `team-size` and `degree` saved? Which unanswerable questions get through now? Remember overfitting.
3. **Fool the extractor.** Write questions that name something with other words: "Did she use K8s?", "Did she code in JS?". What does it extract? Does it refuse even though the KB says "Kubernetes"?

## Known limitations

- **Synonyms and acronyms:** "K8s" doesn't find "Kubernetes", and "CRM" doesn't find "HubSpot". Verification is as literal as the KB.
- **Questions with no names:** "How much does she earn?" names nothing, so verification can't catch it. Those still depend on the gate and the prompt.
- **One more LLM call** per question that passes the gate (two in `keyword` and `hybrid`). On a CPU it's little, because the replies are short; with a remote model it's one more network call.
