---
title: ALSARA - ALS Agentic Research Agent
emoji: 🧬
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: "6.12.0"
app_file: als_agent_app.py
license: mit
short_description: AI research assistant for ALS research & trials
pinned: false
sponsors: Sambanova, Anthropic, LlamaIndex
tags:
  - mcp-in-action-track-consumer
---

# ALSARA

ALSARA is an end-to-end agentic research assistant built on an **MCP-first architecture**: a custom MCP client (stdlib bypass), six custom MCP servers, a 4-phase planning/executing/reflecting/synthesis loop, Chroma-backed RAG with pre-loaded biomedical context, `asyncio.as_completed` parallel tool execution, and a query-normalization caching layer to cut redundant LLM calls. Built solo to answer a specific question:

> **Can an MCP-based agent give a real ALS patient and their caregivers actionable trial, treatment, and nutrition information — fast enough, cheap enough, and accurate enough to use daily — without hallucinating citations?**

The target user is one person — my friend in France who was recently diagnosed. Every design decision (location-aware trial search, European bias in the pre-loaded data, in-app auth that works on iPhone) traces back to that constraint.

---

## Architecture

```
User → Gradio 6 UI (in-app auth: password OR personal Anthropic key)
         │
         ▼
   Agent loop (als_agent_app.py)      — 4-phase workflow, manual streaming orchestration
         │                              - patient-framed system prompt (~3K tokens)
         │                              - mandatory 4-section per-treatment template
         │                              - STATISTICS RULE (translate p-values / ORs / HRs)
         ├─ stream_with_retry          - auto-fallback Sonnet 4.5 → Sonnet 4 on 429/529
         ├─ parallel_tool_execution    - asyncio.as_completed for faster slowest-path
         ├─ smart_cache                - query-normalized result cache
         ├─ citation_verifier          - post-synthesis NCT/PMID/DOI check (whitelist + HTTP)
         └─ MCPClientManager           - custom JSON-RPC subprocess client
              │
              ▼
   Six MCP servers (each a subprocess)
     ├─ aact_server        — PostgreSQL (579K trials) + Haversine proximity + intervention synonym expansion
     ├─ pubmed_server      — NCBI E-utilities (search + details)
     ├─ biorxiv_server     — website scraping (API has no search endpoint)
     ├─ llamaindex_server  — ChromaDB + fastembed (BAAI/bge-small-en-v1.5), lazy-loaded
     ├─ fetch_server       — web content with SSRF protection
     └─ clinicaltrials_links — curated trial fallback
```

### Custom components

