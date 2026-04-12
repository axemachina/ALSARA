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
sponsors: Sambanova, Anthropic, ElevenLabs, LlamaIndex
tags:
  - mcp-in-action-track-consumer
video: https://drive.google.com/drive/folders/14151Xo3eS4uFk3CoDbf-FzO8wGOoN61p?usp=drive_link
---


# ALSARA - ALS Agentic Research Agent

ALSARA (ALS Agentic Research Assistant) is an AI-powered research tool that intelligently orchestrates multiple biomedical databases to answer complex questions about ALS (Amyotrophic Lateral Sclerosis) research, treatments, and clinical trials in real-time.

Built with a 4-phase agentic workflow (Planning → Executing → Reflecting → Synthesis), ALSARA searches PubMed, 559,000+ clinical trials via AACT database, and provides voice accessibility for ALS patients - delivering comprehensive research in 5-10 seconds.

Built with Model Context Protocol (MCP), Gradio 6.x, and Anthropic Claude.

## Key Features

### Core Capabilities
- **4-Phase Agentic Workflow**: Intelligent planning, parallel execution, reflection with gap-filling, and comprehensive synthesis
- **Real-time Literature Search**: Query millions of PubMed peer-reviewed papers
- **Clinical Trial Discovery**: Access 559,000+ trials from AACT PostgreSQL database (primary) with ClinicalTrials.gov fallback
- **Voice Accessibility**: Text-to-speech using ElevenLabs for ALS patients with limited mobility
- **Smart Caching**: Query normalization with 24-hour TTL for instant similar query responses
- **Parallel Tool Execution**: 70% faster responses by running all searches simultaneously

### Advanced Features
- **Multi-Provider LLM Support**: Claude primary with SambaNova Llama 3.3 70B fallback
- **Query Classification**: Smart routing between simple answers and complex research
- **Rate Limiting**: 30 requests/minute per user with exponential backoff
- **Memory Management**: Automatic conversation truncation and garbage collection
- **Health Monitoring**: Uptime tracking, error rates, and tool usage statistics
- **Citation Tracking**: All responses include PMIDs, DOIs, NCT IDs, and source references
- **Web Scraping**: Fetch full-text articles with SSRF protection
- **Export Conversations**: Download chat history as markdown files

## Architecture

The system uses a sophisticated multi-layer architecture:

### 1. User Interface Layer
- **Gradio 6.x** web application with chat interface
- Real-time streaming responses
- Voice output controls
- Export and retry functionality

### 2. Agentic Orchestration Layer
**4-Phase Workflow:**
1. **PLANNING**: Agent strategizes which databases to query
2. **EXECUTING**: Parallel searches across all data sources
3. **REFLECTING**: Evaluates results, identifies gaps, runs additional searches
4. **SYNTHESIS**: Comprehensive answer with citations and confidence scoring

### 3. LLM Provider Layer
- **Primary**: Anthropic Claude (claude-sonnet-4-5-20250929)
- **Fallback**: SambaNova Llama 3.3 70B (free alternative)
- Smart routing based on query complexity

### 4. MCP Server Layer
Each server runs as a separate subprocess with JSON-RPC communication:

- **aact-server**: Primary clinical trials database (559,000+ trials)
- **pubmed-server**: PubMed literature search
- **fetch-server**: Web scraping with security hardening
- **elevenlabs-server**: Voice synthesis for accessibility
- **clinicaltrials_links**: Fallback trial links when AACT unavailable
- **llamaindex-server**: RAG/semantic search (optional)

**Technical Note:** Uses custom MCP client (`custom_mcp_client.py`) to bypass SDK bugs with proper async/await handling, line-buffered I/O, and automatic retry logic.

## Available Tools

The agent has access to specialized tools across 6 MCP servers:

### AACT Clinical Trials Database Tools (PRIMARY)

#### 1. `aact__search_aact_trials`
Search 559,000+ clinical trials from the AACT PostgreSQL database.

**Parameters:**
- `condition` (string, optional): Medical condition (default: "ALS")
- `status` (string, optional): Trial status - "recruiting", "active", "completed", "all"
- `intervention` (string, optional): Treatment/drug name
- `sponsor` (string, optional): Trial sponsor organization
- `phase` (string, optional): Trial phase (1, 2, 3, 4)
- `max_results` (integer, optional): Maximum results (default: 10)

**Returns:** Comprehensive trial data with NCT IDs, titles, status, phases, enrollment, and locations.

#### 2. `aact__get_aact_trial`
Get complete details for a specific clinical trial.

**Parameters:**
- `nct_id` (string, required): ClinicalTrials.gov NCT ID

**Returns:** Full trial information including eligibility, outcomes, interventions, and contacts.

---

### PubMed Literature Tools

#### 3. `pubmed__search_pubmed`
Search PubMed for peer-reviewed research papers.

