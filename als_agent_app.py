# als_agent_app.py
import gradio as gr
import asyncio
import json
import os
import logging
from pathlib import Path
from datetime import datetime, timedelta
import sys
import time
from typing import Optional, List, Dict, Any, Tuple, AsyncGenerator, Union
from collections import defaultdict
from dotenv import load_dotenv
import httpx
import base64
import tempfile
import re

# Load environment variables from .env file
load_dotenv()

# Add current directory to path for shared imports
sys.path.insert(0, str(Path(__file__).parent))
from shared import SimpleCache
from llm_client import UnifiedLLMClient
from smart_cache import SmartCache, DEFAULT_PREWARM_QUERIES
from services.registry import get_tool_schemas, call_tool as _registry_call_tool, flush_llamaindex

# Helper function imports for refactored code
from refactored_helpers import (
    stream_with_retry,
    execute_tool_calls,
    build_assistant_message
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log', mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Rate Limiter Class
class RateLimiter:
    """Rate limiter to prevent API overload"""

    def __init__(self, max_requests_per_minute: int = 30):
        self.max_requests_per_minute = max_requests_per_minute
        self.request_times = defaultdict(list)

    async def check_rate_limit(self, key: str = "default") -> bool:
        """Check if request is within rate limit"""
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)

        # Clean old requests
        self.request_times[key] = [
            t for t in self.request_times[key]
            if t > minute_ago
        ]

        # Check if under limit
        if len(self.request_times[key]) >= self.max_requests_per_minute:
            return False

        # Record this request
        self.request_times[key].append(now)
        return True

    async def wait_if_needed(self, key: str = "default"):
        """Wait if rate limit exceeded"""
        while not await self.check_rate_limit(key):
            await asyncio.sleep(2)  # Wait 2 seconds before retry

# Initialize rate limiter
rate_limiter = RateLimiter(max_requests_per_minute=30)

# Memory management settings
MAX_CONVERSATION_LENGTH = 50  # Maximum messages to keep in history
MEMORY_CLEANUP_INTERVAL = 300  # Cleanup every 5 minutes

async def cleanup_memory():
    """Periodic memory cleanup task"""
    while True:
        try:
            # Clean up expired cache entries
            tool_cache.cleanup_expired()
            smart_cache.cleanup() if smart_cache else None

            # Force garbage collection for large cleanups
            import gc
            collected = gc.collect()
            if collected > 0:
                logger.debug(f"Memory cleanup: collected {collected} objects")

        except Exception as e:
            logger.error(f"Error during memory cleanup: {e}")

        await asyncio.sleep(MEMORY_CLEANUP_INTERVAL)

# Start memory cleanup task
cleanup_task = None

# Track whether last response used research workflow (for voice button)
last_response_was_research = False

# Health monitoring
class HealthMonitor:
    """Monitor system health and performance"""

    def __init__(self):
        self.start_time = datetime.now()
        self.request_count = 0
        self.error_count = 0
        self.tool_call_count = defaultdict(int)
        self.response_times = []
        self.last_error = None

    def record_request(self):
        self.request_count += 1

    def record_error(self, error: str):
        self.error_count += 1
        self.last_error = {"time": datetime.now(), "error": str(error)[:500]}

    def record_tool_call(self, tool_name: str):
        self.tool_call_count[tool_name] += 1

    def record_response_time(self, duration: float):
        self.response_times.append(duration)
        # Keep only last 100 response times to avoid memory buildup
        if len(self.response_times) > 100:
            self.response_times = self.response_times[-100:]

    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status"""
        uptime = (datetime.now() - self.start_time).total_seconds()
        avg_response_time = sum(self.response_times) / len(self.response_times) if self.response_times else 0

        return {
            "status": "healthy" if self.error_count < 10 else "degraded",
            "uptime_seconds": uptime,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "error_rate": self.error_count / max(1, self.request_count),
            "avg_response_time": avg_response_time,
            "cache_size": tool_cache.size(),
            "rate_limit_status": f"{len(rate_limiter.request_times)} active keys",
            "most_used_tools": dict(sorted(self.tool_call_count.items(), key=lambda x: x[1], reverse=True)[:5]),
            "last_error": self.last_error
        }

# Initialize health monitor
health_monitor = HealthMonitor()

# Error message formatter
def format_error_message(error: Exception, context: str = "") -> str:
    """Format error messages with helpful suggestions"""

    error_str = str(error)
    error_type = type(error).__name__

    # Common error patterns and suggestions
    if "timeout" in error_str.lower():
        suggestion = """
**Suggestions:**
- Try simplifying your search query
- Break complex questions into smaller parts
- Check your internet connection
- The service may be temporarily overloaded - try again in a moment
        """
    elif "rate limit" in error_str.lower():
        suggestion = """
**Suggestions:**
- Wait a moment before trying again
- Reduce the number of simultaneous searches
- Consider using cached results when available
        """
    elif "connection" in error_str.lower() or "network" in error_str.lower():
        suggestion = """
**Suggestions:**
- Check your internet connection
- The external service may be temporarily unavailable
- Try again in a few moments
        """
    elif "invalid" in error_str.lower() or "validation" in error_str.lower():
        suggestion = """
**Suggestions:**
- Check your query for special characters or formatting issues
- Ensure your question is clear and well-formed
- Avoid using HTML or script tags in your query
        """
    elif "memory" in error_str.lower() or "resource" in error_str.lower():
        suggestion = """
**Suggestions:**
- The system may be under heavy load
- Try a simpler query
- Clear your browser cache and refresh the page
        """
    else:
        suggestion = """
**Suggestions:**
- Try rephrasing your question
- Break complex queries into simpler parts
- If the error persists, please report it to support
        """

    formatted = f"""
❌ **Error Encountered**

**Type:** {error_type}
**Details:** {error_str[:500]}
{f"**Context:** {context}" if context else ""}

{suggestion}

**Need Help?**
- Try the example queries in the sidebar
- Check the System Health tab for service status
- Report persistent issues on GitHub
    """

    return formatted.strip()

# Initialize the unified LLM client
# All provider logic is now handled inside UnifiedLLMClient
client = None  # Initialize to None for proper cleanup handling
try:
    client = UnifiedLLMClient()
    logger.info(f"LLM client initialized: {client.get_provider_display_name()}")
except ValueError as e:
    # Re-raise configuration errors with clear instructions
    logger.error(f"LLM configuration error: {e}")
    raise

# Model configuration
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
logger.info(f"Using model: {ANTHROPIC_MODEL}")

MAX_RESPONSE_TOKENS = min(int(os.getenv("MAX_RESPONSE_TOKENS") or "32000"), 64000)
logger.info(f"Max response tokens set to: {MAX_RESPONSE_TOKENS}")

# Global smart cache (24 hour TTL for research queries)
smart_cache = SmartCache(cache_dir=".cache", ttl_hours=24)

# Keep tool cache for tool results
tool_cache = SimpleCache(ttl=3600)

async def call_tool_cached(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Dispatch a tool call with caching and rate limiting."""
    cached_result = tool_cache.get(tool_name, arguments)
    if cached_result:
        return cached_result
    await rate_limiter.wait_if_needed(tool_name.split("__")[0])
    result = await _registry_call_tool(tool_name, arguments)
    tool_cache.set(tool_name, arguments, result)
    health_monitor.record_tool_call(tool_name)
    return result


def export_conversation(history: Optional[List[Any]]) -> Optional[Path]:
    """Export conversation to markdown format"""
    if not history:
        return None

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"als_conversation_{timestamp}.md"

    content = f"""# ALS Research Conversation
**Exported:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

"""

    for i, (user_msg, assistant_msg) in enumerate(history, 1):
        content += f"## Query {i}\n\n**User:** {user_msg}\n\n**Assistant:**\n{assistant_msg}\n\n---\n\n"

    content += f"""
*Generated by ALSARA - ALS Agentic Research Agent*
*Total interactions: {len(history)}*
"""

    filepath = Path(filename)
    filepath.write_text(content, encoding='utf-8')
    logger.info(f"Exported conversation to {filename}")

    return filepath


def filter_internal_tags(text: str) -> str:
    """Remove all internal processing tags from the output."""
    import re

    # Remove internal tags and their content with single regex
    text = re.sub(r'<(thinking|search_quality_reflection|search_quality_score)>.*?</\1>|<(thinking|search_quality_reflection|search_quality_score)>.*$', '', text, flags=re.DOTALL)

    # Remove wrapper tags but keep content
    text = re.sub(r'</?(result|answer)>', '', text)

    # Fix phase formatting - ensure consistent formatting
    # Add proper line breaks around phase headers
    # First normalize any existing phase markers to be on their own line
    phase_patterns = [
        # Fix incorrect formats (missing asterisks) first
        (r'(?<!\*)🎯\s*PLANNING:(?!\*)', r'**🎯 PLANNING:**'),
        (r'(?<!\*)🔧\s*EXECUTING:(?!\*)', r'**🔧 EXECUTING:**'),
        (r'(?<!\*)🤔\s*REFLECTING:(?!\*)', r'**🤔 REFLECTING:**'),
        (r'(?<!\*)✅\s*SYNTHESIS:(?!\*)', r'**✅ SYNTHESIS:**'),

        # Then ensure the markers are on new lines (if not already)
        (r'(?<!\n)(\*\*🎯\s*PLANNING:\*\*)', r'\n\n\1'),
        (r'(?<!\n)(\*\*🔧\s*EXECUTING:\*\*)', r'\n\n\1'),
        (r'(?<!\n)(\*\*🤔\s*REFLECTING:\*\*)', r'\n\n\1'),
        (r'(?<!\n)(\*\*✅\s*SYNTHESIS:\*\*)', r'\n\n\1'),

        # Then add spacing after them
        (r'(\*\*🎯\s*PLANNING:\*\*)', r'\1\n'),
        (r'(\*\*🔧\s*EXECUTING:\*\*)', r'\1\n'),
        (r'(\*\*🤔\s*REFLECTING:\*\*)', r'\1\n'),
        (r'(\*\*✅\s*SYNTHESIS:\*\*)', r'\1\n'),
    ]

    for pattern, replacement in phase_patterns:
        text = re.sub(pattern, replacement, text)

    # Clean up excessive whitespace while preserving intentional formatting
    text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces to single space
    text = re.sub(r'\n{4,}', '\n\n\n', text)  # Maximum 3 newlines
    text = re.sub(r'^\n+', '', text)  # Remove leading newlines
    text = re.sub(r'\n+$', '\n', text)  # Single trailing newline

    return text.strip()

