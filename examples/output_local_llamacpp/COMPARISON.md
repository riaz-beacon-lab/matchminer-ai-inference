# Local run (Gemma 4 E2B / llama.cpp) vs. reference run (Gemma 4 31B / vLLM)

Both runs use the *same* small models (TrialSpace-0526, TrialChecker-0526,
BoilerplateChecker-0526) and the same 10 trials / 12 patients of example data.
The only difference is the summarization LLM:

| | `examples/output/` (reference) | `examples/output_local_llamacpp/` (this run) |
| --- | --- | --- |
| LLM | Gemma 4 31B IT, vLLM, H100-class | Gemma 4 E2B IT Q4_0, llama.cpp, RTX 5060 Ti 16 GB |
| Trial spaces extracted | 30 (from 10 trials) | 24 (from 10 trials) |
| `final_matches.csv` | 35 rows, 12 patients, 5 trials | 16 rows, 11 patients, 3 trials |
| `passes_exclusion_criteria` | 29 True / 6 False | 16 True / 0 False |

## Caveat: the checked-in reference artifacts are not self-consistent

`output/final_matches.csv` was **not** produced from the `output/trial_summaries.csv`
that sits next to it: 21 of its 35 `trial_id-clinical_space_number` keys do not
exist in that trial-summary file, and 0/35 space texts match (patient summaries
do match, 35/35). The trial artifacts were regenerated later without
regenerating the final matches. So a direct row-count comparison against
`final_matches.csv` is only indicative.

The numbers below therefore come from re-running the *deterministic* downstream
stages (candidate retrieval -> TrialChecker) on both runs' checked-in summaries.
Raw scores: `trialchecker_scores_31B.csv`, `trialchecker_scores_E2B.csv`.

## Consistent comparison: candidate retrieval + TrialChecker

| | 31B spaces | E2B spaces |
| --- | --- | --- |
| Candidate pairs (top-20 spaces/patient) | 240 | 240 |
| Trials reaching candidate lists | 10/10 | 10/10 |
| TrialChecker score median | 0.000 | 0.033 |
| p75 | 0.482 | 0.152 |
| max | **0.994** | **0.612** |
| Pairs passing (>= 0.2) | 98 (41 %) | 52 (22 %) |
| Unique patient-trial pairs passing | **56** | **16** |
| Patients with >= 1 match | 12 | 11 |

* Overlap: 15 of the 16 local pairs are also in the 31B set — precision 94 %,
  recall 27 %. The one extra local pair is (patient 11609, NCT05538130).
* The checker is far less confident in the E2B spaces: its best score is 0.612
  versus 0.994 for the 31B spaces.
* Of the 52 passing E2B candidate rows, 40 belong to NCT06234423 — nearly all
  copies of one duplicated space (see below).
* On the shared pairs that do survive into `final_matches.csv`, ranking agrees
  moderately: identical `match_rank` on 11/16 rows (Spearman 0.53), and the
  rank-1 trial per patient agrees for 8/11 patients.
* Summaries are much more verbose locally: patient summary median 1 996 vs
  1 096 characters, matched clinical space 1 244 vs 383, patient exclusion
  evidence mean 1 012 vs 163.

## Why the local run finds fewer matches

Retrieval is *not* the bottleneck — both runs produce 240 candidate pairs
covering all 10 trials, and every patient sees NCT05538130 as a candidate. The
losses come from trial space extraction:

1. **Repetition.** For NCT06234423 the small model emitted the *same* space 10
   times (10 identical 612-character lines; the package's QC flags this as
   `trials_with_non_distinct_spaces`). Those duplicates occupy 120 of the 240
   candidate slots — half of every patient's top-20 — crowding out other trials.
2. **Under-splitting.** The 31B run splits most trials into 2-4 clinically
   distinct spaces; the local run collapses 7 of 10 trials to a single space.
   A merged space matches fewer patients and scores lower with TrialChecker,
   which is what filters the pairs out.
3. **A real clinical error.** For NCT06234423 the 31B run correctly separates a
   female-only ovarian cohort from a general advanced-solid-tumour cohort. The
   local run writes `Sex allowed: Male or female` for an ovarian arm — exactly
   the mistake the prompt warns about.
4. **Exclusion checking looks permissive.** The local run passes all 16 pairs
   while the reference fails 6. Same BoilerplateChecker weights, so the cause is
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