**Parameters:**
- `query` (string, required): Search query (e.g., "ALS SOD1 therapy")
- `max_results` (integer, optional): Maximum results (default: 10)
- `sort` (string, optional): Sort by "relevance" or "date"

**Returns:** Papers with titles, abstracts, PMIDs, authors, and publication dates.

#### 4. `pubmed__get_paper_details`
Get complete details for a specific PubMed paper.

**Parameters:**
- `pmid` (string, required): PubMed ID

**Returns:** Full paper information including abstract, journal, DOI, and PubMed URL.

---

### Web Fetching Tools

#### 5. `fetch__fetch_url`
Fetch and extract content from web URLs with security hardening.

**Parameters:**
- `url` (string, required): URL to fetch
- `extract_text_only` (boolean, optional): Extract only text content (default: true)

**Returns:** Extracted webpage content with SSRF protection.

---

### Voice Accessibility Tools

#### 6. `elevenlabs__text_to_speech`
Convert research findings to audio for accessibility.

**Parameters:**
- `text` (string, required): Text to convert (max 2500 chars)
- `voice_id` (string, optional): Voice selection (default: Rachel - medical-friendly)
- `speed` (number, optional): Speech speed (0.5-2.0)

**Returns:** Audio stream for playback.

---

### Fallback Tools

#### 7. `clinicaltrials_links__get_known_als_trials`
Returns curated list of important ALS trials when AACT is unavailable.

#### 8. `clinicaltrials_links__get_search_link`
Generates direct ClinicalTrials.gov search URLs.

---

### Tool Usage Notes

- **Rate Limiting**: All tools respect API rate limits (PubMed: 3 req/sec)
- **Caching**: Results cached for 24 hours with smart query normalization
- **Connection Pooling**: AACT uses async PostgreSQL with 2-10 connections
- **Timeout Protection**: 90-second timeout with automatic retry
- **Security**: SSRF protection, input validation, content size limits

## Quick Start

### Prerequisites

- Python 3.10+ (3.12 recommended)
- Anthropic API key
- Git

### Installation

1. Clone the repository

```bash
git clone https://github.com/yourusername/als-research-agent.git
cd als-research-agent
```

2. Create virtual environment

```bash
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies

```bash
pip install -r requirements.txt
```

4. Set up environment variables

Create a `.env` file:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-xxx

# Recommended
ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
ELEVENLABS_API_KEY=xxx
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM  # Rachel voice

# Optional Features
ENABLE_RAG=false             # Enable semantic search (requires setup)
USE_FALLBACK_LLM=true        # Enable free SambaNova fallback
DISABLE_CACHE=false          # Disable smart caching

# Configuration
GRADIO_SERVER_PORT=7860
MAX_CONCURRENT_SEARCHES=3
RATE_LIMIT_PUBMED_DELAY=1.0
```

5. Run the application

```bash
python als_agent_app.py
```

or

```bash
./venv/bin/python3.12 als_agent_app.py 2>&1
```

The app will launch at http://localhost:7860

## Project Structure

```
als-research-agent/
├── README.md
├── requirements.txt
├── .env.example
├── als_agent_app.py             # Main Gradio application (1835 lines)
├── custom_mcp_client.py         # Custom MCP client implementation
├── llm_client.py                # Multi-provider LLM abstraction
├── query_classifier.py          # Research vs simple query detection
├── smart_cache.py               # Query normalization and caching
├── refactored_helpers.py        # Streaming and tool execution
├── parallel_tool_execution.py   # Concurrent search management
├── servers/
│   ├── aact_server.py           # AACT clinical trials database (PRIMARY)
│   ├── pubmed_server.py         # PubMed literature search
│   ├── fetch_server.py          # Web scraping with security
│   ├── elevenlabs_server.py     # Voice synthesis
│   ├── clinicaltrials_links.py  # Fallback trial links
│   └── llamaindex_server.py     # RAG/semantic search (optional)
├── shared/
│   ├── __init__.py
│   ├── config.py                # Centralized configuration
│   ├── cache.py                 # TTL-based caching
│   └── utils.py                 # Rate limiting and formatting
└── tests/
    ├── test_pubmed_server.py
    ├── test_aact_server.py
    ├── test_fetch_server.py
    ├── test_elevenlabs.py
    ├── test_integration.py
    ├── test_llm_client.py
    ├── test_performance.py
    └── test_workflow_*.py
```

## Usage Examples

### Example Queries

**Complex Research Questions:**
- "What are the latest gene therapy trials for SOD1 mutations with recent biomarker data?"
- "Compare antisense oligonucleotide therapies in Phase 2 or 3 trials"
- "Find recent PubMed papers on ALS protein aggregation from Japanese researchers"

**Clinical Trial Discovery:**
- "Active trials in Germany for bulbar onset ALS"
- "Recruiting trials for ALS patients under 40 with slow progression"
- "Phase 3 trials sponsored by Biogen or Ionis"

