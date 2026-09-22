# Local run (Gemma 4 E2B / llama.cpp) vs. reference run (Gemma 4 31B / vLLM)

Both runs use the *same* small models (TrialSpace-0526, TrialChecker-0526,
BoilerplateChecker-0526) and the same 10 trials / 12 patients of example data.
The only difference is the summarization LLM:

| | `examples/output/` (reference) | `examples/output_local_llamacpp/` (this run) |
| --- | --- | --- |
| LLM | Gemma 4 31B IT, vLLM, H100-class | Gemma 4 E2B IT Q4_0, llama.cpp, RTX 5060 Ti 16 GB |
| Trial spaces extracted | 30 (from 10 trials) | 24 (from 10 trials) |
| Final matches | 35 rows, 12 patients, 5 trials | 16 rows, 11 patients, 3 trials |
| `passes_exclusion_criteria` | 29 True / 6 False | 16 True / 0 False |

## final_matches.csv

* **Every one of the 16 local matches is also in the 31B result** (16/16 overlap).
  So the small model does not invent matches here; it finds a subset:
  precision 100 %, recall 16/35 = 46 % against the 31B run.
* Patient coverage 11/12. Only `3996000000` drops out — its single 31B match
  (NCT03319901) does not survive locally.
* Trial coverage 3/5. NCT05538130 loses 10 of its 11 patient pairs and
  NCT06234423 loses 7; NCT03319901 and NCT05608252 disappear entirely.
* Ranking agrees moderately: same `match_rank` on 11/16 shared pairs
  (Spearman 0.53), and the rank-1 trial per patient agrees for 8/11 patients.
* Summaries are much more verbose locally: patient summary median 1 996 vs
  1 096 characters, matched clinical space 1 244 vs 383, patient exclusion
  evidence mean 1 012 vs 163.

## Why the local run finds fewer matches

The retrieval stage is *not* the bottleneck — recomputing candidates from the
saved embeddings gives 240 candidate pairs in both runs, covering all 10 trials,
and every patient sees NCT05538130 as a candidate. The losses come from trial
space extraction:

1. **Repetition.** For NCT06234423 the small model emitted the *same* space 10
   times (10 identical 612-character lines; the package's QC flags this as
   `trials_with_non_distinct_spaces`). Those duplicates occupy 120 of the 240
   candidate slots — half of every patient's top-20 — crowding out other trials.
2. **Under-splitting.** The 31B run splits most trials into 2-4 clinically
   distinct spaces; the local run collapses 7 of 10 trials to a single space.
   A single merged space matches fewer patients and scores lower with
   TrialChecker, which is what filters the pairs out.
3. **A real clinical error.** For NCT06234423 the 31B run correctly separates a
   female-only ovarian cohort from a general advanced-solid-tumour cohort. The
   local run writes `Sex allowed: Male or female` for an ovarian arm — exactly
   the mistake the prompt warns about.
4. **Exclusion checking looks permissive.** The local run passes all 16 pairs
   while the 31B run fails 6. Same BoilerplateChecker weights, so the cause is
   the extracted text: the local exclusion lists are longer but more generic
   boilerplate, and the patient-side evidence is more verbose and less pointed.

Patient summaries themselves hold up well (all 12 contain every required field,
biomarkers and treatment dates are largely correct — see patient 1722 in both
files). Trial space extraction is where 4.6 B parameters at Q4 fall short.

## Cheap things to try next

* Raise `repetition_penalty` (1.05 -> 1.15) / `presence_penalty` for the
  `trial` task to stop the duplicate-space loop, or de-duplicate spaces after
  `postprocess_trial_summaries`.
* A 12-14 B Q4 GGUF still fits in 16 GB and should recover most of the space
  splitting; only `remote.model_name` plus the llama.cpp server change.