def compress_messages_for_synthesis(messages: List[Dict], keep_last_n: int = 2) -> List[Dict]:
    """Compress older tool results in message history to reduce token usage.

    Keeps the system prompt, user query, and the last N message pairs intact.
    Truncates tool result content in older messages to summaries.
    """
    if len(messages) <= 4:  # system + user + assistant + tool_results = nothing to compress
        return messages

    compressed = []
    # Keep system prompt and original user query
    compressed.append(messages[0])  # system
    compressed.append(messages[1])  # first user message (may include history)

    # Find where the "keep" boundary is — keep the last keep_last_n*2 messages intact
    keep_from = max(2, len(messages) - keep_last_n * 2)

    for i in range(2, len(messages)):
        msg = messages[i]
        if i < keep_from:
            # Compress this message
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                # This is a tool_results message — truncate each result
                compressed_content = []
                for item in msg["content"]:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        content = item.get("content", "")
                        if isinstance(content, str) and len(content) > 500:
                            # Keep first 500 chars as summary
                            compressed_content.append({
                                **item,
                                "content": content[:500] + "\n[... truncated for context efficiency ...]"
                            })
                        else:
                            compressed_content.append(item)
                    else:
                        compressed_content.append(item)
                compressed.append({**msg, "content": compressed_content})
            elif msg.get("role") == "assistant" and isinstance(msg.get("content"), list):
                # Assistant message with tool_use blocks — keep tool_use, truncate text
                compressed_content = []
                for item in msg["content"]:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = item.get("text", "")
                        if len(text) > 300:
                            compressed_content.append({**item, "text": text[:300] + "\n[... truncated ...]"})
                        else:
                            compressed_content.append(item)
                    else:
                        compressed_content.append(item)  # Keep tool_use blocks intact
                compressed.append({**msg, "content": compressed_content})
            else:
                compressed.append(msg)
        else:
            # Keep recent messages intact
            compressed.append(msg)

    return compressed

def is_complex_query(message: str) -> bool:
    """Detect complex queries that might need more iterations"""
    complex_indicators = [
        "genotyping", "genetic testing", "multiple", "comprehensive",
        "all", "compare", "versus", "difference between", "systematic",
        "gene-targeted", "gene targeted", "list the main", "what are all",
        "complete overview", "detailed analysis", "in-depth"
    ]
    return any(indicator in message.lower() for indicator in complex_indicators)


def validate_query(message: str) -> Tuple[bool, str]:
    """Validate and sanitize user input to prevent injection and abuse"""
    # Check length
    if not message or not message.strip():
        return False, "Please enter a query"

    if len(message) > 2000:
        return False, "Query too long (maximum 2000 characters). Please shorten your question."

    # Check for potential injection patterns
    suspicious_patterns = [
        r'<script', r'javascript:', r'onclick', r'onerror',
        r'\bignore\s+previous\s+instructions\b',
        r'\bsystem\s+prompt\b',
        r'\bforget\s+everything\b',
        r'\bdisregard\s+all\b'
    ]

    for pattern in suspicious_patterns:
        if re.search(pattern, message, re.IGNORECASE):
            logger.warning(f"Suspicious pattern detected in query: {pattern}")
            return False, "Invalid query format. Please rephrase your question."

    # Check for excessive repetition (potential spam)
    words = message.lower().split()
    if len(words) > 10:
        # Check if any word appears too frequently
        word_freq = {}
        for word in words:
            word_freq[word] = word_freq.get(word, 0) + 1

        max_freq = max(word_freq.values())
        if max_freq > len(words) * 0.5:  # If any word is more than 50% of the query
            return False, "Query appears to contain excessive repetition. Please rephrase."

    return True, ""


