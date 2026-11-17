# One evolving package; lessons are docs; step tags are immutable

All code lives in a single package, `src/talk_to_my_cv/`, which grows step by step. `lessons/NN-name/` holds only READMEs, and each one links to the `step-(N-1)...step-N` diff. We rejected a code folder per lesson because it duplicates code and drifts apart. Tags `step-NN` are never moved: when a bug in an earlier step is found, it is fixed forward and the fix is noted in the next lesson. This keeps "runs on its own from its tag" true for every published tag.
