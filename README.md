---
title: ALSARA - ALS Agentic Research Agent
emoji: 🧬
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: "6.0.0"
app_file: als_agent_app.py
license: mit
short_description: AI research assistant for ALS research & trials
pinned: false
sponsors: Sambanova, Anthropic, LlamaIndex
tags:
  - mcp-in-action-track-consumer
video: https://drive.google.com/drive/folders/14151Xo3eS4uFk3CoDbf-FzO8wGOoN61p?usp=drive_link
---


# ALSARA - ALS Agentic Research Agent

ALSARA is an AI-powered research tool that helps ALS patients and caregivers find clinical trials, treatments, and nutritional guidance by searching multiple biomedical databases in real-time.

Built with Model Context Protocol (MCP), Gradio 6.x, and Anthropic Claude.

## What It Does

- **Find trials near you** — search by city, ZIP code, or coordinates with GPS proximity matching
- **Monitor new trials** — check for newly posted or updated ALS trials in the last N days
- **Filter by ALS subtype** — SOD1, C9orf72, FUS, TDP-43, bulbar, limb, familial, sporadic
- **Research supplements** — evidence-based guidance on omega-3, vitamin D, creatine, and more
- **Search literature** — query PubMed and bioRxiv for peer-reviewed papers and preprints
- **Track treatments** — current status of tofersen, masitinib, dazucorilant, gene therapies

## Pre-loaded Data (385 items, instant results)

| Category | Count | Topics |
|----------|-------|--------|
| Clinical trials | 102 | France, DC/Baltimore, UK, Germany, NL, Italy, Spain, Scandinavia, Morocco |
| Nutrition papers | 106 | Omega-3, vitamin D, creatine, CoQ10, curcumin, probiotics, ketogenic diet |
| Treatment papers | 89 | Tofersen, masitinib, edaravone, riluzole, combination therapies |
| Gene therapy papers | 88 | AAV, CRISPR, SOD1, C9orf72, TDP-43, FUS, STMN2, ATXN2, miRNA |

## Architecture

**4-Phase Agentic Workflow:** Planning → Executing → Reflecting → Synthesis

**7 MCP Servers** (each runs as a subprocess):
- `aact-server` — 579K+ clinical trials with proximity search and subtype filtering
- `pubmed-server` — PubMed literature search
- `biorxiv-server` — bioRxiv preprint search (website scraping, relevance-ranked)
- `llamaindex-server` — RAG semantic search with fastembed (lightweight, no PyTorch)
- `fetch-server` — web scraping with SSRF protection
- `clinicaltrials-links` — curated ALS trials fallback

**LLM:** Claude Sonnet 4.5 primary, auto-fallback to Sonnet 4 on overload, with retry logic.

## Available Tools

### Trial Discovery
| Tool | Description |
|------|-------------|
| `aact__find_trials_near_me` | GPS proximity search — city, ZIP, or coordinates + radius + subtype filter |
| `aact__check_new_als_trials` | Trials posted/updated in last N days, with subtype filter |
| `aact__search_als_trials` | Search by status, phase, intervention |
| `aact__get_trial_details` | Full trial info: eligibility, outcomes, locations, interventions |

### Research
| Tool | Description |
|------|-------------|
| `pubmed__search_pubmed` | Search PubMed for peer-reviewed papers |
| `pubmed__get_paper_details` | Full paper details by PMID |
| `biorxiv__search_preprints` | Relevance-ranked bioRxiv preprint search |
| `biorxiv__get_preprint_details` | Preprint details by DOI |
| `fetch__fetch_url` | Fetch web content with security hardening |

### Semantic Search (RAG)
| Tool | Description |
|------|-------------|
| `llamaindex__semantic_search` | Search 385 pre-loaded papers/trials by meaning |
| `llamaindex__index_paper` | Add papers to persistent memory |
| `llamaindex__list_indexed_papers` | List all indexed items |

### Fallback
| Tool | Description |
|------|-------------|
| `trials_links__get_known_als_trials` | Curated list of important ALS trials |
| `trials_links__get_search_link` | Generate ClinicalTrials.gov search URLs |

## Quick Start

### Prerequisites
- Python 3.10+
- Anthropic API key
- AACT database credentials ([register free](https://aact.ctti-clinicaltrials.org/users/sign_up))

### Installation

```bash
git clone https://github.com/yourusername/ALSARA.git
cd ALSARA
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Configuration

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

Required secrets:
- `ANTHROPIC_API_KEY` — Claude API key
- `AACT_USER` / `AACT_PASSWORD` — AACT database credentials
- `APP_USERNAME` / `APP_PASSWORD` — login protection (optional)

### Run

```bash
python als_agent_app.py
```

Opens at http://localhost:7860

## Deploy to HuggingFace Spaces

1. Push code to your HF Space repo (including `chroma_db/`)
2. Set secrets in Space Settings:
   - `ANTHROPIC_API_KEY`
   - `AACT_USER`, `AACT_PASSWORD`
   - `APP_USERNAME`, `APP_PASSWORD`
   - `ENABLE_RAG=true`
   - `ENABLE_BIORXIV=true`
3. Use **CPU Upgrade** hardware (~$9/mo) for reliable performance

## Project Structure

```
ALSARA/
├── als_agent_app.py             # Main Gradio application
├── llm_client.py                # Multi-provider LLM with auto-fallback
├── custom_mcp_client.py         # Custom MCP client (bypasses SDK bugs)
├── parallel_tool_execution.py   # Concurrent tool execution
├── query_classifier.py          # Research vs simple query routing
├── smart_cache.py               # Query normalization and caching
├── chroma_db/                   # Pre-loaded RAG data (385 items)
├── servers/
│   ├── aact_server.py           # AACT trials + proximity search
│   ├── pubmed_server.py         # PubMed search
│   ├── biorxiv_server.py        # bioRxiv preprint search
│   ├── llamaindex_server.py     # RAG with fastembed
│   ├── fetch_server.py          # Web scraping
│   └── clinicaltrials_links.py  # Curated trial links
├── shared/
│   ├── config.py                # Centralized configuration
│   ├── cache.py                 # TTL-based caching
│   └── utils.py                 # Rate limiting, formatting
├── .env.example                 # Template for secrets
└── requirements.txt
```

## Security

- **Password auth** with brute-force lockout (5 attempts, 5-minute cooldown)
- **Auto-fallback** to Sonnet 4 when Sonnet 4.5 is overloaded
- **Retry logic** on API errors (429/529/503) with exponential backoff
- **SSRF protection** on web fetching
- **No patient data stored** — conversations are session-only

## Resources

- [ALS Association](https://www.als.org/)
- [AACT Database](https://aact.ctti-clinicaltrials.org/)
- [PubMed](https://pubmed.ncbi.nlm.nih.gov/)
- [ClinicalTrials.gov](https://clinicaltrials.gov/)
- [Model Context Protocol](https://modelcontextprotocol.io/)

## License

MIT

---

**ALSARA — Accelerating ALS research, one query at a time.**