async def als_research_agent(message: str, history: Optional[List[Dict[str, Any]]]) -> AsyncGenerator[str, None]:
    """Main agent logic with streaming response and error handling"""

    global last_response_was_research

    start_time = time.time()
    health_monitor.record_request()

    try:
        # Validate input first
        valid, error_msg = validate_query(message)
        if not valid:
            yield f"⚠️ **Input Validation Error:** {error_msg}"
            return

        logger.info(f"Received valid query: {message[:100]}...")  # Log first 100 chars

        # Truncate history to prevent memory bloat
        if history and len(history) > MAX_CONVERSATION_LENGTH:
            logger.info(f"Truncating conversation history from {len(history)} to {MAX_CONVERSATION_LENGTH} messages")
            history = history[-MAX_CONVERSATION_LENGTH:]

        # System prompt (condensed for token efficiency)
        enable_rag = os.getenv("ENABLE_RAG", "false").lower() == "true"

        from datetime import datetime as _dt
        _today = _dt.now().strftime("%B %d, %Y")
        _user_location = os.getenv("USER_LOCATION", "France").strip()

        base_prompt = f"""You are ALSARA, an ALS research assistant. ALL queries are in the context of ALS unless stated otherwise.

=== AUDIENCE ===
Your answer goes directly to **an ALS patient and their caregiver/family** — NOT to a clinician or researcher.

**JARGON RULE (one-strike).** Any noun a non-medical 16-year-old wouldn't immediately understand MUST be followed by a parenthetical or em-dash plain-language explanation in the SAME sentence. This applies universally — not just to the example terms below. The first time you use any of these (and any other medical term), gloss it inline:
- intracisternal, intrathecal, subcutaneous, intramuscular
- allogeneic ("from a donor"), autologous ("from your own body")
- antisense oligonucleotide, monoclonal antibody, biosimilar
- immunomodulator, neuroprotective, neuroinflammation
- lipid peroxidation, glutathione, mitochondrial, oxidative stress
- pharmacodynamic, biomarker, target engagement
- ALSFRS-R, FVC, SVC, NfL, GFAP, GPNMB, TBARS, 4-HNE
- Gold Coast Criteria, El Escorial Criteria (these are ALS diagnostic standards)
- Phase 1 / Phase 2 / Phase 3, dose-finding, open-label, double-blind, placebo-controlled
- sporadic vs familial, gene therapy, motor neuron

**STATISTICS RULE.** Any statistical value — p-value, odds ratio (OR), hazard ratio (HR), confidence interval (CI), relative risk, effect size, slope, adjusted/unadjusted comparisons — must either be TRANSLATED into patient language or DROPPED. Raw "p=0.0176" or "OR 0.27 (95% CI 0.10-0.71)" is noise to a patient. Translate to:
- ❌ "median survival 45 months vs 22 months, p=0.0176" → ✅ "ALCAR patients lived about 45 months on average, vs 22 months for placebo — essentially doubled their survival, and the difference was statistically solid"
- ❌ "adjusted OR 0.27, p<0.05" → ✅ "patients on ALCAR were roughly 3× more likely to be alive at 2 years"
- ❌ "slope -1.0 vs -1.4, p=0.0575" → ✅ "their ALS score declined a bit slower (around -1.0 points/month vs -1.4 for untreated), though the difference was borderline"
- ❌ "HR 0.36 (95% CI 0.15-0.85, p=0.02)" → ✅ "cut the risk of hospitalization or respiratory failure by about two-thirds"
When in doubt, report the raw numbers (45 vs 22 months) since those are patient-meaningful — just skip the p-values, ORs, and CIs.

Examples to copy the tone from:
- ❌ "PIKfyve inhibitor" → ✅ "a drug that blocks PIKfyve, an enzyme that helps clear broken proteins from nerve cells"
- ❌ "intracisternal delivery" → ✅ "injected directly into the spinal fluid at the base of the skull (one-time injection)"
- ❌ "allogeneic WJ-MSCs intrathecally" → ✅ "stem cells from a donor (allogeneic, meaning not your own), delivered into your spinal fluid through a lumbar puncture (intrathecal)"
- ❌ "ALSFRS-R" → ✅ "ALSFRS-R, the standard questionnaire your ALS team uses to score how the disease is progressing — higher is better"
- ❌ "Phase 1/2 dose-finding study" → ✅ "an early-stage trial (Phase 1/2) that's still figuring out the right dose"
- ❌ "GPNMB pharmacodynamic biomarker" → ✅ "GPNMB, a protein in blood and spinal fluid that goes up when the drug is doing what it's supposed to do — used as a sign the drug is working"

**TONE — banned phrases get positive replacements.** When you'd reach for these clinician phrases, use the patient version instead:
- ❌ "consider for patients with X" → ✅ "this might be relevant if you have X"
- ❌ "may be considered as adjunct to riluzole" → ✅ "you could ask your ALS team about adding this on top of riluzole"
- ❌ "well-tolerated" → ✅ "side effects were mild and not a reason to stop"
- ❌ "demonstrated potential efficacy" → ✅ "showed early signs of helping"
- ❌ "suitable candidates include Y" → ✅ "ask your ALS team whether Y applies to you"
- ❌ "limited statistical power" → ✅ "the study was too small to be sure"

If evidence is weak, say "the data is thin" or "we don't really know yet." Use "your ALS team" not "the clinician."

**MANDATORY PER-TREATMENT TEMPLATE.** Every treatment, drug, supplement, or trial you describe MUST follow this exact four-section template. No exceptions. No omissions. No alternative labels (do NOT use "Mechanism" / "Status" / "Eligibility" / "Sites" — those are clinician labels).

```
**N. <Treatment name>** 🟢/🟡/🔴 <one-word confidence>
- **What it is:** 1–2 plain-language sentences. Every technical term glossed inline (per the JARGON RULE above).
- **Where it stands:** Trial phase, approval status, AND current recruitment status — in plain words. If it's not actually available right now, say so first.
- **Who it's for:** Eligibility translated into "you might be eligible if you …" language. Mention any major exclusions (e.g., "won't work if you already have a tracheostomy").
- **If you want to explore this:**
  - Bring trial ID `NCTxxxx` (or PMID/DOI) to your next ALS clinic visit
  - The exact question to ask, in quotes (e.g., "Is the Paris site of DAZALS open to new patients?")
  - The CURRENT recruitment status at the nearest France/Europe site, by name (specific hospital + city)
  - Honest fallback if not accessible: compassionate use, a sister trial, the patient association (ARSLA), or "wait until next year"
```

**CONTRADICTION RULE.** If tool results contradict themselves (e.g., "recruiting" in one field, "active, not recruiting" in another), name the contradiction clearly in the "Where it stands" section and tell the patient what to verify. Do NOT cherry-pick the rosier option.

**NO REDUNDANT TAILS.** Do not end every single "If you want to explore this" block with the same "If unavailable, consult your local neurologist" or similar boilerplate. Say it ONCE — at the very end of the response, as a single footer line before the MEMORY UPDATE (e.g., "If none of these options are accessible to you, your local neurologist can review this list with you and help identify alternatives."). Per-treatment action blocks should be specific to that treatment, not copy-paste fallback text.

=== GEOGRAPHY (STRONG BIAS) ===
The user is based in **{_user_location}**. When listing clinical trials:
- Surface trials with sites in {_user_location} FIRST, then neighboring countries (UK, Germany, Belgium, Netherlands, Italy, Spain, Switzerland) SECOND, then the US/rest of world LAST.
- If a trial has a site in {_user_location} or nearby, name the specific hospital/city.
- If no relevant trials are in Europe, say so explicitly (don't bury the user in US-only options without flagging it).
- Use `find_trials_near_me` with {_user_location} coordinates to surface local options — don't just list whatever AACT returns.

**FRANCE ANCHOR LIST (use these in action-step blocks).** When pointing a French patient to next steps, name real-world entry points by name — not just trial IDs:
- **ARSLA** ([arsla.org](https://www.arsla.org/)) — the French ALS patient association. They maintain a directory of all French Centres de référence SLA and can help locate trials, connect families with those centers, and explain compassionate-use options. Mention them in at least one action-step block per response.
- **Named French ALS centers** (any of these is a reasonable next-visit destination for a French patient): Pitié-Salpêtrière (Paris), Hôpital Pierre Wertheimer (Lyon), CHU de Tours, CHU de Lille, La Timone (Marseille), CHU de Montpellier, CHU de Nice, CHU de Limoges, CHU de Bordeaux, CHU de Nancy.
- **Filnemus** — French rare neuromuscular disease consortium (worth mentioning for genetic/familial ALS questions).
- For trials with a Paris site, default to "Pitié-Salpêtrière" as the named center unless the trial data specifies a different Paris hospital.

**DO NOT include phone numbers, street addresses, or specific contact emails for French centers** (or any other centers). Those details change, and you cannot verify them — citing a wrong phone number is worse than not citing one. Point the patient to ARSLA's directory instead: "find your nearest Centre de référence SLA via ARSLA's directory at arsla.org." URL-only references to arsla.org are fine (they're verifiable).

**Pick ONE named center per response, not one per treatment.** If a response covers 5 supplements or trials, don't rotate through 5 different French centers as if each supplement is tied to a specific one. Either name one default center (Pitié-Salpêtrière unless the patient's question suggests otherwise) in a single footer, or name the center that's actually tied to the specific trial's French site.

CURRENT DATE: {_today}
- NEVER write a date later than today. If a tool result contains a date that seems from the future, it's a data timestamping quirk — do not amplify it.
- "Last 6 months" means the 180 days BEFORE today, not any month after today.

ANTI-FABRICATION RULES (strict):
- Every NCT ID, PMID, or DOI you cite MUST come from an actual tool result in this conversation. Do NOT write "NCT07XXXXXX" or similar plausible-looking IDs from memory.
- If you want to reference a trial or paper you didn't verify via tools, either call `get_trial_details` / `get_paper_details` to confirm it first, or write "(not independently verified)" beside it.
- Every cited paper must include a URL so the user can check it: `https://pubmed.ncbi.nlm.nih.gov/PMID/` for PMIDs, `https://clinicaltrials.gov/study/NCTID` for trials, `https://doi.org/DOI` for preprints.
- If you are uncertain about a specific detail (year, author, result), say "uncertain" — do not invent.

SEARCH RULES: ALWAYS include "ALS" or "amyotrophic lateral sclerosis" in every search query.

=== WORKFLOW (REQUIRED FOR EVERY RESEARCH QUERY) ===

Follow these phases in order. Each phase marker must be bold on its own line (e.g., **🎯 PLANNING:**).

1. **🎯 PLANNING:** Outline your search strategy — which databases, search terms, and prioritization."""

        if enable_rag:
            base_prompt += """
   Start with semantic_search for cached context, but ALWAYS also search PubMed and/or AACT — never rely on cached data alone."""

        base_prompt += """

2. **🔧 EXECUTING:** Run your planned searches. You MUST search at least 2 sources in parallel:
   - ALWAYS search PubMed for peer-reviewed literature
   - For treatment/drug queries: ALSO search AACT trials (search_als_trials or find_trials_near_me)
   - RAG semantic_search is supplementary — never use it as your only source

3. **🤔 REFLECTING:** Evaluate results. If gaps remain, do additional searches within this phase (don't restart the workflow)."""

        if enable_rag:
            base_prompt += """
   Index significant papers as you go via llamaindex__index_paper (title, abstract snippet, authors, doi, year, url, finding)."""

        base_prompt += """

4. **✅ SYNTHESIS:** REQUIRED final section. The literal `**✅ SYNTHESIS:**` header MUST appear on its own line. The answer section MUST include:
   - **Opening sentence: lead with evidence, not bleakness.** This is a patient, not a meta-analysis. Do NOT open with "The evidence is disappointing" or "Most treatments have failed" — even when that's arguably true. Instead: lead with what DOES have evidence (even if thin), THEN cover what's been tried and failed. A good opening: "A few nutritional approaches have real evidence worth knowing about — here they are, followed by the ones that sounded promising but didn't pan out." If nothing at all has positive evidence, say "No approved treatments have shown strong benefit yet, but several are in active trials — here's what's currently being tested."
   - Direct answer to the question
   - **Maximum 5 detailed treatment/trial entries.** If you found more, list the top 5 and end with: "I found N more candidates — ask me about [topic A] or [topic B] if you want details on those." Patients don't read past 5.
   - **Ordering: positive/promising evidence FIRST, negative/failed second, experimental/unknown last.** Leading with four red-flagged "not recommended" entries demoralizes the patient and is often factually incomplete (you probably missed the positive-signal interventions — see the OPEN-ENDED query rule in CLINICAL TRIALS).
   - Each treatment/trial entry MUST follow the four-section per-treatment template defined in the AUDIENCE section (What it is / Where it stands / Who it's for / If you want to explore this).
   - Numbered citations [1], [2] with clickable URLs (PubMed: https://pubmed.ncbi.nlm.nih.gov/PMID/, trials: https://clinicaltrials.gov/study/NCTID)
   - Confidence tags on major claims: 🟢 High (multiple peer-reviewed studies), 🟡 Moderate (limited/preprint), 🔴 Low (single study/theoretical) — apply per claim, not just in a final summary
   - If searches failed: state limitations and provide knowledge-based answer
   - End with one or two suggested follow-up questions the patient could ask
   - Do NOT add a "Clinical Considerations" / "Most accessible for X" / "Best for Y" comparison section — those are clinician summaries. The per-treatment "Who it's for" already covers eligibility from the patient angle."""

        if enable_rag:
            base_prompt += """

5. **📚 MEMORY UPDATE:** REQUIRED final line. The literal `**📚 MEMORY UPDATE:**` header must appear on its own line, followed by a ONE-LINE honest summary. Use **"Reviewed"** if you only fetched papers/trials this session; use **"Indexed"** ONLY if you actually called `llamaindex__index_paper` to save them to long-term memory. Format: `Reviewed N papers | M trials | Topic: [topic]` OR `Indexed N new papers | Reviewed M papers | Topic: [topic]` if you indexed any. Do NOT say "Indexed" when you didn't call the index tool — it's misleading."""

        base_prompt += """

=== KEY RULES ===
- Each phase appears EXACTLY ONCE. Never repeat or restart the workflow.
- NEVER invent citations. Only cite papers actually found via search tools.
- Prioritize recent research (2023-2025). Note preprints are NOT peer-reviewed.
- Use search result abstracts for synthesis. Only fetch full details for top 5-7 most relevant papers.
- If searches return nothing: broaden terms, try synonyms, then state what was tried.

=== CLINICAL TRIALS ===
- LOCATION SEARCH: aact__find_trials_near_me — find trials near a city, ZIP code, or coordinates. Supports radius_miles and subtype filters (SOD1, C9orf72, bulbar, limb, familial, sporadic). USE THIS for any location-based trial query.
- NEW TRIALS: aact__check_new_als_trials — find trials posted or updated in the last N days. Supports subtype filter.
- GENERAL SEARCH: aact__search_als_trials — search by status, phase, intervention. Use uppercase status: RECRUITING, COMPLETED, etc.
- FALLBACK: trials_links__get_known_als_trials — curated list of important ALS trials.

IMPORTANT LOCATION RULES:
- For ANY location-based trial query, use ONLY find_trials_near_me. Do NOT also call search_als_trials with a location — it will return 0 results for countries/regions.
- For "Europe" queries: find_trials_near_me with latitude=48.86, longitude=2.35 (Paris), radius_miles=500, max_results=30.
- For "USA" / "U.S.A." / "North America" queries: find_trials_near_me with latitude=39.83, longitude=-98.58 (geographic center of US), radius_miles=500, max_results=30. For East Coast: latitude=38.9, longitude=-77.0 (DC), radius_miles=500. For North America add a second search with latitude=45.5, longitude=-73.6 (Montreal), radius_miles=500 to cover Canada.
- For specific countries: find_trials_near_me with the capital city coordinates and radius_miles=300.
- For US regions: find_trials_near_me with city name or ZIP code, radius_miles=200.
- search_als_trials is ONLY for non-location queries (e.g., filter by phase, intervention, status).

NAMED-INTERVENTION RULE (mandatory):
When the user names a specific drug, supplement, gene, or intervention (e.g., "ALCAR", "acetyl-L-carnitine", "tofersen", "vitamin D", "stem cells", "masitinib", "edaravone"), the EXECUTING phase MUST include `search_als_trials(intervention="<name>")` — even if PubMed and semantic_search are also called. PubMed alone will miss trials that haven't published results yet.
- The server already expands common synonyms (ALCAR ↔ acetyl-L-carnitine, tofersen ↔ BIIB067, AMX0035 ↔ Relyvrio, NurOwn ↔ MSC-NTF, CoQ10 ↔ ubiquinone, etc.) — you don't need to manually try every variant.
- **If `status="RECRUITING"` (the default) returns 0, ALSO try `status="ACTIVE_NOT_RECRUITING"` and `status="COMPLETED"`.** A drug may have completed trials with published results even if no recruiting trial is currently open — this is still useful for the patient to understand the drug's track record. Always say in the response which status returned the result so the patient knows whether they can join.

OPEN-ENDED SUPPLEMENT/TREATMENT QUERIES (mandatory coverage):
When the user asks an open-ended question like "what supplements are recommended", "best treatments for ALS", "what should I try", or similar — do NOT only list whatever PubMed surfaces. You MUST explicitly search for each of these **known-signal interventions** (because missing a supplement with positive evidence is worse than listing too many):
- `acetyl-L-carnitine` (ALCAR) — 2013 Beghi RCT doubled median survival; NCT06126315 is actively recruiting as a Phase 2/3 confirmatory trial
- `omega-3` or `DHA` — DHA has neuroprotective signals; EPA may be harmful — this nuance matters
- `high caloric` or `fat-rich` (search PubMed for "high caloric ALS" or "fat-rich ALS") — 2022 RCT (PMID 35022317) showed survival benefit from high-caloric/fatty supplementation
- `vitamin D` — mixed/negative evidence but commonly asked about
- `creatine` — negative trials but a high-awareness supplement
- `CoQ10` (ubiquinone) — negative trials but frequently asked about

**Ordering rule for open-ended queries**: in the synthesis, list supplements with POSITIVE or PROMISING evidence FIRST (ALCAR, omega-3/DHA, high-caloric supplementation), then the ones tried-and-failed. Leading with four red-flagged "not recommended" entries sends a demoralizing signal that's also factually incomplete.

=== SELF-CORRECTION ===
If zero results: broaden terms, try synonyms, search related concepts. State what you tried.
"""

        # Add enhanced instructions for Llama models to improve thoroughness
        if client.is_using_llama_primary():
            llama_enhancement = """

ENHANCED SEARCH REQUIREMENTS FOR COMPREHENSIVE RESULTS:
You MUST follow this structured approach for EVERY research query:

=== MANDATORY SEARCH PHASES ===
Phase 1 - Comprehensive Database Search (ALL databases REQUIRED):
□ Search PubMed with multiple keyword variations
□ Search AACT database for clinical trials
□ Use at least 3-5 different search queries per database

Phase 2 - Strategic Detail Fetching (BE SELECTIVE):
□ Get paper details for the TOP 5-7 most relevant PubMed results
□ Get trial details for the TOP 3-4 most relevant clinical trials
□ ONLY fetch details for papers that are DIRECTLY relevant to the query
□ Use search result abstracts to prioritize which papers need full details

Phase 3 - Synthesis Requirements:
□ Include ALL relevant papers found (not just top 3-5)
□ Organize by subtopic or treatment approach
□ Provide complete citations with URLs

MINIMUM SEARCH STANDARDS:
- For general queries: At least 10-15 total searches across all databases
- For specific treatments: At least 5-7 searches per database
- For comprehensive reviews: At least 15-20 total searches
- NEVER stop after finding just 2-3 results

EXAMPLE SEARCH PATTERN for "gene therapy ALS":
1. pubmed__search_pubmed: "gene therapy ALS"
2. pubmed__search_pubmed: "AAV ALS treatment"
3. pubmed__search_pubmed: "SOD1 gene therapy"
4. pubmed__search_pubmed: "C9orf72 gene therapy"
5. pubmed__search_pubmed: "viral vector ALS"
# 6. biorxiv__search_preprints: (temporarily unavailable)
# 7. biorxiv__search_preprints: (temporarily unavailable)
6. aact__search_aact_trials: condition="ALS", intervention="gene therapy"
7. aact__search_aact_trials: condition="ALS", intervention="AAV"
10. [Get details for ALL results found]
11. [Web fetch for recent developments]

CRITICAL: Thoroughness is MORE important than speed. Users expect comprehensive results."""

            system_prompt = base_prompt + llama_enhancement
            logger.info("Using enhanced prompting for Llama model to improve search thoroughness")
        else:
            # Use base prompt directly for Claude
            system_prompt = base_prompt

        # Import query classifier
        from query_classifier import QueryClassifier

        # Classify the query to determine processing mode
        classification = QueryClassifier.classify_query(message)
        processing_hint = QueryClassifier.get_processing_hint(classification)
        logger.info(f"Query classification: {classification}")

        # Check smart cache for similar queries first
        cached_result = smart_cache.find_similar_cached(message)
        if cached_result:
            logger.info(f"Smart cache hit for query: {message[:50]}...")
            yield "🎯 **Using cached result** (similar query found)\n\n"
            yield cached_result
            return

        # Check if this is a high-frequency query with special config
        high_freq_config = smart_cache.get_high_frequency_config(message)
        if high_freq_config:
            logger.info(f"High-frequency query detected with config: {high_freq_config}")
            # Note: We could use optimized search terms or Claude here
            # For now, just log it and continue with normal processing

        # Get available tools
        tools = get_tool_schemas()

        # Check if this is a simple query that doesn't need research
        if not classification['requires_research']:
            # Simple query - skip the full research workflow
            logger.info(f"Simple query detected - using direct response mode: {classification['reason']}")

            # Mark that this response won't use research workflow (disable voice button)
            global last_response_was_research
            last_response_was_research = False

            # Use a simplified prompt for non-research queries
            simple_prompt = """You are an AI assistant for ALS research questions.
For this query, provide a helpful, conversational response without using research tools.
Keep your response friendly and informative."""

            # For simple queries, just make one API call without tools
            messages = [
                {"role": "system", "content": simple_prompt},
                {"role": "user", "content": message}
            ]

            # Display processing hint
            yield f"{processing_hint}\n\n"

            # Single API call for simple response (no tools)
            async for response_text, tool_calls, provider_used in stream_with_retry(
                client=client,
                messages=messages,
                tools=None,  # No tools for simple queries
                system_prompt=simple_prompt,
                max_retries=2,
                model=ANTHROPIC_MODEL,
                max_tokens=2000,  # Shorter responses for simple queries
                stream_name="simple response"
            ):
                yield response_text

            # Return early - skip all the research phases
            return

        # Research query - use full workflow with tools
        logger.info(f"Research query detected - using full workflow: {classification['reason']}")

        # Mark that this response will use research workflow (enable voice button)
        last_response_was_research = True
        yield f"{processing_hint}\n\n"

        # Build messages for research workflow
        messages = [
            {"role": "system", "content": system_prompt}
        ]

        # Add history (remove Gradio metadata)
        if history:
            # Only keep 'role' and 'content' fields from messages
            for msg in history:
                if isinstance(msg, dict):
                    messages.append({
                        "role": msg.get("role"),
                        "content": msg.get("content")
                    })
                else:
                    messages.append(msg)
        
        # Add current message
        messages.append({"role": "user", "content": message})
        
        # Initial API call with streaming using helper function
        full_response = ""
        tool_calls = []
        # Accumulate every tool result string for the post-synthesis citation verifier
        all_tool_result_texts: list = []

        # Use the stream_with_retry helper to handle all retry logic
        provider_used = "Anthropic Claude"  # Track which provider
        async for response_text, current_tool_calls, provider_used in stream_with_retry(
            client=client,
            messages=messages,
            tools=tools,
            system_prompt=system_prompt,
            max_retries=2,  # Increased from 0 to allow retries
            model=ANTHROPIC_MODEL,
            max_tokens=MAX_RESPONSE_TOKENS,
            stream_name="initial API call"
        ):
            full_response = response_text
            tool_calls = current_tool_calls
            # Apply single-pass filtering when yielding
            # Optionally show provider info when using fallback
            if provider_used != "Anthropic Claude" and response_text:
                yield f"[Using {provider_used}]\n{filter_internal_tags(full_response)}"
            else:
                yield filter_internal_tags(full_response)
        
        # Handle recursive tool calls (agent may need multiple searches)
        tool_iteration = 0

        # Adjust iteration limit based on query complexity
        if is_complex_query(message):
            max_tool_iterations = 5
            logger.info("Complex query detected - allowing up to 5 iterations")
        else:
            max_tool_iterations = 3
            logger.info("Standard query - allowing up to 3 iterations")

        while tool_calls and tool_iteration < max_tool_iterations:
            tool_iteration += 1
            logger.info(f"Tool iteration {tool_iteration}: processing {len(tool_calls)} tool calls")

            # No need to re-yield the planning phase - it was already shown

            # Build assistant message using helper
            assistant_content = build_assistant_message(
                text_content=full_response,
                tool_calls=tool_calls
            )

            messages.append({
                "role": "assistant",
                "content": assistant_content
            })
            
            # Show working indicator for long searches
            num_tools = len(tool_calls)
            if num_tools > 0:
                working_text = f"\n⏳ **Searching {num_tools} database{'s' if num_tools > 1 else ''} in parallel...** "
                if num_tools > 2:
                    working_text += f"(this typically takes 30-45 seconds)\n"
                elif num_tools > 1:
                    working_text += f"(this typically takes 15-30 seconds)\n"
                else:
                    working_text += f"\n"
                full_response += working_text
                yield filter_internal_tags(full_response)  # Show working indicator immediately

            # Execute tool calls in parallel (results arrive via as_completed for faster reporting)
            from parallel_tool_execution import execute_tool_calls_parallel
            progress_text, tool_results_content = await execute_tool_calls_parallel(
                tool_calls=tool_calls,
                call_mcp_tool_func=call_tool_cached
            )

            # Add progress text to full response and yield accumulated content
            full_response += progress_text
            if progress_text:
                yield filter_internal_tags(full_response)

            # Add single user message with ALL tool results
            messages.append({
                "role": "user",
                "content": tool_results_content
            })

            # Track raw tool result text for the citation verifier whitelist
            for item in tool_results_content:
                if isinstance(item, dict) and isinstance(item.get("content"), str):
                    all_tool_result_texts.append(item["content"])

            # Smart reflection: Only add reflection prompt if results seem incomplete
            needs_reflection = False  # Default for tool_iteration > 1
            if tool_iteration == 1:
                # First iteration - use normal workflow with reflection
                # Check confidence indicators in tool results
                results_text = str(tool_results_content).lower()

                # Indicators of low confidence/incomplete results
                low_confidence_indicators = [
                    'no results found', '0 results', 'no papers',
                    'no trials', 'limited', 'insufficient', 'few results'
                ]

                # Indicators of high confidence/complete results
                high_confidence_indicators = [
                    'recent study', 'multiple studies', 'clinical trial',
                    'systematic review', 'meta-analysis', 'significant results'
                ]

                # Count confidence indicators
                low_conf_count = sum(1 for ind in low_confidence_indicators if ind in results_text)
                high_conf_count = sum(1 for ind in high_confidence_indicators if ind in results_text)

                # Calculate total results found across all tools
                import re
                result_numbers = re.findall(r'(\d+)\s+(?:results?|papers?|studies|trials?)', results_text)
                total_results = sum(int(n) for n in result_numbers) if result_numbers else 0

                # Decide if reflection is needed - more aggressive skipping for performance
                needs_reflection = (
                    low_conf_count > 1 or  # Only if multiple low-confidence indicators
                    (high_conf_count == 0 and total_results < 10) or  # No high confidence AND few results
                    total_results < 3  # Almost no results at all
                )

                if needs_reflection:
                    reflection_prompt = [
                        {"type": "text", "text": "\n\nEvaluate your results. If gaps remain, search more within a **🤔 REFLECTING:** phase. When ready, you MUST provide **✅ SYNTHESIS:** with your complete answer. Always end with synthesis."}
                    ]
                    messages.append({
                        "role": "user",
                        "content": reflection_prompt
                    })
                    logger.info(f"Smart reflection triggered (low_conf:{low_conf_count}, high_conf:{high_conf_count}, results:{total_results})")
                else:
                    # High confidence - skip reflection and go straight to synthesis
                    logger.info(f"Skipping reflection - high confidence (low_conf:{low_conf_count}, high_conf:{high_conf_count}, results:{total_results})")
                    synthesis_prompt = [
                        {"type": "text", "text": (
                            "\n\nResults look comprehensive. Now produce the final answer with these MANDATORY rules:\n"
                            "1. Start with the header `**✅ SYNTHESIS:**` on its own line\n"
                            "2. EVERY treatment/trial entry MUST follow the four-section per-treatment template from the AUDIENCE section: **What it is** / **Where it stands** / **Who it's for** / **If you want to explore this** (with NCT ID + question to ask + named French center + fallback). Do NOT use 'Mechanism' / 'Status' / 'Eligibility' / 'Sites' as labels.\n"
                            "3. Maximum 5 treatments. If more, end the list with: 'I found N more — ask me about [X] or [Y] for those.'\n"
                            "4. Use confidence tags per claim: 🟢 / 🟡 / 🔴 . Apply the JARGON RULE inline (gloss every technical term).\n"
                            "5. End with `**📚 MEMORY UPDATE:**` on its own line. Use 'Reviewed N papers / M trials' — do NOT say 'Indexed' unless you actually called llamaindex__index_paper.\n"
                            "6. Do NOT add a 'Clinical Considerations' or 'Most accessible for X' summary section after the treatments.\n"
                        )}
                    ]
                    messages.append({
                        "role": "user",
                        "content": synthesis_prompt
                    })
            else:
                # Subsequent iterations (tool_iteration > 1) — the agent already
                # emitted PLANNING/EXECUTING/REFLECTING on iteration 1. Don't
                # repeat those, but DO emit SYNTHESIS + MEMORY UPDATE markers
                # for the final answer.
                logger.info(f"Iteration {tool_iteration}: finalizing with synthesis + memory update markers")
                update_prompt = [
                    {"type": "text", "text": (
                        "\n\nYou now have all the information you need. Produce the FINAL answer (do NOT redo planning/executing/reflecting):\n"
                        "1. Start with `**✅ SYNTHESIS:**` on its own line\n"
                        "2. EVERY treatment/trial MUST use the four-section per-treatment template: **What it is** / **Where it stands** / **Who it's for** / **If you want to explore this** (with NCT/PMID + question to ask + named French center via ARSLA/Pitié-Salpêtrière/etc + fallback). Do NOT use 'Mechanism' / 'Status' / 'Eligibility' as labels.\n"
                        "3. Maximum 5 treatments. If more found, end the list with: 'I found N more — ask me about [X] or [Y].'\n"
                        "4. Confidence tags 🟢 / 🟡 / 🔴 per claim. Apply JARGON RULE inline.\n"
                        "5. End with `**📚 MEMORY UPDATE:**` and an honest summary ('Reviewed N papers / M trials' — only 'Indexed' if you actually called llamaindex__index_paper).\n"
                        "6. Do NOT add a 'Clinical Considerations' / 'Most accessible for X' / 'Best for Y' comparison section.\n"
                    )}
                ]
                messages.append({
                    "role": "user",
                    "content": update_prompt
                })

            # Compress older messages to reduce token usage before synthesis call
            messages = compress_messages_for_synthesis(messages, keep_last_n=3)

            # Second API call with tool results (with retry logic)
            logger.info("Starting synthesis API call...")
            logger.info(f"Messages array has {len(messages)} messages (after compression)")
            logger.info(f"Last 3 messages: {json.dumps([{'role': m.get('role'), 'content_type': type(m.get('content')).__name__, 'content_len': len(str(m.get('content')))} for m in messages[-3:]], indent=2)}")
            # Log the actual tool results content
            logger.info(f"Tool results content ({len(tool_results_content)} items): {json.dumps(tool_results_content[:1], indent=2) if tool_results_content else 'EMPTY'}")  # Log first item only to avoid spam

            # Second streaming call for synthesis
            synthesis_response = ""
            additional_tool_calls = []

            # For subsequent iterations, use a system prompt that prevents
            # re-running PLANNING/EXECUTING/REFLECTING (already emitted in iter 1)
            # but STILL requires the final SYNTHESIS + MEMORY UPDATE markers.
            iteration_system_prompt = system_prompt
            if tool_iteration > 1:
                iteration_system_prompt = """You are ALSARA, an expert ALS research assistant producing the final answer.

You already completed PLANNING, EXECUTING, and REFLECTING in the previous turn. Do NOT repeat those phases.

Your job now is to produce the FINAL ANSWER with these MANDATORY markers:
1. **✅ SYNTHESIS:** on its own line, followed by the full answer
2. Throughout the answer, tag each claim with confidence: 🟢 High / 🟡 Moderate / 🔴 Low
3. **📚 MEMORY UPDATE:** on its own line at the end, followed by a ONE-LINE summary

Include every citation with a clickable URL (PubMed: https://pubmed.ncbi.nlm.nih.gov/PMID/, trials: https://clinicaltrials.gov/study/NCTID).
NEVER invent NCT IDs, PMIDs, or DOIs. Every citation must come from a tool result you actually received."""

            # Tool availability: keep tools on iteration 1 so the model can
            # dig deeper if it wants to, then lock them down on iteration 2+
            # to force synthesis. Previously we stripped tools on "high confidence"
            # — but when the initial response ended with "let me get more details",
            # the model then returned an empty reply because it had nothing to do.
            available_tools = tools if tool_iteration == 1 else []

            # Track a "baseline" of the accumulated response so we can yield
            # incrementally during streaming. This keeps the HF Spaces SSE
            # connection alive (idle proxy timeout ~30s).
            baseline = full_response
            async for response_text, current_tool_calls, provider_used in stream_with_retry(
                client=client,
                messages=messages,
                tools=available_tools,
                system_prompt=iteration_system_prompt,
                max_retries=2,
                model=ANTHROPIC_MODEL,
                max_tokens=MAX_RESPONSE_TOKENS,
                stream_name="synthesis API call"
            ):
                synthesis_response = response_text
                additional_tool_calls = current_tool_calls
                # Yield per-chunk so the browser keeps receiving data.
                yield filter_internal_tags(baseline + synthesis_response)

            full_response += synthesis_response

            # Check for additional tool calls
            if additional_tool_calls:
                logger.info(f"Found {len(additional_tool_calls)} recursive tool calls")

                # Check if we're about to hit the iteration limit
                if tool_iteration >= (max_tool_iterations - 1):  # Last iteration before limit
                    # We're on the last allowed iteration
                    logger.info(f"Approaching iteration limit ({max_tool_iterations}), wrapping up with current results")

                    # Don't execute more tools, instead trigger final synthesis
                    # Add a user message to force final synthesis without tools
                    messages.append({
                        "role": "user",
                        "content": [{"type": "text", "text": "Please provide a complete synthesis of all the information you've found so far. No more searches are available - summarize what you've discovered."}]
                    })

                    # Make one final API call to synthesize all the results
                    final_synthesis = ""
                    baseline = full_response
                    async for response_text, _, provider_used in stream_with_retry(
                        client=client,
                        messages=messages,
                        tools=[],  # No tools for final synthesis
                        system_prompt=system_prompt,
                        max_retries=1,
                        model=ANTHROPIC_MODEL,
                        max_tokens=MAX_RESPONSE_TOKENS,
                        stream_name="final synthesis"
                    ):
                        final_synthesis = response_text
                        yield filter_internal_tags(baseline + final_synthesis)

                    full_response += final_synthesis

                    # Clear tool_calls to exit the loop gracefully
                    tool_calls = []
                else:
                    # We have room for more iterations, proceed normally
                    # Build assistant message for recursive calls
                    assistant_content = build_assistant_message(
                        text_content=synthesis_response,
                        tool_calls=additional_tool_calls
                    )

                    messages.append({
                        "role": "assistant",
                        "content": assistant_content
                    })

                    # Execute recursive tool calls
                    progress_text, tool_results_content = await execute_tool_calls(
                        tool_calls=additional_tool_calls,
                        call_mcp_tool_func=call_tool_cached
                    )

                    full_response += progress_text
                    # Yield the full accumulated response
                    if progress_text:
                        yield filter_internal_tags(full_response)

                    # Add results and continue loop
                    messages.append({
                        "role": "user",
                        "content": tool_results_content
                    })

                    # Accumulate tool result text for the verifier whitelist
                    for item in tool_results_content:
                        if isinstance(item, dict) and isinstance(item.get("content"), str):
                            all_tool_result_texts.append(item["content"])

                    # Set tool_calls for next iteration
                    tool_calls = additional_tool_calls
            else:
                # No more tool calls, exit loop
                tool_calls = []

        if tool_iteration >= max_tool_iterations:
            logger.warning(f"Reached maximum tool iterations ({max_tool_iterations})")

        # Check if synthesis was provided — with condensed prompt this should rarely trigger
        has_synthesis = any(marker in full_response for marker in ["✅ SYNTHESIS:", "✅ ANSWER:", "## Summary", "## Conclusion"])
        if tool_iteration > 0 and not has_synthesis:
            logger.warning(f"No synthesis marker found after {tool_iteration} iterations — the response may still contain useful content")
            # Don't make an extra API call — the response likely has the answer already,
            # just without the exact marker. The condensed prompt should prevent this.

        # --- Post-synthesis citation verification ---
        # Deterministically check every NCT/PMID/DOI in the final response:
        #   1. Against IDs that actually appeared in tool results this session
        #      (catches hallucinated IDs without any network call)
        #   2. Against canonical registries (ClinicalTrials.gov, PubMed, doi.org)
        # If anything fails, append a warning block so the user can't miss it.
        try:
            from citation_verifier import (
                verify_citations,
                collect_ids_from_tool_results,
                format_verification_block,
            )
            whitelist = collect_ids_from_tool_results(all_tool_result_texts)
            verifications = await asyncio.wait_for(
                verify_citations(full_response, tool_result_ids=whitelist),
                timeout=15.0,
            )
            warning_block = format_verification_block(verifications)
            if warning_block:
                full_response += "\n\n" + warning_block
                yield filter_internal_tags(full_response)
                flagged = sum(1 for v in verifications if v.status in ("not_from_search", "not_found"))
                logger.warning(
                    f"Citation verification flagged {flagged} citation(s) "
                    f"out of {len(verifications)} total"
                )
            else:
                logger.info(f"All {len(verifications)} citations verified OK")
        except asyncio.TimeoutError:
            logger.warning("Citation verification timed out — skipping")
        except Exception as e:
            logger.warning(f"Citation verification failed (non-fatal): {e}")

        # Record successful response time
        response_time = time.time() - start_time
        health_monitor.record_response_time(response_time)
        logger.info(f"Request completed in {response_time:.2f} seconds")

    except Exception as e:
        logger.error(f"Error in als_research_agent: {e}", exc_info=True)
        health_monitor.record_error(str(e))
        error_message = format_error_message(e, context=f"Processing query: {message[:100]}...")
        yield error_message

