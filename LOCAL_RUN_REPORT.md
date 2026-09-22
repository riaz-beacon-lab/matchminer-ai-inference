# MatchMiner-AI: local single-GPU run report

**Branch:** `local-run` · **Date:** 2026-09-22 · **Package:** `matchminer-ai` 0.4.0

**Goal:** get `examples/run_examples.ipynb` to run end to end on one Windows
workstation, hosting every model locally except the 31B summarization LLM.

**Outcome:** achieved. All 44 code cells execute with zero errors in ~7 minutes
wall clock. Trial and patient summarization pass every QC check the package
applies. Match quality is substantially below the reference 31B run, and the
cause is isolated to one pipeline stage (trial space extraction).

---

## 1. Environment

| | |
| --- | --- |
| OS | Windows 11 Enterprise 26200 |
| GPU | NVIDIA RTX 5060 Ti, 15.9 GiB, Blackwell (sm_120), driver 610.88 / CUDA UMD 13.3 |
| Python | 3.12.13 (uv-managed venv) |
| Key libs | torch 2.11.0+cu128, transformers 5.17.0, sentence-transformers 6.1.0 |
| LLM server | llama.cpp `b10235-221f0f635`, `llama-server.exe` |

No vLLM. No FlashAttention. Both turned out to be unnecessary (§3.1, §3.2).

## 2. Models

MatchMiner-AI is a four-model pipeline. Three of the four run directly on the
local GPU; only the LLM is swapped for a smaller quantized one.

