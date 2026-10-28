# MatchMiner-AI web app

Enter an MRN and get a final decision for each candidate clinical trial, plus
visual tracing of *why*: notes → key events → patient summary → candidate trial
spaces → TrialChecker / BoilerplateChecker → decision.

Everything lives in `webapp/`. The `matchminer_ai` package in `../src` is
imported as-is (editable path dependency) and is never modified.

```
webapp/
  backend/   Flask services + MCP server (uv, Python 3.12)
  frontend/  Vue 3 + Vite + TypeScript + Vue Flow (bun)
```

## Models

| Step | Model | Where |
| --- | --- | --- |
| Patient + trial summarization, key-event journey | `gpt-5.6-luna` | Mayo Apigee → Azure OpenAI **Responses API** |
| Embedding (`TrialSpace`) | `ksg-dfci/TrialSpace-0526` | local GPU |
| Match quality (`TrialChecker`) | `ksg-dfci/TrialChecker-0526` | local GPU |
| General exclusions (`BoilerplateChecker`) | `ksg-dfci/BoilerplateChecker-0526` | local GPU |
| Optional LLM review (0–5 score + exclusion verdict, with rationale) | `gemma-4-E2B-it` | local llama.cpp, `http://127.0.0.1:8081/v1` |

How luna is wired in without touching the package: `mmai_web.llm.backends.install()`
replaces the `get_llm_backend` lookup in `patients.summarize`, `trials.summarize`
and `matching.llm_checks` with a router. Any task section in
`backend/config/mmai_web.yaml` with `provider: openai_responses` goes to the
Responses API; every other task uses the package's own backend. The same hook
swaps the patient prompt-builder process pool for a thread pool, because a
spawned process pool inside a web server re-imports the entry point on Windows.
To move another step to luna (or back to local), edit the YAML.

## Run

```powershell
# 1. Optional: local Gemma for the "LLM review" toggle. Start it BEFORE the
#    backend: on this workstation the backend's torch process and llama.cpp
#    compete for commit memory, and whichever starts second can fail to load.
H:\Apps\llama.cpp\run_server_gemma4e2b.bat

# 2. Backend (API + MCP) on http://127.0.0.1:5050
cd webapp\backend
copy dotenv.tpl .env          # fill APIGEEX_CLIENT_ID / APIGEEX_CLIENT_SECRET
uv sync
uv run mmai-web warmup        # optional: embed the trial corpus once (cached in .cache/)
uv run mmai-web serve

# 3a. Frontend dev server on http://localhost:5173 (proxies /api to :5050)
cd webapp\frontend
bun install
bun run dev

# 3b. ...or build it once and let the backend serve it at http://127.0.0.1:5050
bun run build
```

Tests: `cd webapp\backend; uv run --group dev pytest`.

## Data

| Setting (env / `.env`) | Default |
| --- | --- |
| `MMAI_WEB_NOTES_SOURCES` | `examples/data/note_set_1.csv;note_set_2.csv` (synthetic). One or more CSVs (`;`-separated) with `patient_id` (= MRN) or `mrn`, `note_text`, `note_date`, optional `event_type`. |
| `MMAI_WEB_TRIAL_SUMMARIES` | `examples/output/trial_summaries.csv` (31B trial spaces for 10 trials) |
| `MMAI_WEB_TRIALS` | `examples/data/trials_for_summarize.csv` (titles / eligibility text) |
| `MMAI_WEB_SUMMARY_MODEL` | `gpt-5.6-luna` |
| `MMAI_WEB_CONFIG` | `backend/config/mmai_web.yaml` |

**Real patient data.** Point `MMAI_WEB_NOTES_SOURCES` at a file outside the
repo (for example `H:\data\mm-ai\mayo_dataset_10.csv`). Notes, summaries and run
results stay in backend memory only. The backend logs counts and exception
*types*, never note text. Only trial embeddings and model metadata are written
to `backend/.cache/`. New note sources (such as the mc-gdm Data Mart server)
plug in by implementing `NotesProvider` in `services/notes.py`.

## Decision rule

For each trial, its best-scoring clinical space is used:

- **Not matched**: the TrialChecker score is below `match_quality.score_cutoff` (0.2).
- **Potentially eligible**: the score passes, BoilerplateChecker finds no general exclusion,
  and (if LLM review ran) the reviewer neither scores it 0 ("not reasonable") nor flags an exclusion.
- **Needs review**: the score passes, but an exclusion check flags it.

These are screening aids, not eligibility determinations.

## HTTP API (one blueprint per service)

| Service | Endpoints |
| --- | --- |
| system | `GET /api/health`, `GET /api/config` |
| notes | `GET /api/notes/patients`, `GET /api/notes/patients/<mrn>[?text=0]` |
| patients | `POST /api/patients/summary`, `POST /api/patients/journey` — body `{"mrn"}` or `{"notes":[...]}`; `POST /api/patients/parse-summary` |
| trials | `GET /api/trials`, `GET /api/trials/<id>`, `POST /api/trials/summarize` |
| embedding | `POST /api/embedding` `{"texts":[...]}` |
| matching | `POST /api/matching/candidates`, `/quality`, `/exclusion`, `/llm-review` |
| pipeline | `POST /api/pipeline/runs` `{"mrn","options"}` → 202 + id; `GET /api/pipeline/runs[/<id>]` |

Other Python apps can skip HTTP and use the services directly:
`from mmai_web.services import get_services`.

## MCP

The same server exposes MCP (streamable HTTP) at `http://127.0.0.1:5050/mcp`.
`uv run mmai-web mcp` runs it over stdio instead. Tools: `list_patients`,
`get_patient_notes`, `summarize_patient`, `extract_patient_journey`,
`parse_patient_summary`, `list_trials`, `get_trial`, `find_candidate_trials`,
`score_match_quality`, `check_exclusion_criteria`, `embed_texts`,
`match_patient_to_trials`, `start_trial_matching`, `get_trial_matching`.
See `mcp.example.json` for client config. MRN-based tools return patient
data, so only connect agents that are approved to receive it.

## UI

- **Decision flow** (Vue Flow): notes → key events (colored by group:
  diagnosis / treatment / disease status / other) → summary facets → patient →
  candidate trials (TrialChecker meter with cutoff tick) → decision buckets.
  Click a node to highlight its neighbors and open details: note text, cited
  source notes, decision reasons, the matched clinical space, exclusion
  criteria, and the LLM rationale.
- **Patient journey**: key events in a year × group grid, chained in date order.
- **Trials**: ranked decision list.