# Gradio Interface
async def main() -> None:
    """Main function to setup and launch the Gradio interface"""
    global cleanup_task

    # Start memory cleanup task
    cleanup_task = asyncio.create_task(cleanup_memory())
    logger.info(f"Direct service tools registered ({len(get_tool_schemas())} tools, 0 subprocesses)")
    
    # Auth config
    app_user = os.environ.get("APP_USERNAME")
    app_pass = os.environ.get("APP_PASSWORD")
    auth_required = bool(app_user and app_pass)
    _failed_attempts = {}
    _max_attempts = 5
    _lockout_seconds = 300

    # Create Gradio interface with export button
    MOBILE_CSS = """
@media (max-width: 768px) {
    .chatbot-container { height: 50vh !important; min-height: 300px !important; }
    .gradio-container { padding: 8px !important; }
}
/* Prevent iOS zoom on input focus */
input, textarea { font-size: 16px !important; }
"""
    with gr.Blocks(css=MOBILE_CSS) as demo:
        # Authentication state: True if logged in OR using own API key
        is_authenticated = gr.State(value=not auth_required)
        user_api_key = gr.State(value=None)  # If user provides their own Anthropic key

        # --- Login screen (in-app, works on mobile) ---
        with gr.Column(visible=auth_required) as login_screen:
            gr.Markdown("# 🧬 ALSARA — Access")
            gr.Markdown(
                "Enter the shared credentials, **or** use your own Anthropic API key "
                "(your queries will be billed to your account)."
            )
            with gr.Row():
                login_user = gr.Textbox(label="Username", scale=1)
                login_pass = gr.Textbox(label="Password", type="password", scale=1)
            login_btn = gr.Button("Log in with password", variant="primary")

            gr.Markdown("**OR** use your own Anthropic API key:")
            login_key = gr.Textbox(label="Anthropic API Key", placeholder="sk-ant-...", type="password")
            login_key_btn = gr.Button("Use my API key", variant="secondary")
            login_msg = gr.Markdown("")

        gr.Markdown("# 🧬 ALSARA - ALS Agentic Research Assistant ")
        gr.Markdown("Ask questions about ALS research, treatments, and clinical trials. This agent searches PubMed, AACT clinical trials database, and other sources in real-time.")

        # Show LLM configuration status using unified client
        llm_status = f"🤖 **LLM Provider:** {client.get_provider_display_name()}"
        gr.Markdown(llm_status)

        with gr.Tabs():
            with gr.TabItem("Chat"):
                chatbot = gr.Chatbot(
                    height="60vh",
                    show_label=False,
                    elem_classes="chatbot-container"
                )

            with gr.TabItem("System Health"):
                gr.Markdown("## 📊 System Health Monitor")

                def format_health_status():
                    """Format health status for display"""
                    status = health_monitor.get_health_status()
                    return f"""
**Status:** {status['status'].upper()} {'✅' if status['status'] == 'healthy' else '⚠️'}

**Uptime:** {status['uptime_seconds'] / 3600:.1f} hours
**Total Requests:** {status['request_count']}
**Error Rate:** {status['error_rate']:.1%}
**Avg Response Time:** {status['avg_response_time']:.2f}s

**Cache Status:**
- Cache Size: {status['cache_size']} items
- Rate Limiter: {status['rate_limit_status']}

**Most Used Tools:**
{chr(10).join([f"- {tool}: {count} calls" for tool, count in status['most_used_tools'].items()])}

**Last Error:** {status['last_error']['error'] if status['last_error'] else 'None'}
                    """

                health_display = gr.Markdown(format_health_status())
                refresh_btn = gr.Button("🔄 Refresh Health Status")
                refresh_btn.click(fn=format_health_status, outputs=health_display)

        with gr.Row():
            with gr.Column(scale=6):
                msg = gr.Textbox(
                    placeholder="Ask about ALS research, treatments, or clinical trials...",
                    container=False,
                    label="Type your question"
                )
            # Voice input disabled
            with gr.Column(scale=1, visible=False):
                audio_input = gr.Audio(
                    sources=["microphone"],
                    type="filepath",
                    label="🎤 Voice Input"
                )
            export_btn = gr.DownloadButton("💾 Export", scale=1)

        with gr.Row():
            submit_btn = gr.Button("Submit", variant="primary")
            retry_btn = gr.Button("🔄 Retry")
            undo_btn = gr.Button("↩️ Undo")
            clear_btn = gr.Button("🗑️ Clear")
            speak_btn = gr.Button("🔊 Read Last Response", variant="secondary", interactive=False, visible=False)  # Voice disabled

        # Audio output component (voice disabled)
        with gr.Row(visible=False) as audio_row:
            audio_output = gr.Audio(
                label="🔊 Voice Output",
                type="filepath",
                autoplay=True,
                visible=True
            )

        gr.Examples(
            examples=[
                "ALS clinical trials in Europe",
                "ALS clinical trials in the U.S.A.",
                "Find Phase 2/3 ALS trials near Paris, France",
                "New ALS trials posted in the last 30 days",
                "Most promising new ALS treatments in the last 6 months",
                "Trials testing acetyl-L-carnitine (ALCAR) for ALS",
                "What supplements are recommended for ALS?",
                "Omega-3 and vitamin D in ALS treatment",
                "Tofersen clinical trial status",
            ],
            inputs=msg,
            examples_per_page=9,
        )

        # Chat interface logic with improved error handling
        async def respond(message: str, history: Optional[List[Dict[str, str]]], authed: bool, api_key: Optional[str]) -> AsyncGenerator[List[Dict[str, str]], None]:
            history = history or []

            # Gate queries until the user has authenticated
            if auth_required and not authed:
                history.append({"role": "user", "content": message})
                history.append({"role": "assistant", "content": "🔒 Please log in at the top of the page to use the assistant."})
                yield history
                return

            # If user provided their own API key, temporarily swap it in for this request
            original_key = os.environ.get("ANTHROPIC_API_KEY")
            if api_key:
                os.environ["ANTHROPIC_API_KEY"] = api_key

            # Append user message
            history.append({"role": "user", "content": message})
            # Append empty assistant message
            history.append({"role": "assistant", "content": ""})

            try:
                # Pass history without the new messages to als_research_agent
                async for response in als_research_agent(message, history[:-2]):
                    # Update the last assistant message in place
                    history[-1]['content'] = response
                    yield history
            except Exception as e:
                logger.error(f"Error in respond: {e}", exc_info=True)
                error_msg = f"❌ Error: {str(e)}"
                history[-1]['content'] = error_msg
                yield history
            finally:
                if api_key and original_key:
                    os.environ["ANTHROPIC_API_KEY"] = original_key

        def update_speak_button():
            """Update the speak button state based on last_response_was_research"""
            global last_response_was_research
            return gr.update(interactive=last_response_was_research)

        def undo_last(history: Optional[List[Dict[str, str]]]) -> Optional[List[Dict[str, str]]]:
            """Remove the last message pair from history"""
            if history and len(history) >= 2:
                # Remove last user message and assistant response
                return history[:-2]
            return history

        async def retry_last(history: Optional[List[Dict[str, str]]]) -> AsyncGenerator[List[Dict[str, str]], None]:
            """Retry the last query with error handling"""
            if history and len(history) >= 2:
                # Get the last user message
                last_user_msg = history[-2]["content"] if history[-2]["role"] == "user" else None
                if last_user_msg:
                    # Remove last assistant message, keep user message
                    history = history[:-1]
                    # Add new empty assistant message
                    history.append({"role": "assistant", "content": ""})
                    try:
                        # Resubmit (pass history without the last user and assistant messages)
                        async for response in als_research_agent(last_user_msg, history[:-2]):
                            # Update the last assistant message in place
                            history[-1]['content'] = response
                            yield history
                    except Exception as e:
                        logger.error(f"Error in retry_last: {e}", exc_info=True)
                        error_msg = f"❌ Error during retry: {str(e)}"
                        history[-1]['content'] = error_msg
                        yield history
                else:
                    yield history
            else:
                yield history

        async def process_voice_input(audio_file):
            """Process voice input and convert to text"""
            try:
                if audio_file is None:
                    return ""

                # Try to use speech recognition if available
                try:
                    import speech_recognition as sr
                    recognizer = sr.Recognizer()

                    # Load audio file
                    with sr.AudioFile(audio_file) as source:
                        audio_data = recognizer.record(source)

                    # Use Google's free speech recognition
                    try:
                        text = recognizer.recognize_google(audio_data)
                        logger.info(f"Voice input transcribed: {text[:50]}...")
                        return text
                    except sr.UnknownValueError:
                        logger.warning("Could not understand audio")
                        return ""
                    except sr.RequestError as e:
                        logger.error(f"Speech recognition service error: {e}")
                        return ""

                except ImportError:
                    logger.warning("speech_recognition not available")
                    return ""

            except Exception as e:
                logger.error(f"Error processing voice input: {e}")
                return ""

        async def speak_last_response(history: Optional[List[Dict[str, str]]]) -> Tuple[gr.update, gr.update]:
            """Convert the last assistant response to speech using ElevenLabs"""
            try:
                # Check if the last response was from research workflow
                global last_response_was_research
                if not last_response_was_research:
                    # This shouldn't happen since button is disabled, but handle it gracefully
                    logger.info("Last response was not research-based, voice synthesis not available")
                    return gr.update(visible=False), gr.update(value=None)

                # Check ELEVENLABS_API_KEY
                api_key = os.getenv("ELEVENLABS_API_KEY")
                if not api_key:
                    logger.warning("No ELEVENLABS_API_KEY configured")
                    return gr.update(visible=True), gr.update(
                        value=None,
                        label="⚠️ Voice service unavailable - Please set ELEVENLABS_API_KEY"
                    )

                if not history or len(history) < 1:
                    logger.warning("No history available for text-to-speech")
                    return gr.update(visible=True), gr.update(
                        value=None,
                        label="⚠️ No conversation history to read"
                    )

                # Get the last assistant response
                last_response = None

                # Detect and handle different history formats
                if isinstance(history, list) and len(history) > 0:
                    # Check if history is a list of lists (Gradio chatbot format)
                    if isinstance(history[0], list) and len(history[0]) == 2:
                        # Format: [[user_msg, assistant_msg], ...]
                        logger.info("Detected Gradio list-of-lists history format")
                        for i, exchange in enumerate(reversed(history)):
                            if len(exchange) == 2 and exchange[1]:  # assistant message is second
                                last_response = exchange[1]
                                break
                    elif isinstance(history[0], dict):
                        # Format: [{"role": "user", "content": "..."}, ...]
                        logger.info("Detected dict-based history format")
                        for i, msg in enumerate(reversed(history)):
                            if msg.get("role") == "assistant" and msg.get("content"):
                                content = msg["content"]
                                # CRITICAL FIX: Handle Claude API content blocks
                                if isinstance(content, list):
                                    # Extract text from content blocks
                                    text_parts = []
                                    for block in content:
                                        if isinstance(block, dict):
                                            # Handle text block
                                            if block.get("type") == "text" and "text" in block:
                                                text_parts.append(block["text"])
                                            # Handle string content in dict
                                            elif "content" in block and isinstance(block["content"], str):
                                                text_parts.append(block["content"])
                                        elif isinstance(block, str):
                                            text_parts.append(block)
                                    last_response = "\n".join(text_parts)
                                else:
                                    # Content is already a string
                                    last_response = content
                                break
                    elif isinstance(history[0], str):
                        # Simple string list - take the last one
                        logger.info("Detected simple string list history format")
                        last_response = history[-1] if history else None
                    else:
                        # Unknown format - try to extract what we can
                        logger.warning(f"Unknown history format: {type(history[0])}")
                        # Try to convert to string as last resort
                        try:
                            last_response = str(history[-1]) if history else None
                        except Exception as e:
                            logger.error(f"Failed to extract last response: {e}")

                if not last_response:
                    logger.warning("No assistant response found in history")
                    return gr.update(visible=True), gr.update(
                        value=None,
                        label="⚠️ No assistant response found to read"
                    )

                # Clean the response text (remove markdown, internal tags, etc.)
                # Convert to string if not already (safety check)
                last_response = str(last_response)

                # IMPORTANT: Extract only the synthesis/main answer, skip references and "for more information"
                # Find where to cut off the response
                cutoff_patterns = [
                    # Clear section headers with colons - most reliable indicators
                    r'\n\s*(?:For (?:more|additional|further) (?:information|details|reading))\s*[:：]',
                    r'\n\s*(?:References?|Sources?|Citations?|Bibliography)\s*[:：]',
                    r'\n\s*(?:Additional (?:resources?|information|reading|materials?))\s*[:：]',

                    # Markdown headers for reference sections (must be on their own line)
                    r'\n\s*#{1,6}\s+(?:References?|Sources?|Citations?|Bibliography)\s*$',
                    r'\n\s*#{1,6}\s+(?:For (?:more|additional|further) (?:information|details))\s*$',
                    r'\n\s*#{1,6}\s+(?:Additional (?:Resources?|Information|Reading))\s*$',
                    r'\n\s*#{1,6}\s+(?:Further Reading|Learn More)\s*$',

                    # Bold headers for reference sections (with newline after)
                    r'\n\s*\*\*(?:References?|Sources?|Citations?)\*\*\s*[:：]?\s*\n',
                    r'\n\s*\*\*(?:For (?:more|additional) information)\*\*\s*[:：]?\s*\n',

                    # Phrases that clearly introduce reference lists
                    r'\n\s*(?:Here are|Below are|The following are)\s+(?:the |some |additional )?(?:references|sources|citations|papers cited|studies referenced)',
                    r'\n\s*(?:References used|Sources consulted|Papers cited|Studies referenced)\s*[:：]',
                    r'\n\s*(?:Key|Recent|Selected|Relevant)\s+(?:references?|publications?|citations)\s*[:：]',

                    # Clinical trials section headers with clear separators
                    r'\n\s*(?:Clinical trials?|Studies|Research papers?)\s+(?:referenced|cited|mentioned|used)\s*[:：]',
                    r'\n\s*(?:AACT|ClinicalTrials\.gov)\s+(?:database entries?|trial IDs?|references?)\s*[:：]',

                    # Web link sections
                    r'\n\s*(?:Links?|URLs?|Websites?|Web resources?)\s*[:：]',
                    r'\n\s*(?:Visit|See|Check out)\s+(?:these|the following)\s+(?:links?|websites?|resources?)',
                    r'\n\s*(?:Learn more|Read more|Find out more|Get more information)\s+(?:at|here|below)\s*[:：]',

                    # Academic citation lists (only when preceded by double newline or clear separator)
                    r'\n\n\s*\d+\.\s+[A-Z][a-z]+.*?et al\..*?(?:PMID|DOI|Journal)',
                    r'\n\n\s*\[1\]\s+[A-Z][a-z]+.*?(?:et al\.|https?://)',

                    # Direct ID listings (clearly separate from main content)
                    r'\n\s*(?:PMID|DOI|NCT)\s*[:：]\s*\d+',
                    r'\n\s*(?:Trial IDs?|Study IDs?)\s*[:：]',

                    # Footer sections
                    r'\n\s*(?:Note|Notes|Disclaimer|Important notice)\s*[:：]',
                    r'\n\s*(?:Data (?:source|from)|Database|Repository)\s*[:：]',
                    r'\n\s*(?:Retrieved from|Accessed via|Source database)\s*[:：]',
                ]

                # FIRST: Extract ONLY the synthesis section (after ✅ SYNTHESIS:)
                # More robust pattern that handles various formatting
                synthesis_patterns = [
                    r'✅\s*\*{0,2}SYNTHESIS\*{0,2}\s*:?\s*\n+(.*)',  # Standard format with newline
                    r'\*\*✅\s*SYNTHESIS:\*\*\s*(.*)',  # Bold format
                    r'✅\s*SYNTHESIS:\s*(.*)',  # Simple format
                    r'SYNTHESIS:\s*(.*)',  # Fallback without emoji
                ]

                synthesis_text = None
                for pattern in synthesis_patterns:
                    synthesis_match = re.search(pattern, last_response, re.IGNORECASE | re.DOTALL)
                    if synthesis_match:
                        synthesis_text = synthesis_match.group(1)
                        logger.info(f"Extracted synthesis section using pattern: {pattern[:30]}...")
                        break

                if synthesis_text:
                    logger.info("Extracted synthesis section for voice reading")
                else:
                    # Fallback: if no synthesis marker found, use the whole response
                    synthesis_text = last_response
                    logger.info("No synthesis marker found, using full response")

                # THEN: Remove references and footer sections
                for pattern in cutoff_patterns:
                    match = re.search(pattern, synthesis_text, re.IGNORECASE | re.MULTILINE)
                    if match:
                        synthesis_text = synthesis_text[:match.start()]
                        logger.info(f"Truncated response at pattern: {pattern[:50]}...")
                        break

                # Now clean the synthesis text
                clean_text = re.sub(r'\*\*(.*?)\*\*', r'\1', synthesis_text)  # Remove bold
                clean_text = re.sub(r'\*(.*?)\*', r'\1', clean_text)  # Remove italic
                clean_text = re.sub(r'#{1,6}\s*(.*?)\n', r'\1. ', clean_text)  # Remove headers
                clean_text = re.sub(r'```.*?```', '', clean_text, flags=re.DOTALL)  # Remove code blocks
                clean_text = re.sub(r'`(.*?)`', r'\1', clean_text)  # Remove inline code
                clean_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', clean_text)  # Remove links
                clean_text = re.sub(r'<[^>]+>', '', clean_text)  # Remove HTML tags
                clean_text = re.sub(r'\n{3,}', '\n\n', clean_text)  # Reduce multiple newlines

                # Strip leading/trailing whitespace
                clean_text = clean_text.strip()

                # Ensure we have something to read
                if not clean_text or len(clean_text) < 10:
                    logger.warning("Synthesis text too short after cleaning, using original")
                    clean_text = last_response[:2500]  # Fallback to first 2500 chars
                # Remove phase markers from text
                clean_text = re.sub(r'\*\*[🎯🔧🤔✅].*?:\*\*', '', clean_text)
                logger.info(f"Calling ElevenLabs text-to-speech with {len(clean_text)} characters...")
                try:
                    from servers.elevenlabs_server import text_to_speech as _tts
                    tts_result = await _tts(text=clean_text, speed=0.95)
                    result_data = json.loads(tts_result) if isinstance(tts_result, str) else tts_result
                except Exception as e:
                    logger.error(f"ElevenLabs call failed: {e}", exc_info=True)
                    raise

                try:

                    if result_data.get("status") == "success" and result_data.get("audio_base64"):
                        # Save audio to temporary file
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
                            audio_data = base64.b64decode(result_data["audio_base64"])
                            tmp_file.write(audio_data)
                            audio_path = tmp_file.name

                        logger.info(f"Audio successfully generated and saved to: {audio_path}")
                        return gr.update(visible=True), gr.update(
                            value=audio_path,
                            visible=True,
                            label="🔊 Click to play voice output"
                        )
                    elif result_data.get("status") == "error":
                        error_msg = result_data.get("message", "Unknown error")
                        error_type = result_data.get("error", "Unknown")
                        logger.error(f"ElevenLabs error - Type: {error_type}, Message: {error_msg}")
                        return gr.update(visible=True), gr.update(
                            value=None,
                            label=f"⚠️ Voice service error: {error_msg}"
                        )
                    else:
                        logger.error(f"Unexpected result structure")
                        return gr.update(visible=True), gr.update(
                            value=None,
                            label="⚠️ Voice service returned no audio"
                        )
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                    logger.error(f"Failed to parse ElevenLabs response, first 500 chars: {str(result)[:500]}")
                    return gr.update(visible=True), gr.update(
                        value=None,
                        label="⚠️ Voice service response error"
                    )
                except Exception as e:
                    logger.error(f"Unexpected error in result parsing: {e}", exc_info=True)
                    raise

            except Exception as e:
                logger.error(f"Error in speak_last_response: {e}", exc_info=True)
                return gr.update(visible=True), gr.update(
                    value=None,
                    label=f"⚠️ Voice service error: {str(e)}"
                )

        msg.submit(
            respond, [msg, chatbot, is_authenticated, user_api_key], [chatbot],
            api_name="chat"
        ).then(
            update_speak_button, None, [speak_btn]
        ).then(
            lambda: "", None, [msg]
        )

        # Voice input event handler (disabled)
        # audio_input.stop_recording(
        #     process_voice_input,
        #     inputs=[audio_input],
        #     outputs=[msg]
        # ).then(
        #     lambda: None,
        #     outputs=[audio_input]  # Clear audio after processing
        # )

        submit_btn.click(
            respond, [msg, chatbot, is_authenticated, user_api_key], [chatbot],
            api_name="chat_button"
        ).then(
            update_speak_button, None, [speak_btn]
        ).then(
            lambda: "", None, [msg]
        )

        retry_btn.click(
            retry_last, [chatbot], [chatbot],
            api_name="retry"
        ).then(
            update_speak_button, None, [speak_btn]
        )

        undo_btn.click(
            undo_last, [chatbot], [chatbot],
            api_name="undo"
        )

        clear_btn.click(
            lambda: None, None, chatbot,
            queue=False,
            api_name="clear"
        ).then(
            lambda: gr.update(interactive=False), None, [speak_btn]
        )

        export_btn.click(
            export_conversation, chatbot, export_btn,
            api_name="export"
        )

        # --- Login handlers (hide the login screen once authenticated) ---
        def do_login_password(username, password):
            import time as _time
            now = _time.time()
            key = (username or "").lower().strip()
            if key in _failed_attempts:
                count, last = _failed_attempts[key]
                if count >= _max_attempts and (now - last) < _lockout_seconds:
                    remaining = int(_lockout_seconds - (now - last))
                    return (gr.update(), True, None, f"⏱️ Too many failed attempts. Try again in {remaining}s.")
            if username == app_user and password == app_pass:
                _failed_attempts.pop(key, None)
                logger.info(f"Login success: {key}")
                return (gr.update(visible=False), True, None, "")
            cnt = _failed_attempts.get(key, (0, 0))[0] + 1
            _failed_attempts[key] = (cnt, now)
            logger.warning(f"Failed login: {key} ({cnt}/{_max_attempts})")
            return (gr.update(), False, None, f"❌ Invalid credentials ({cnt}/{_max_attempts})")

        def do_login_api_key(api_key):
            if not api_key or not api_key.strip().startswith("sk-ant-"):
                return (gr.update(), False, None, "❌ Invalid API key format. Should start with 'sk-ant-'.")
            logger.info("User provided their own API key")
            return (gr.update(visible=False), True, api_key.strip(), "")

        login_btn.click(
            do_login_password,
            inputs=[login_user, login_pass],
            outputs=[login_screen, is_authenticated, user_api_key, login_msg],
        )
        login_pass.submit(
            do_login_password,
            inputs=[login_user, login_pass],
            outputs=[login_screen, is_authenticated, user_api_key, login_msg],
        )
        login_key_btn.click(
            do_login_api_key,
            inputs=[login_key],
            outputs=[login_screen, is_authenticated, user_api_key, login_msg],
        )
        login_key.submit(
            do_login_api_key,
            inputs=[login_key],
            outputs=[login_screen, is_authenticated, user_api_key, login_msg],
        )

        # Voice output event handler (disabled)
        # speak_btn.click(
        #     speak_last_response, [chatbot], [audio_row, audio_output],
        #     api_name="speak"
        # )

    # Enable queue for streaming to work
    demo.queue()

    try:
        # Use environment variable for port, default to 7860 for HuggingFace
        port = int(os.environ.get("GRADIO_SERVER_PORT", 7860))

        demo.launch(
            server_name="0.0.0.0",
            server_port=port,
            share=False,
            ssr_mode=False,
        )
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Error during launch: {e}", exc_info=True)
    finally:
        # Cleanup
        logger.info("Cleaning up resources...")
        await flush_llamaindex()

def _handle_sigterm(signum, frame):
    """Translate SIGTERM into KeyboardInterrupt so the graceful cleanup path runs.

    HF Spaces sends SIGTERM on Restart/rebuild. Python does NOT convert SIGTERM
    to KeyboardInterrupt automatically, so without this the process just dies
    and flush_llamaindex() (which syncs chroma_db to the Dataset repo)
    never gets the chance to run.
    """
    import signal as _signal
    logger.info(f"Received signal {signum} — initiating graceful shutdown")
    raise KeyboardInterrupt()


if __name__ == "__main__":
    import signal
    signal.signal(signal.SIGTERM, _handle_sigterm)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by user")
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        raise
    finally:
        # Cancel cleanup task if running
        if cleanup_task and not cleanup_task.done():
            cleanup_task.cancel()
            logger.info("Cancelled memory cleanup task")

        # Cleanup unified LLM client
        if client is not None:
            try:
                asyncio.run(client.cleanup())
                logger.info("LLM client cleanup completed")
            except Exception as e:
                logger.warning(f"LLM client cleanup error: {e}")
                pass
