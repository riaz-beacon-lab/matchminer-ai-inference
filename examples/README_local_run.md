# Running the example notebook on one local GPU (Windows, no vLLM)

`run_examples.ipynb` on the `local-run` branch is wired up to run entirely on a
single workstation GPU. The only change versus upstream is *where the LLM runs*:
vLLM is replaced by a [llama.cpp](https://github.com/ggml-org/llama.cpp) server
speaking the OpenAI chat-completions API, which the package already supports
through its remote backend (`remote.enabled: true`).

Verified on: Windows 11, RTX 5060 Ti 16 GB (Blackwell), CUDA 13.3 driver,
Python 3.12, torch 2.11.0+cu128.

## Which model runs where

| Pipeline step | Model | How it runs |
| --- | --- | --- |
| Trial space extraction, patient summarization, optional LLM checkers | `gemma-4-E2B-it` (Q4_0 GGUF) | llama.cpp server on `http://127.0.0.1:8081/v1` |
| Embeddings (`TrialSpace`) | [`ksg-dfci/TrialSpace-0526`](https://huggingface.co/ksg-dfci/TrialSpace-0526) | sentence-transformers, local GPU |
| Match-quality checker (`TrialChecker`) | [`ksg-dfci/TrialChecker-0526`](https://huggingface.co/ksg-dfci/TrialChecker-0526) | transformers `text-classification`, local GPU |
| Exclusion checker (`BoilerplateChecker`) | [`ksg-dfci/BoilerplateChecker-0526`](https://huggingface.co/ksg-dfci/BoilerplateChecker-0526) | transformers `text-classification`, local GPU |

The three small models are downloaded automatically from the Hugging Face Hub on
first use (~4 GB total) and all fit on the GPU next to the llama.cpp process.
Production uses Gemma 4 31B; the 4.6 B-parameter E2B model is what fits in 16 GB
here. Output *format* holds up well (all trial spaces and patient summaries
passed the package QC keyword checks), but match quality is not comparable to
the 31B model.

## Setup

```powershell
uv venv --python 3.12
.\.venv\Scripts\Activate.ps1
uv pip install -e .            # vLLM is an optional extra: -e ".[vllm]"
uv pip install jupyterlab      # only needed to open/run the notebook
```

Start the LLM server (keep it running in its own window):

```powershell
H:\Apps\llama.cpp\run_server_gemma4e2b.bat   # -> http://127.0.0.1:8081
```

That script serves `gemma-4-E2B-it-Q4_0.gguf` with `--ctx-size 262144
--parallel 4`, i.e. 4 slots of 64 K context, which matches
`max_concurrent_requests: 4` in the config below.

## Run the notebook

Interactively: open `examples/run_examples.ipynb` and run all cells (working
directory must be `examples/`). Headless:

```powershell
cd examples
..\.venv\Scripts\python.exe -m jupyter nbconvert --to notebook --execute --inplace `
  --ExecutePreprocessor.kernel_name=python3 --ExecutePreprocessor.timeout=7200 run_examples.ipynb
```

## What changed for the local run

* `examples/config_local_llamacpp.yaml` — generated from
  `matchminer_ai/presets/default.yaml`, with:
  * `remote.enabled: true`, `server_urls: [http://127.0.0.1:8081/v1]`,
    `max_concurrent_requests: 4`;
  * `remote.model_name: gemma-4-E2B-it` for all four LLM tasks (the served alias,
    not a Hub ID — provenance metadata falls back to synthetic values);
  * `patient.remote.tokenizer_name: google/gemma-4-31B-it` — chunking and prompt
    budgets still use the Gemma tokenizer (config + tokenizer files only, no
    weights);
  * context and sampling sizes cut to fit one GPU: `max_model_len` 32768,
    `patient.chunk_size` 24000, `max_tokens` 6000 (trials) / 4000 (patients) /
    1500 (LLM checkers), greedy decoding (`temperature: 0`, `top_k: 1`);
  * `patient.prompt_build_workers: 4` so prompt building does not spawn one
    tokenizer process per CPU core.
* `run_examples.ipynb` — the two local-mode (in-process vLLM) cells are now
  markdown notes, the remote-mode cells load the config above, and every later
  step is passed `config=config`. The two optional *LLM-based* checkers run on
  `.head(10)` rows; the classifier-based checkers still run on the full set.
* `pyproject.toml` — `vllm` moved from required dependencies to a `[vllm]`
  extra, so the package installs on Windows.

## Notes / gotchas

* The patient step builds prompts in a `multiprocessing.Pool`. On Windows this
  works from a Jupyter kernel, but a plain `.py` script must guard its entry
  point with `if __name__ == "__main__":`, otherwise the spawned workers
  re-import the script and fork-bomb.
* llama.cpp ignores the vLLM-specific request fields the package sends
  (`skip_special_tokens`, `chat_template_kwargs`), so no extra_body pruning is
  needed.
* Model provenance metadata is fetched from the Hub, so the run needs network
  access (or a pre-populated `.mmai_cache/model_metadata`).