**Treatment Information:**
- "Compare efficacy of riluzole, edaravone, and AMX0035"
- "What combination therapies showed promise in 2024?"
- "Latest developments in stem cell therapy for ALS"

**Accessibility Features:**
- Click the voice icon to hear research summaries
- Adjustable speech speed for comfort
- Medical-friendly voice optimized for clarity

## Performance Characteristics

- **Typical Response Time**: 5-10 seconds for complex queries
- **Parallel Speedup**: 70% faster than sequential searching
- **Cache Hit Time**: <100ms for similar queries (24-hour TTL)
- **Concurrent Handling**: 4 requests in ~8 seconds
- **Tool Call Timeout**: 90 seconds with automatic retry
- **Memory Limit**: 50 messages per conversation (~8-50KB per message)

## Development

### Running Tests

```bash
# All tests
pytest tests/ -v

# Unit tests only
pytest tests/ -m "not integration"

# With coverage
pytest --cov=servers --cov-report=html

# Quick tests
./run_quick_tests.sh
```

### Adding New MCP Servers

1. Create new server file in `servers/`
2. Use FastMCP API to implement tools:

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-server")

@mcp.tool()
async def my_tool(param: str) -> str:
    """Tool description"""
    return f"Result: {param}"

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

3. Add server to `als_agent_app.py` in `setup_mcp_servers()`
4. Write tests in `tests/`

## Deployment

### Hugging Face Spaces

1. Create a Gradio Space
2. Push your code
3. Add secrets:
   - `ANTHROPIC_API_KEY` (required)
   - `ELEVENLABS_API_KEY` (for voice features)

### Docker

```bash
docker build -t als-research-agent .
docker run -p 7860:7860 \
  -e ANTHROPIC_API_KEY=your_key \
  -e ELEVENLABS_API_KEY=your_key \
  als-research-agent
```

### Cloud Deployment (Azure/AWS/GCP)

The application is containerized and ready for deployment on any cloud platform supporting Docker containers. See deployment guides for specific platforms.

## Troubleshooting

**MCP server not responding**
- Check Python path and virtual environment activation
- Verify all dependencies installed: `pip install -r requirements.txt`

**Rate limit exceeded**
- Add delays between requests
- Check Anthropic API quota
- Use `USE_FALLBACK_LLM=true` for free alternative

**Voice synthesis not working**
- Verify `ELEVENLABS_API_KEY` is set
- Check API quota at ElevenLabs dashboard
- Text may be too long (max 2500 chars)

**AACT database connection issues**
- Database may be under maintenance (Sunday 7 AM ET)
- Fallback to `clinicaltrials_links` server activates automatically

**Cache not working**
- Check `DISABLE_CACHE` is not set to true
- Verify `.cache/` directory has write permissions

## Resources

### ALS Research Organizations
- ALS Association: https://www.als.org/
- ALS Therapy Development Institute: https://www.als.net/
- Answer ALS Data Portal: https://dataportal.answerals.org/
- International Alliance of ALS/MND Associations: https://www.als-mnd.org/

### Data Sources
- PubMed E-utilities: https://www.ncbi.nlm.nih.gov/books/NBK25501/
- AACT Database: https://aact.ctti-clinicaltrials.org/
- ClinicalTrials.gov: https://clinicaltrials.gov/

### Technologies
- Model Context Protocol: https://modelcontextprotocol.io/
- Gradio Documentation: https://www.gradio.app/docs/
- Anthropic Claude: https://www.anthropic.com/
- ElevenLabs API: https://elevenlabs.io/

## Security & Privacy

- **No Patient Data Storage**: Conversations are not permanently stored
- **SSRF Protection**: Blocks access to private IPs and localhost
- **Input Validation**: Injection pattern detection and length limits
- **Rate Limiting**: Per-user request throttling
- **API Key Security**: All keys stored as environment variables

## License

MIT License - See LICENSE file for details

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for your changes
4. Ensure all tests pass (`pytest`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## Future Enhancements

### In Development
- **NCBI Gene Database**: Gene information and mutations
- **OMIM Integration**: Genetic disorder phenotypes
- **Protein Data Bank**: 3D protein structures
- **AlphaFold Database**: AI-predicted protein structures

### Planned Features
- **Voice Input**: Speech recognition for queries
- **Patient Trial Matching**: Personalized eligibility assessment
- **Research Trend Analysis**: Track emerging themes
- **Alert System**: Notifications for new trials/papers
- **Enhanced Export**: BibTeX, CSV, PDF formats
- **Multi-language Support**: Global accessibility
- **Drug Repurposing Module**: Identify potential ALS treatments
- **arXiv Integration**: Computational biology papers

## Acknowledgments

Built for the global ALS research community to accelerate the path to a cure.

Special thanks to:
- The MCP team for the Model Context Protocol
- Anthropic for Claude AI
- The open-source community for invaluable contributions

---

**ALSARA - Accelerating ALS research, one query at a time.**

For questions, issues, or contributions, please open an issue on GitHub.