| Role | Model | Base | Size on disk | How it runs here |
| --- | --- | --- | --- | --- |
| Summarization LLM | `gemma-4-E2B-it` Q4_0 GGUF (4.63 B params) | — | 2.8 GB | llama.cpp server, `http://127.0.0.1:8081/v1` |
| Embedding | [`ksg-dfci/TrialSpace-0526`](https://huggingface.co/ksg-dfci/TrialSpace-0526) `279dc90` | Qwen3-Embedding-0.6B | 1.2 GB | sentence-transformers, CUDA |
| Match-quality checker | [`ksg-dfci/TrialChecker-0526`](https://huggingface.co/ksg-dfci/TrialChecker-0526) `0976a2c` | ModernBERT-large | 1.5 GB | transformers `text-classification`, CUDA |
| Exclusion checker | [`ksg-dfci/BoilerplateChecker-0526`](https://huggingface.co/ksg-dfci/BoilerplateChecker-0526) `326d21f` | ModernBERT-large | 1.5 GB | transformers `text-classification`, CUDA |

Production uses Gemma 4 31B IT (FP8) for the LLM role; E2B is what fits in
16 GB alongside the three small models. Peak observed GPU usage for the whole
pipeline was ~7.8 GB (llama.cpp ~3.3 GB + one checker model at a time).

## 3. Method

### 3.1 LLM: remote backend instead of vLLM

The package already ships an OpenAI-compatible **remote backend**
(`src/matchminer_ai/llm/remote_inference.py`), used when `remote.enabled: true`.
llama.cpp's server speaks that protocol, so it drops straight in — **no package
code changes were needed**. Two details that made this painless:

* In remote mode `build_prompt_list()` sends raw `messages` and lets the server
  apply the chat template, so no local Gemma weights or template are required.
* llama.cpp ignores the vLLM-specific request fields the package sends
  (`skip_special_tokens`, `chat_template_kwargs`), rather than erroring, so no
  pruning of `extra_body` was needed. Verified with a direct curl probe before
  wiring anything up.

`get_endpoint_model_metadata()` already tolerates a served model name that is
not a Hub ID (`gemma-4-E2B-it`), falling back to synthetic provenance metadata.

### 3.2 The three small models

All three loaded and ran unmodified on Blackwell with torch cu128. The concern
about FlashAttention was not an issue in practice: transformers falls back to
SDPA/eager for ModernBERT and Qwen3-Embedding when FlashAttention is absent.
Verified each in isolation before running the notebook (embedding produced
(2, 1024) float32 vectors; both checkers returned scores).

### 3.3 Configuration

`examples/config_local_llamacpp.yaml`, generated from
`matchminer_ai/presets/default.yaml` so that no required key is lost. Deltas:

| Setting | Default | Local | Why |
| --- | --- | --- | --- |
| `remote.enabled` | `false` | `true` | use the HTTP backend |
| `remote.server_urls` | `localhost:8000/v1` | `127.0.0.1:8081/v1` | llama.cpp port |
| `remote.max_concurrent_requests` | 16 | 4 | matches `--parallel 4` slots |
| `*.remote.model_name` | `google/gemma-4-31B-it` | `gemma-4-E2B-it` | served alias |
| `patient.remote.tokenizer_name` | `google/gemma-4-31B-it` | unchanged | chunking still uses the Gemma tokenizer (config + tokenizer files only, ~31 MB, no weights) |
| `*.engine.max_model_len` | 30000–100000 | 32768 | 64 K per slot, 4 slots |
| `patient.chunk_size` | 50000 | 24000 | keeps prompts inside one slot |
| `max_tokens` | 15000–20000 | 6000 / 4000 / 1500 | trials / patients / LLM checkers |
| sampling | temp 1.0, top_p 0.95, top_k 20, presence 1.5 (trials) | temp 0, top_p 1.0, top_k 1, repetition 1.05 | greedy decoding improves format adherence for a small model |
| `patient.prompt_build_workers` | `min(cpu_count, 32)` | 4 | avoids spawning 32 tokenizer processes |

### 3.4 Notebook changes

* The two **local-mode (in-process vLLM)** cells became markdown notes that keep
  the original code visible.
* The two **remote-mode** cells load `config_local_llamacpp.yaml`; every
  downstream step is passed the same `config=config`.
* The two **optional LLM-based** checkers run on `.head(10)` rows — they are far
  slower than the classifier checkers. Classifier checkers still run on the full
  candidate set.
* Artifact writes point at `examples/output_local_llamacpp/` so the checked-in
  31B reference artifacts in `examples/output/` are never clobbered.
* `pyproject.toml`: `vllm` moved from required dependencies to a `[vllm]` extra,
  so the package installs on Windows at all.

### 3.5 Execution

```powershell
# terminal 1
H:\Apps\llama.cpp\run_server_gemma4e2b.bat      # ctx 262144, --parallel 4, flash-attn on

# terminal 2
cd examples
..\.venv\Scripts\python.exe -m jupyter nbconvert --to notebook --execute --inplace `
  --ExecutePreprocessor.kernel_name=python3 --ExecutePreprocessor.timeout=7200 run_examples.ipynb
```

Input data: 10 trials (first 10 of 470 in `trials_for_summarize.csv`),
117 notes / 12 patients (`note_set_1.csv`), plus 56 notes (`note_set_2.csv`)
for the longitudinal-update step.

## 4. Results

### 4.1 Execution

44/44 code cells executed, **0 errors**, ~7 minutes total:

| Stage | Wall clock |
| --- | --- |
| Trial summarization (10 trials) | ~1 min |
| Patient summarization (12 patients, 2 note sets) | ~2 min |
| Embedding (36 texts) | ~10 s |
| Classifier checkers (240 + 16 pairs) | ~3 min |
| LLM-based optional checkers (10 + 10 pairs) | ~1 min |

Throughput: ~88 tok/s decode per stream on the E2B Q4_0 model; trial prompts
were 5–8 K tokens, patient prompts 20–23 K tokens.

### 4.2 Package QC — all clean

* Trials: 0 failed inference, 0 truncated responses, 0 spaces over the embedding
  token limit, 10/10 trials produced spaces (24 spaces total).
  One flag: `trials_with_non_distinct_spaces = 1/10` (see §5.1).
* Patients: 12/12 summaries contain every required field (Age, Sex, Cancer type,
  Histology, Current extent, Biomarkers, Treatment history); 0 exceeded the
  embedding token limit; exclusion evidence extracted for all 12.
* Optional LLM checkers parsed cleanly: match-quality scores 3–5, exclusion
  verdicts boolean — no `parse_failed`.
* End-to-end output: 16 final matches across 11 patients.

### 4.3 Comparison with the 31B reference artifacts

Detailed write-up and raw score tables:
`examples/output_local_llamacpp/COMPARISON.md`,
`trialchecker_scores_{31B,E2B}.csv`.

**Caveat found first:** the checked-in `examples/output/final_matches.csv` is not
self-consistent with the `trial_summaries.csv` beside it — 21 of its 35
`trial_id-clinical_space_number` keys do not exist in that file, and 0/35 space
texts match (patient summaries match 35/35). The trial artifacts were
regenerated later without regenerating the final matches. Comparing row counts
against that file is therefore only indicative.

So the comparison was redone by re-running the **deterministic** downstream
stages (candidate retrieval → TrialChecker) over both runs' checked-in
summaries:

| | 31B spaces | E2B spaces |
| --- | --- | --- |
| Trial spaces | 30 | 24 |
| Candidate pairs (top-20 spaces/patient) | 240 | 240 |
| Trials reaching candidate lists | 10/10 | 10/10 |
| TrialChecker score median / p75 / max | 0.000 / 0.482 / **0.994** | 0.033 / 0.152 / **0.612** |
| Candidate rows passing (≥ 0.2) | 98 (41 %) | 52 (22 %) |
| Unique patient-trial pairs passing | **56** | **16** |
| Patients with ≥ 1 match | 12 | 11 |

* **Overlap: 15 of 16** local pairs are in the 31B set → precision 94 %,
  recall 27 %. The one extra local pair is (patient 11609, NCT05538130).
* On pairs that survive into both `final_matches.csv` files, ranking agrees
  moderately: identical `match_rank` on 11/16 rows (Spearman 0.53); rank-1 trial
  per patient agrees for 8/11 patients.
* Exclusion checking is more permissive locally: 16 True / 0 False versus
  29 True / 6 False. Same BoilerplateChecker weights, so the difference is in
  the extracted text, not the model.
* Local output is much more verbose: patient summary median 1 996 vs 1 096
  characters, matched clinical space 1 244 vs 383, patient exclusion evidence
  mean 1 012 vs 163.

## 5. Findings

### 5.1 The bottleneck is trial space extraction, not retrieval or the checkers

Recomputing candidates from the saved embeddings gives 240 candidate pairs in
both runs, covering all 10 trials, with every patient seeing every trial's
spaces as candidates. Retrieval behaves. Four concrete failure modes in the
small model's space extraction explain the gap:

1. **Repetition loop.** For NCT06234423 the model emitted the *same* space 10
   times — ten byte-identical 612-character lines. Those duplicates take 120 of
   the 240 candidate slots (half of every patient's top-20), crowding out other
   trials. The package's QC catches this as `trials_with_non_distinct_spaces`.
2. **Under-splitting.** The 31B run splits most trials into 2–4 clinically
   distinct spaces; the local run collapses 7 of 10 trials into a single space.
   A merged space matches fewer patients and scores lower with TrialChecker.
3. **A real clinical error.** On the same trial, the 31B run correctly separates
   a female-only ovarian cohort from a general advanced-solid-tumour cohort; the
   local run writes `Sex allowed: Male or female` for an ovarian arm — precisely
   the error the prompt warns against.
4. **Verbose, generic exclusion text.** Longer but less pointed exclusion lists
   and patient evidence make the BoilerplateChecker pass everything.

TrialChecker's confidence ceiling drops from 0.994 to 0.612, which is the
quantitative signature of (1)–(2).

### 5.2 Patient summarization holds up

All 12 patient summaries are structurally complete and largely correct.
Spot-checking patient 1722 against the 31B output: cancer type, histology
(signet-ring), HER2 3+/ISH amplified, KRAS G12D, PIK3CA H1047R, TP53 R175H,
CDH1 truncation, ARID1A LOH, MET and FGFR2 amplification, MSS, TMB 5 — all
present in both. The local version misses PD-L1 CPS and is wordier, but no
fabrication was observed.

### 5.3 Platform issues encountered

| Issue | Resolution |
| --- | --- |
| vLLM has no usable Windows wheel | Use the package's remote backend + llama.cpp; move `vllm` to an optional extra |
| `multiprocessing.Pool` in `patients/prompt_builder.py` fork-bombs on Windows | Harmless from a Jupyter kernel, but a plain `.py` driver **must** guard its entry point with `if __name__ == "__main__":`. Cost 8 minutes of confusion when a test script omitted it |
| `HF_HUB_OFFLINE=1` breaks the run | `get_model_metadata()` calls `model_info()` for provenance; needs network or a pre-populated `.mmai_cache/model_metadata` |
| Patient chunking needs a Gemma tokenizer | `google/gemma-4-31B-it` config + tokenizer files only (31 MB), no weights |
| Default `prompt_build_workers` = CPU count | Set to 4; each worker loads its own tokenizer process |

Minor observation, not fixed: `matching/inference.py` passes
`model_metadata_cache_dir` as the tokenizer's `cache_dir`, so checker tokenizers
are downloaded into the metadata cache directory rather than the HF cache.

## 6. Recommendations

**Cheap, try first:** raise `repetition_penalty` 1.05 → 1.15 (or add
`presence_penalty`) for the `trial` task to break the duplicate-space loop — a
one-line YAML change, ~2 minutes to re-run the trial step. Optionally
de-duplicate spaces after `postprocess_trial_summaries`.

**Bigger win:** a 12–14 B Q4 GGUF still fits in 16 GB and should recover most of
the space splitting. Only `remote.model_name` and the llama.cpp server change;
no code or notebook edits.

**Upstream-worthy:** regenerate `examples/output/final_matches.csv` so the
checked-in reference artifacts are internally consistent (§4.3).

**For the wider question in Ken's email:** the three small models ran without
trouble on a consumer Blackwell card with a stock CUDA 12.8 torch build — no
FlashAttention, no dependency pain. The pipeline's own remote backend means any
OpenAI-compatible server (llama.cpp, vLLM, or a hosted BAA endpoint) can host
the LLM, so GPU selection really only constrains the LLM half of the problem.

## 7. Artifacts

| Path | Contents |
| --- | --- |
| `examples/config_local_llamacpp.yaml` | local run configuration |
| `examples/README_local_run.md` | setup and run instructions |
| `examples/run_examples.ipynb` | executed notebook with outputs |
| `examples/output/` | **untouched** 31B reference artifacts (verified identical to `main`) |
| `examples/output_local_llamacpp/` | this run's artifacts + `COMPARISON.md` + TrialChecker score tables |

Commits on `local-run`: `8da3b8b` (run the notebook locally), `b395db9`
(separate artifacts, restore reference outputs), `4ba1b63` (notebook writes to
the local output dir), `21eb3de` / `2202348` (comparison notes and scores).