- **`custom_mcp_client.py`** — a direct-subprocess JSON-RPC client that replaces `mcp.client.stdio`. The stdlib client has buffering and async/await bugs that caused silent truncations beyond 8KB; this one uses line-buffered I/O and a 60s timeout.
- **`parallel_tool_execution.py`** — uses `asyncio.as_completed` instead of `asyncio.gather` so progress is reported as each tool finishes, not at the end of the slowest.
- **`smart_cache.py`** — query normalization (case, stopwords, synonym folding) so `"gene therapy ALS"` and `"ALS gene therapy"` hit the same cache entry.
- **`llm_client.py`** — unified streaming client with automatic model fallback (Sonnet 4.5 → Sonnet 4 on 429/529), and exponential backoff retries. (Scaffolding for a SambaNova cost-optimization provider exists but the provider itself is unimplemented, so Anthropic is the only live backend.)
- **`citation_verifier.py`** — post-synthesis audit. Extracts every NCT/PMID/DOI from the model's response, checks them against a whitelist of IDs that actually appeared in tool results this session (deterministic hallucination detection), then verifies PMIDs/DOIs via E-utilities/doi.org as a fallback. Any citation not in the whitelist or not resolvable online gets a visible `⚠️ Citation verification` warning block appended to the response.
- **`chroma_sync.py`** — push/pull for RAG persistence. On boot: if HF Spaces persistent storage is empty, pull the latest snapshot from a private HF Dataset repo (`CHROMA_SYNC_REPO`); fall back to the git-committed seed. At runtime: upload after every N new indexes (default 5) and on graceful shutdown.
- **4-phase agent loop** in `als_agent_app.py` — explicit PLANNING/EXECUTING/REFLECTING/SYNTHESIS emitted to the UI with streaming, multi-iteration tool calling with message-history compression between iterations, and prompt-gated tool availability (no tools on synthesis turns).
- **Patient-framing system prompt** — mandatory 4-section per-treatment template (What it is / Where it stands / Who it's for / If you want to explore this), one-strike JARGON RULE with 25+ terms, STATISTICS RULE (translate all p-values / ORs / HRs into patient language), banned-phrase replacements ("may be considered" → "you could ask your ALS team about"), max-5 treatments per response, and geographic bias toward `USER_LOCATION` (default France) with ARSLA + named French ALS centers as action-step anchors.
- **AACT intervention synonym expansion** (`servers/aact_server.py::_INTERVENTION_SYNONYMS`) — an abbreviation table mapping ALCAR↔acetyl-L-carnitine, tofersen↔BIIB067, AMX0035↔Relyvrio, NurOwn↔MSC-NTF, CoQ10↔ubiquinone, and ~20 others. The intervention filter OR-searches all known forms so `search_als_trials(intervention="ALCAR")` actually finds trials stored under "Acetyl-l-carnitine".

### Pre-loaded RAG (seed snapshot, 676 items, ~10MB — grows at runtime)

The `chroma_db/` in the repo is an initial seed of ALS-relevant data, biased toward my friend's geography and clinical reality. At runtime the agent keeps indexing new papers; with HF Persistent Storage + Dataset sync configured, those additions persist across Space restarts (see "Known limitations" for the exact wiring).

| Category | Count | Examples |
|----------|-------|----------|
| Clinical trials | 103 | France, UK, Germany, NL, Italy, Spain, Scandinavia, DC/Baltimore, Morocco — includes Phase 2/3 acetyl-L-carnitine (ALCAR) trial (NCT06126315) |
| Nutrition papers | 106 | Omega-3, vitamin D, creatine, CoQ10, ketogenic, probiotics, Mediterranean, PEG feeding |
| Treatment papers | 89 | Tofersen, masitinib, edaravone, riluzole, antisense oligos |
| Gene therapy papers | 88 | AAV, CRISPR, SOD1, C9orf72, TDP-43, FUS, STMN2, ATXN2, miRNA |
| ALCAR research | 24 | Acetyl-L-carnitine mechanisms, neuroprotection, mitochondrial function |
| French SLA research | 64 | Pitié-Salpêtrière, ENCALS prognostic score, RespiStimALS, French Alps genetic cluster, Filnemus network |
| Drug-Approved | ~35 | Riluzole, edaravone, AMX0035/Relyvrio, sodium phenylbutyrate |
| Drug-Emerging | ~35 | NurOwn, reldesemtiv, arimoclomol, pridopidine, ravulizumab, CNM-Au8, CuATSM, ezogabine, verdiperstat, zilucoplan |
| Supportive Care | ~25 | NIV, tracheostomy, dysphagia, diaphragm pacing, cough assist, PEG timing |
| Biomarkers & Scales | ~25 | ALSFRS-R, neurofilament light chain, ENCALS/TRICALS scoring, FVC/SVC, muscle strength |
| Symptom Management | ~30 | Spasticity, pseudobulbar affect (Nuedexta), pain, depression, sialorrhea, fatigue, sleep |
| Rehab & Communication | ~20 | Exercise safety, stretching, AAC devices, eye tracking, BCI, voice banking |
| Caregiver & End-of-Life | ~15 | Caregiver burden, palliative care, hospice, advance care planning |
| Populations | ~20 | Bulbar-onset, juvenile ALS, slow progressors, cognitive decline, familial |
| Pathology | ~25 | TDP-43, glutamate excitotoxicity, oxidative stress, neuroinflammation |
| Genetics & Testing | ~15 | SOD1/C9orf72/FUS/TARDBP panels, familial counseling, penetrance |
| Digital Health | ~10 | Remote monitoring, wearable sensors, telemedicine |
| Alternative Therapies | ~10 | rTMS, cannabinoids, photobiomodulation |

---

## Design decisions and what I learned

**Single-agent with prompt discipline, not multi-agent.** I considered an orchestrator + specialist workers pattern for ~19 tools. Analysis showed the single-agent approach was already near its limit (system prompt bloat, forgotten synthesis phase, mixed tool-selection signals). The decision to stay single was deliberate: the target user is one person, not production scale. The pain of multi-agent coordination would've bought nothing for this use case. I documented the decision instead of building it.

**bioRxiv has no search API.** The official API only returns papers chronologically by date range. The original server fetched 100 random recent papers and filtered client-side — that's why queries for "ALS gene therapy" returned random neuroscience papers. I rewrote the server to scrape `biorxiv.org/search/` directly (same approach as the published JackKuo MCP server), which gives relevance-ranked keyword search. medRxiv blocks scraping with 403, so it's bioRxiv-only.

**fastembed beats BioBERT for this.** I started with `dmis-lab/biobert-base-cased-v1.2` assuming a biomedical model would be better. In testing, `BAAI/bge-small-en-v1.5` via fastembed beat it on every retrieval query — by 10-20 percentage points in cosine similarity — and is 6× smaller (68MB vs 469MB with the PyTorch dependency chain). Domain-specific models aren't always better; evaluation on your actual data matters.

**The forced-synthesis fallback was a prompt bug, not a model bug.** Early versions had an extra LLM call that kicked in when the synthesis phase didn't appear. Root cause: the reflection prompt said `(**✅ ANSWER:**)` while the system prompt checked for `✅ SYNTHESIS:`. Fixing the marker mismatch eliminated an entire API call per query.

**Claude overload errors need model fallback, not just retry.** When Sonnet 4.5 is overloaded (429/529), retrying Sonnet 4.5 doesn't help. The client now falls back to Sonnet 4 (same price, slightly less capable) transparently after retries exhaust on the primary. Cheaper than paying for nothing.

**Gradio 6 + SSR + auth is broken on HF Spaces, especially on mobile.** The built-in `auth=(user, pass)` parameter renders a login page that submits but doesn't redirect on iPhone Safari. `ssr_mode=False` is required for HF Spaces, and that combination with auth produced 500 errors on every request. I built an in-app login screen using regular Gradio components (Textbox + Button + State + visibility toggles) which uses the same mechanism as the chat UI — and therefore works wherever the chat works.

**Pre-loading is free, not "cheap".** ChromaDB + fastembed embeddings run entirely locally. The pre-load (grew from 385 → 676 items across several topic sweeps) cost $0 in API calls. The indexing takes a few minutes; the seed snapshot ships in the repo. For a single-user app this is dramatically better than relying on cold semantic search on every query.

**Token budget matters more than you'd think.** With 19 tool definitions per call and a 3K-token system prompt, a 3-iteration research query was sending 20K+ tokens per call. I condensed the prompt to ~1.2K, stopped sending tools on synthesis turns, and compressed older tool results to 500-char summaries between iterations. Real cost reduction, no quality loss. (The prompt later grew back to ~3K once patient-framing, anti-hallucination, and geography rules were added — but that bought real behavior changes, not just instructions the model ignores.)

**Prompt rules only work if they're deterministic and modeled.** Telling the model "explain jargon" with zero examples → no change. Telling it "explain jargon, here are 6 worked before/after pairs" → the model copies the pattern for those 6 terms but doesn't extrapolate. What actually landed: a **one-strike rule** ("any term a 16-year-old wouldn't know MUST be glossed inline — no exceptions") plus a **25-term explicit list** plus **4 positive replacement examples for banned phrases** ("may be considered" → "you could ask your ALS team about"). Same pattern for the action-step template: "AT LEAST two of" → zero compliance across 7 treatments; "every treatment MUST follow this four-section template" + a filled-in example → 100% compliance.

**Hallucinated NCT IDs were a real problem — the whitelist fix is free.** Early responses cited pattern-matched NCT numbers that looked plausible but didn't exist. The fix has two layers: (1) a prompt rule that every NCT/PMID/DOI must come from an actual tool result, and (2) a post-synthesis audit. Before any network call, the verifier checks the response's citations against a whitelist built from every ID that appeared in tool results during THIS conversation. IDs not on the whitelist are immediately flagged `🚫 not in search results`. This costs nothing (pure string matching) and catches the exact failure mode the prompt was supposed to prevent. PMIDs and DOIs get additional network verification via E-utilities and doi.org. NCTs can't be verified online (ClinicalTrials.gov blocks programmatic access) so the whitelist is the only signal — but since AACT is our authoritative source for NCTs, that's fine.

**The AACT intervention filter was broken for abbreviations.** `search_als_trials(intervention="ALCAR")` returned 0 — even though NCT06126315 exists in the database with intervention name "Acetyl-l-carnitine". The LIKE-match on the abbreviation never hit the canonical name. A naive fix would be to tell the prompt to "try synonyms"; the right fix is server-side expansion. `_INTERVENTION_SYNONYMS` is now a dict mapping each common abbreviation to all known forms, and the server OR-searches all of them. Same fix works for tofersen↔BIIB067, AMX0035↔Relyvrio, etc. — patient-facing abbreviation matching shouldn't be the LLM's job.

**Patient voice is training-bias inversion, not paraphrase.** Claude was trained heavily on medical literature, so its default register for medicine is "peer-reviewed paper." Telling it "write for a patient" gets you "write for a patient *using clinical vocabulary*." What actually flips the register: (a) a mandatory per-treatment template with explicit patient-frame labels (What it is / Where it stands / Who it's for / If you want to explore this — NOT Mechanism / Status / Eligibility / Trial), (b) banned-phrase replacements with the positive form provided, and (c) a STATISTICS RULE that forces translation of every p-value/OR/HR into patient language. The model can't default to "p=0.02" if the prompt requires "cut the risk of hospitalization by about two-thirds."

---

## What It Does (user-facing)

- **Find trials near you** — GPS proximity search via AACT + Haversine SQL. "Trials near Paris 300mi" returns 30+ results with distance, phase, interventions, sites, eligibility. Supports subtype filters (SOD1, C9orf72, FUS, TDP-43, bulbar, limb, familial, sporadic).
- **Monitor new trials** — trials posted or updated in the last N days, with the same subtype filter.
- **Search by drug or supplement name** — `search_als_trials(intervention="ALCAR")` works even though the database stores it as "Acetyl-l-carnitine"; the server expands ~25 common abbreviations (tofersen↔BIIB067, AMX0035↔Relyvrio, etc.).
- **Research supplements & treatments** — pre-loaded evidence on omega-3, vitamin D, creatine, ketogenic, tofersen, masitinib, gene therapies. Every treatment recommendation follows a mandatory patient-friendly template (What it is / Where it stands / Who it's for / action steps with named French ALS centers and ARSLA).
- **Search live literature** — PubMed + bioRxiv in parallel during a query, with semantic recall from the RAG cache.
- **Cited answers with automatic fabrication check** — every response's citations are audited after synthesis. Any NCT/PMID/DOI not seen in actual tool results gets a visible `⚠️ Citation verification` warning so the patient knows which items to double-check.

---

## Available Tools (18 tools across 6 MCP servers)

| Server | Tools |
|--------|-------|
| `aact` | `find_trials_near_me`, `check_new_als_trials`, `search_als_trials`, `get_trial_details` |
| `pubmed` | `search_pubmed`, `get_paper_details` |
| `biorxiv` | `search_preprints`, `get_preprint_details` |
| `llamaindex` (lazy-loaded) | `semantic_search`, `index_paper`, `list_indexed_papers`, `get_research_connections`, `upload_now` |
| `fetch` | `fetch_url` |
| `trials_links` | `get_known_als_trials`, `get_search_link`, `get_trial_link`, `get_trial_resources` |

---

## Known limitations

- **RAG relevance on structured records is mediocre.** Embedding models handle free-text abstracts well but struggle with trial records (fixed fields, similar phrasing). In practice one generic trial often ranks first regardless of query. This is why the direct DB tools (`find_trials_near_me`, SQL queries) are always called alongside semantic search, not as a replacement.
- **Runtime-indexed papers need a paid Persistent Storage add-on to survive restarts.** The committed `chroma_db/` is a seed. If deployed without configuration, new papers the agent discovers during a session live in `/tmp/chroma_db` (ephemeral) and are lost on restart. With `CHROMA_DB_PATH=/data/chroma_db` (pointing at a mounted HF Storage Bucket, ~$5/mo) + a `CHROMA_SYNC_REPO` Dataset repo + a write-scoped `HF_TOKEN`, additions are durable on the Bucket and backed up to the Dataset every `CHROMA_SYNC_BATCH_SIZE` indexes (default 5) and once more on graceful shutdown. All three configs are optional — without them the app still runs, just statelessly.
- **Single-agent architecture near its ceiling.** With 18 tools the system prompt is already doing a lot of work (~3K tokens of rules, templates, and anchors). Adding NCBI Gene + OMIM (as originally planned in `implementation_plan.md`) would likely require a refactor to orchestrator/specialist split.
- **Response latency for broad queries is 45–90s.** That's the trade-off of running PubMed + AACT + RAG + bioRxiv in parallel, then streaming a long synthesis. Fine for the intended use pattern (deliberate research queries, not chat banter).
- **In-app auth is basic.** No sessions, no rotating tokens, no rate-limiting per IP. Credentials live in environment variables. The brute-force lockout is in-process and resets when the Space restarts. Adequate for a 2-user tool, inadequate for anything wider.
- **This is a research aid, not medical advice.** The agent cites real trials and papers but can't assess eligibility, drug interactions, or clinical fit. Every response directs back to ALS specialists for actual decisions.

---

## Quick Start

### Prerequisites
- Python 3.10+
- Anthropic API key
- AACT database credentials ([register free](https://aact.ctti-clinicaltrials.org/users/sign_up))

### Install & run

```bash
git clone https://github.com/axemachina/ALSARA.git
cd ALSARA
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # fill in your keys
python als_agent_app.py # http://localhost:7860
```

### Secrets

Required:
- `ANTHROPIC_API_KEY` — Claude API key (used unless a user supplies their own via the login screen)
- `AACT_USER` / `AACT_PASSWORD` — AACT database credentials

Optional:
- `USER_LOCATION=France` — country/region of the primary user. The agent biases trial suggestions toward this location and pulls from a country-specific anchor list (ARSLA + named French ALS centers, when France). Default: `France`.
- `APP_USERNAME` / `APP_PASSWORD` — if set, the in-app login screen gates access
- `PUBMED_EMAIL` — increases PubMed rate limits 3 → 10 req/sec
- `ANTHROPIC_FALLBACK_MODEL` — fallback when primary is overloaded (default: `claude-sonnet-4-20250514`)
- `ENABLE_RAG=true` — enable semantic search over the pre-loaded snapshot (default `false`, set to `true` in the HF Space)
- `ENABLE_BIORXIV=true` — enable bioRxiv preprint search (default `false`)

Persistence (optional, HF Spaces):
- `CHROMA_DB_PATH=/data/chroma_db` — point at a mounted HF Storage Bucket for durability across restarts
- `CHROMA_SYNC_REPO=your-user/alsara-chroma` — private HF Dataset repo; chroma_db is pushed here as backup
- `HF_TOKEN=hf_...` — token with WRITE access to the Dataset repo
- `CHROMA_SYNC_BATCH_SIZE=5` — upload every N new indexed papers (default 5)

### Deploy to HuggingFace Spaces

1. Push to the Space repo (the committed `chroma_db/` seed ships with it — ~10MB)
2. Add the secrets above in Space Settings → Variables and secrets
3. Hardware: CPU Basic works; CPU Upgrade gives smoother cold starts
4. First boot takes ~60s (downloads the fastembed ONNX model once, then caches it)
5. For durable runtime indexing, enable **Storage Buckets** in Space Settings (~$5/mo), create a private Dataset repo (`hf repos create your-user/alsara-chroma --repo-type dataset --private`), and set the four persistence secrets listed above

---

## Project structure

```
ALSARA/
├── als_agent_app.py             # Gradio 6 UI + 4-phase agent loop + in-app auth
├── llm_client.py                # Anthropic client with retry + model fallback
├── chroma_sync.py               # HF Dataset push/pull for chroma_db persistence
├── custom_mcp_client.py         # Direct-subprocess MCP client (stdlib bypass)
├── parallel_tool_execution.py   # asyncio.as_completed orchestrator
├── refactored_helpers.py        # stream_with_retry, message builders, tool execution
├── citation_verifier.py         # Post-synthesis NCT/PMID/DOI audit (whitelist + HTTP verify)
├── query_classifier.py          # Research vs simple query routing
├── smart_cache.py               # Query-normalized response cache
├── chroma_db/                   # Seed RAG snapshot (~10MB, 676 items)
├── servers/
│   ├── aact_server.py           # 579K+ trials + Haversine proximity + subtype filters
│   ├── pubmed_server.py         # NCBI E-utilities (search + details, XML parsing)
│   ├── biorxiv_server.py        # Website scraping (API lacks search endpoint)
│   ├── llamaindex_server.py     # ChromaDB + fastembed wrapper, lazy-loaded
│   ├── fetch_server.py          # SSRF-protected web content fetching
│   ├── clinicaltrials_links.py  # Curated ALS trial fallback (no network deps)
│   └── elevenlabs_server.py     # Voice synthesis (disabled in current build)
├── shared/
│   ├── config.py                # Centralized config + rate limits
│   ├── cache.py                 # TTL cache primitive
│   ├── http_client.py           # Shared httpx client with connection pooling
│   └── utils.py                 # Formatters, rate limiter, error formatter
├── tests/                       # Unit + integration tests across servers
├── .env.example                 # Template for local / HF Secrets
├── .gitattributes               # LFS rules (HF Xet storage for binaries)
├── requirements.txt             # Pinned gradio==6.12.0, fastembed, etc.
├── claude.md                    # Tool usage guide for Claude Code dev env
├── implementation_plan.md       # Historical design doc (pre-shipping notes)
└── README.md
```

---

## Resources

### Data sources
- [AACT Database](https://aact.ctti-clinicaltrials.org/) — PostgreSQL mirror of ClinicalTrials.gov (Duke/FDA)
- [ClinicalTrials.gov](https://clinicaltrials.gov/) — original trial registry
- [PubMed E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/) — NCBI search API
- [bioRxiv](https://www.biorxiv.org/) / [medRxiv](https://www.medrxiv.org/) — preprint servers
- [EU Clinical Trials Register](https://www.clinicaltrialsregister.eu/) — European trial registry

### ALS-specific orgs and networks
- [ALS Association (US)](https://www.als.org/)
- [MND Association (UK)](https://www.mndassociation.org/)
- [ARSLA (France)](https://www.arsla.org/)
- [ALS Liga (Belgium)](https://www.alsliga.be/)
- [AISLA (Italy)](https://www.aisla.it/)
- [ALS Netherlands](https://www.als-centrum.nl/)
- [International Alliance of ALS/MND Associations](https://www.als-mnd.org/)
- [TRICALS](https://www.tricals.org/) — European ALS trial consortium
- [ENCALS](https://www.encals.eu/) — European Network for the Cure of ALS
- [Healey ALS Platform Trial](https://www.massgeneral.org/neurology/als/research/platform-trial)

### Tech
- [Model Context Protocol](https://modelcontextprotocol.io/) — the MCP spec this project is built on
- [Anthropic Claude](https://www.anthropic.com/) — Sonnet 4.5 / Sonnet 4 fallback
- [Gradio](https://www.gradio.app/docs/) — UI framework
- [LlamaIndex](https://www.llamaindex.ai/) / [ChromaDB](https://www.trychroma.com/) / [fastembed](https://github.com/qdrant/fastembed) — RAG stack
- [JackKuo bioRxiv MCP](https://github.com/JackKuo666/bioRxiv-MCP-Server) — reference implementation for the bioRxiv scraping approach

## License

MIT

---

**ALSARA — built for one person, shared because it might help others.**
