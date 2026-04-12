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
from custom_mcp_client import MCPClientManager
from llm_client import UnifiedLLMClient
from smart_cache import SmartCache, DEFAULT_PREWARM_QUERIES

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

# Global MCP client manager
mcp_manager = MCPClientManager()

# Internal thinking tags are always filtered for cleaner output

# Model configuration
# Use Claude 3.5 Sonnet with correct model ID that works with the API key
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
logger.info(f"Using model: {ANTHROPIC_MODEL}")

# Configuration for max tokens in responses
# Set MAX_RESPONSE_TOKENS in .env to control response length
# Claude 3.5 Sonnet supports up to 8192 tokens
MAX_RESPONSE_TOKENS = min(int(os.getenv("MAX_RESPONSE_TOKENS") or "8192"), 8192)
logger.info(f"Max response tokens set to: {MAX_RESPONSE_TOKENS}")

# Global smart cache (24 hour TTL for research queries)
smart_cache = SmartCache(cache_dir=".cache", ttl_hours=24)

# Keep tool cache for MCP tool results
tool_cache = SimpleCache(ttl=3600)

# Cache for tool definitions to avoid repeated fetching
_cached_tools = None
_tools_cache_time = None
TOOLS_CACHE_TTL = 86400  # 24 hour cache for tool definitions (tools rarely change)

async def setup_mcp_servers() -> MCPClientManager:
    """Initialize all MCP servers using custom client"""
    logger.info("Setting up MCP servers...")

    # Get the directory where this script is located
    script_dir = Path(__file__).parent.resolve()
    servers_dir = script_dir / "servers"

    logger.info(f"Script directory: {script_dir}")
    logger.info(f"Servers directory: {servers_dir}")

    # Verify servers directory exists
    if not servers_dir.exists():
        logger.error(f"Servers directory not found: {servers_dir}")
        raise FileNotFoundError(f"Servers directory not found: {servers_dir}")

    # Add all servers to manager
    servers = {
        "pubmed": servers_dir / "pubmed_server.py",
        "aact": servers_dir / "aact_server.py",  # PRIMARY: AACT database for comprehensive clinical trials data
        "trials_links": servers_dir / "clinicaltrials_links.py",  # FALLBACK: Direct links and known ALS trials
        "fetch": servers_dir / "fetch_server.py",
        "elevenlabs": servers_dir / "elevenlabs_server.py",  # Voice capabilities for accessibility
    }

    # bioRxiv temporarily disabled - commenting out to hide from users
    # enable_biorxiv = os.getenv("ENABLE_BIORXIV", "true").lower() == "true"
    # if enable_biorxiv:
    #     servers["biorxiv"] = servers_dir / "biorxiv_server.py"
    # else:
    #     logger.info("⚠️ bioRxiv/medRxiv disabled for faster searches (set ENABLE_BIORXIV=true to enable)")

    # Conditionally add LlamaIndex RAG based on environment variable
    enable_rag = os.getenv("ENABLE_RAG", "false").lower() == "true"
    if enable_rag:
        logger.info("📚 RAG/LlamaIndex enabled (will add ~10s to startup for semantic search)")
        servers["llamaindex"] = servers_dir / "llamaindex_server.py"
    else:
        logger.info("🚀 RAG/LlamaIndex disabled for faster startup (set ENABLE_RAG=true to enable)")

    # Parallelize server initialization for faster startup
    async def init_server(name: str, script_path: Path):
        try:
            await mcp_manager.add_server(name, str(script_path))
            logger.info(f"✓ MCP server {name} initialized")
        except Exception as e:
            logger.error(f"Failed to initialize MCP server {name}: {e}")
            raise

    # Start all servers concurrently
    tasks = [init_server(name, script_path) for name, script_path in servers.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Check for any failures
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            name = list(servers.keys())[i]
            logger.error(f"Failed to initialize MCP server {name}: {result}")
            raise result

    logger.info("All MCP servers initialized successfully")
    return mcp_manager

async def cleanup_mcp_servers() -> None:
    """Cleanup MCP server sessions"""
    logger.info("Cleaning up MCP server sessions...")
    await mcp_manager.close_all()
    logger.info("MCP cleanup complete")


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

async def get_all_tools() -> List[Dict[str, Any]]:
    """Retrieve all available tools from MCP servers with caching"""
    global _cached_tools, _tools_cache_time

    # Check if cache is valid
    if _cached_tools and _tools_cache_time:
        if time.time() - _tools_cache_time < TOOLS_CACHE_TTL:
            logger.debug("Using cached tool definitions")
            return _cached_tools

    # Fetch fresh tool definitions
    logger.info("Fetching fresh tool definitions from MCP servers")
    all_tools = []

    # Get tools from all servers
    server_tools = await mcp_manager.list_all_tools()

    for server_name, tools in server_tools.items():
        for tool in tools:
            # Convert MCP tool to Anthropic function format
            all_tools.append({
                "name": f"{server_name}__{tool['name']}",
                "description": tool.get('description', ''),
                "input_schema": tool.get('inputSchema', {})
            })

    # Update cache
    _cached_tools = all_tools
    _tools_cache_time = time.time()
    logger.info(f"Cached {len(all_tools)} tool definitions")

    return all_tools

async def call_mcp_tool(tool_name: str, arguments: Dict[str, Any], max_retries: int = 3) -> str:
    """Execute an MCP tool call with caching, rate limiting, retry logic, and error handling"""

    # Check cache first (no retries needed for cached results)
    cached_result = tool_cache.get(tool_name, arguments)
    if cached_result:
        return cached_result

    last_error = None

    for attempt in range(max_retries):
        try:
            # Apply rate limiting
            await rate_limiter.wait_if_needed(tool_name.split("__")[0])

            # Parse tool name
            if "__" not in tool_name:
                logger.error(f"Invalid tool name format: {tool_name}")
                return f"Error: Invalid tool name format: {tool_name}"

            server_name, tool_method = tool_name.split("__", 1)

            if attempt > 0:
                logger.info(f"Retry {attempt}/{max_retries} for tool: {tool_method} on server: {server_name}")
            else:
                logger.info(f"Calling tool: {tool_method} on server: {server_name}")

            # Call tool with timeout using custom client
            result = await asyncio.wait_for(
                mcp_manager.call_tool(server_name, tool_method, arguments),
                timeout=90.0  # 90 second timeout for complex tool calls (BioRxiv searches can be slow)
            )

            # Result is already a string from custom client
            final_result = result if result else "No content returned from tool"

            # Cache the result
            tool_cache.set(tool_name, arguments, final_result)

            # Record successful tool call
            health_monitor.record_tool_call(tool_name)

            return final_result

        except asyncio.TimeoutError as e:
            last_error = e
            logger.warning(f"Tool call timed out (attempt {attempt + 1}/{max_retries}): {tool_name}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                continue
            # Last attempt failed
            timeout_error = TimeoutError(f"Tool timeout after {max_retries} attempts - the {server_name} server may be overloaded")
            return format_error_message(timeout_error, context=f"Calling {tool_name}")

        except ValueError as e:
            logger.error(f"Invalid tool/server: {tool_name} - {e}")
            return format_error_message(e, context=f"Invalid tool: {tool_name}")

        except Exception as e:
            last_error = e
            logger.warning(f"Error calling tool {tool_name} (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
            # Last attempt failed
            return format_error_message(e, context=f"Tool {tool_name} failed after {max_retries} attempts")

    # Should not reach here, but handle just in case
    if last_error:
        return f"Tool failed after {max_retries} attempts: {str(last_error)[:200]}"
    return "Unexpected error in tool execution"

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

        # System prompt
        base_prompt = """You are ALSARA, an expert ALS (Amyotrophic Lateral Sclerosis) research assistant with agentic capabilities for planning, execution, and reflection.

CRITICAL CONTEXT: ALL queries should be interpreted in the context of ALS research unless explicitly stated otherwise.

MANDATORY SEARCH QUERY RULES:
1. ALWAYS include "ALS" or "amyotrophic lateral sclerosis" in EVERY search query
2. If the user's query doesn't mention ALS, ADD IT to your search terms
3. This prevents irrelevant results from other conditions

Examples:
- User: "genotyping for gene targeted treatments" → Search: "genotyping ALS gene targeted treatments"
- User: "psilocybin clinical trials" → Search: "psilocybin ALS clinical trials"
- User: "stem cell therapy" → Search: "stem cell therapy ALS"
- User: "gene therapy trials" → Search: "gene therapy ALS trials"

Your capabilities:
- Search PubMed for peer-reviewed research papers
- Find active clinical trials in the AACT database"""

        # Add RAG capability only if enabled
        enable_rag = os.getenv("ENABLE_RAG", "false").lower() == "true"
        if enable_rag:
            base_prompt += """
- **Semantic search using RAG**: Instantly search cached ALS research papers using AI-powered semantic matching"""

        base_prompt += """
- Fetch and analyze web content
- Synthesize information from multiple sources
- Provide citations with PMIDs, DOIs, and NCT IDs

=== AGENTIC WORKFLOW (REQUIRED) ===

You MUST follow ALL FOUR phases for EVERY query - no exceptions:

1. **🎯 PLANNING PHASE** (MANDATORY - ALWAYS FIRST):
   Before using any tools, you MUST explicitly outline your search strategy:"""

        if enable_rag:
            base_prompt += """
   - FIRST check research memory using semantic_search to find cached papers on this topic
   - If memory returns results, check their indexed_at dates:
     • Papers indexed < 30 days ago → use memory + skip PubMed for those subtopics
     • Papers indexed ≥ 30 days ago → use memory AND search PubMed for newer publications since that date (freshness check)
   - If memory returns no results → full PubMed search as normal (new topic)"""

        base_prompt += """
   - State what databases you will search and in what order
   - ALWAYS plan to search PubMed for peer-reviewed research
   - For clinical questions, also include AACT trials database
   - Identify key search terms and variations
   - Explain your prioritization approach
   - Format: MUST start on a NEW LINE with "**🎯 PLANNING:**" followed by your strategy

2. **🔧 EXECUTION PHASE** (MANDATORY - AFTER PLANNING):
   - MUST mark this phase on a NEW LINE with "**🔧 EXECUTING:**"
   - Execute your planned searches systematically"""

        if enable_rag:
            base_prompt += """
   - START with semantic search using RAG for instant cached results"""

        base_prompt += """
   - MINIMUM requirement: Search PubMed for peer-reviewed literature
   - For clinical questions, search AACT trials database
   - Gather initial results from each source
   - Show tool calls and results
   - This phase is for INITIAL searches only (as planned)

3. **🤔 REFLECTION PHASE** (MANDATORY - AFTER EXECUTION):
   After tool execution, you MUST ALWAYS reflect before synthesizing:

   CRITICAL FORMAT REQUIREMENTS:
   - MUST be EXACTLY: **🤔 REFLECTING:**
   - MUST include the asterisks (**) for bold formatting
   - MUST start on a NEW LINE (never inline with other text)
   - WRONG: "🤔 REFLECTING:" (missing asterisks)
   - WRONG: "search completed🤔 REFLECTING:" (inline, not on new line)
   - CORRECT: New line, then **🤔 REFLECTING:**

   Content requirements:
   - Evaluate: "Do I have sufficient information to answer comprehensively?"
   - Identify gaps: "What aspects of the query remain unaddressed?"
   - Decide: "Should I refine my search or proceed to synthesis?"

   CRITICAL: If you need more searches:
   - DO NOT start a new PLANNING phase
   - DO NOT write new phase markers
   - Stay WITHIN the REFLECTION phase
   - Simply continue searching and analyzing while in REFLECTING mode
   - Additional searches are part of reflection, not a new workflow

   INDEX AS YOU GO (do this during reflection, not at the end):
   - After each search batch, immediately call `llamaindex__index_paper` for each significant paper found
   - Do NOT wait until the Memory Update phase — index papers as you find them
   - This prevents hitting token limits before indexing happens
   - Keep index calls concise: title, abstract (first 300 chars), authors, doi, year, url, 1-sentence finding
   - Skip papers where response returns `"status": "already_indexed"`

   - NEVER skip this phase - it ensures answer quality

4. **✅ SYNTHESIS PHASE** (MANDATORY - FINAL PHASE):
   - MUST start on a NEW LINE with "**✅ SYNTHESIS:**"
   - Provide comprehensive synthesis of all findings
   - Include all citations with URLs
   - Summarize key insights
   - **CONFIDENCE SCORING**: Include confidence level for key claims:
     • High confidence (🟢): Multiple peer-reviewed studies or systematic reviews
     • Moderate confidence (🟡): Limited studies or preprints with consistent findings
     • Low confidence (🔴): Single study, conflicting evidence, or theoretical basis
   - This phase MUST appear in EVERY response

5. **📚 MEMORY UPDATE PHASE** (MANDATORY when RAG enabled - AFTER SYNTHESIS):
   - MUST start on a NEW LINE with "**📚 MEMORY UPDATE:**"
   - Papers should already be indexed during the Reflection phase — this is just a summary
   - Write a single line: "Indexed N new papers | M already in memory | Topic: [topic]"
   - If indexing was skipped entirely, index up to 3 most important papers here as a fallback
   - Keep this phase SHORT — it is a status report, not where indexing happens

FORMATTING RULES:
- Each phase marker MUST appear on its own line
- Never put phase markers inline with other text
- Always use the exact format: **[emoji] PHASE_NAME:**
- MUST include asterisks for bold: **🤔 REFLECTING:** not just 🤔 REFLECTING:
- Each phase should appear EXACTLY ONCE per response - never repeat the workflow

CRITICAL WORKFLOW RULES:
- You MUST include ALL FIVE phases in your response
- Each phase appears EXACTLY ONCE (never repeat Planning→Executing→Reflecting→Synthesis→Memory Update)
- Missing any phase is unacceptable
- Duplicating phases is unacceptable
- The workflow is a SINGLE CYCLE:
  1. PLANNING (once at start)
  2. EXECUTING (initial searches)
  3. REFLECTING (evaluate AND do additional searches if needed - all within this phase)
  4. SYNTHESIS (final answer)
  5. MEMORY UPDATE (index new papers found this session)
- NEVER restart the workflow - additional searches happen WITHIN reflection

CRITICAL SYNTHESIS RULES:
- You MUST ALWAYS follow synthesis with a 📚 MEMORY UPDATE phase
- If searches fail, state "Despite search limitations..." and provide knowledge-based answer
- If you reach iteration limits, immediately provide synthesis then memory update
- NEVER end without both synthesis and memory update - both are MANDATORY
- If uncertain, start synthesis with: "Based on available information..."

SYNTHESIS MUST INCLUDE:
1. Direct answer to the user's question
2. Key findings from successful searches (if any)
3. Citations with clickable URLs
4. If searches failed: explanation + knowledge-based answer
5. Suggested follow-up questions or alternative approaches

=== SELF-CORRECTION BEHAVIOR ===

If your searches return zero or insufficient results:
- Try broader search terms (remove qualifiers)
- Try alternative terminology or synonyms
- Search for related concepts
- Explicitly state what you tried and what you found

When answering:
1. Be concise in explanations while maintaining clarity
2. Focus on presenting search results efficiently
3. Always cite sources with specific identifiers AND URLs:
   - PubMed: Include PMID and URL (https://pubmed.ncbi.nlm.nih.gov/PMID/)
   - Preprints: Include DOI and URL (https://doi.org/DOI)
   - Clinical Trials: Include NCT ID and URL (https://clinicaltrials.gov/study/NCTID)
4. Use numbered citations [1], [2] with a references section at the end
5. Prioritize recent research (2023-2025)
6. When discussing preprints, note they are NOT peer-reviewed
7. Explain complex concepts clearly
8. Acknowledge uncertainty when appropriate
9. Suggest related follow-up questions

CRITICAL CITATION RULES:
- ONLY cite papers, preprints, and trials that you have ACTUALLY found using the search tools
- NEVER make up or invent citations, PMIDs, DOIs, or NCT IDs
- NEVER cite papers from your training data unless you have verified them through search
- If you cannot find specific research on a topic, explicitly state "No studies found" rather than inventing citations
- Every citation must come from actual search results obtained through the available tools
- If asked about a topic you know from training but haven't searched, you MUST search first before citing

IMPORTANT: When referencing papers in your final answer, ALWAYS include clickable URLs alongside citations to make it easy for users to access the sources.

Available tools:
- pubmed__search_pubmed: Search peer-reviewed research literature
- pubmed__get_paper_details: Get full paper details from PubMed (USE SPARINGLY - only for most relevant papers)
# - biorxiv__search_preprints: (temporarily unavailable)
# - biorxiv__get_preprint_details: (temporarily unavailable)
- aact__search_aact_trials: Search clinical trials (PRIMARY - use this first)
- aact__get_aact_trial: Get specific trial details from AACT database
- trials_links__get_known_als_trials: Get curated list of important ALS trials (FALLBACK)
- trials_links__get_search_link: Generate direct ClinicalTrials.gov search URLs
- fetch__fetch_url: Retrieve web content
- llamaindex__semantic_search: Search persistent research memory (vector similarity — use FIRST in every session)
- llamaindex__index_paper: Save a paper to persistent memory (call after synthesis for each key paper)
- llamaindex__list_indexed_papers: List all papers currently in memory (useful to audit coverage)
- llamaindex__get_research_connections: Find papers in memory related to a given title

PERFORMANCE OPTIMIZATION:
- Search results already contain abstracts - use these for initial synthesis
- Only fetch full details for papers that are DIRECTLY relevant to the query
- Limit detail fetches to 5-7 most relevant items per database
- Prioritize based on: recency, relevance to query, impact/importance

Search strategy:
1. Search all relevant databases (PubMed, AACT clinical trials)
2. ALWAYS supplement with web fetching to:
   - Find additional information not in databases
   - Access sponsor/institution websites
   - Get recent news and updates
   - Retrieve full-text content when needed
   - Verify and expand on database results
3. Synthesize all sources for comprehensive answers

For clinical trials - NEW ARCHITECTURE:
PRIMARY SOURCE - AACT Database:
- Use search_aact_trials FIRST - provides comprehensive clinical trials data from AACT database
- 559,000+ trials available with no rate limits
- Use uppercase status values: RECRUITING, ACTIVE_NOT_RECRUITING, NOT_YET_RECRUITING, COMPLETED
- For ALS searches, the condition "ALS" will automatically match related terms

FALLBACK - Links Server (when AACT unavailable):
- Use get_known_als_trials for curated list of 8 important ALS trials
- Use get_search_link to generate search URLs for clinical trials
- Use get_trial_link to generate direct links to specific trials

ADDITIONAL SOURCES:
- If specific NCT IDs are mentioned, can also use fetch__fetch_url with:
  https://clinicaltrials.gov/study/{NCT_ID}
- Search sponsor websites, medical news, and university pages for updates

ARCHITECTURE FLOW:
User Query → AACT Database (Primary)
                ↓
         If AACT unavailable
                ↓
         Links Server (Fallback)
                ↓
         Direct links to trial websites

Note: Direct API access is unavailable - using AACT database instead
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
        tools = await get_all_tools()

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

            # Execute tool calls in parallel for better performance
            from parallel_tool_execution import execute_tool_calls_parallel
            progress_text, tool_results_content = await execute_tool_calls_parallel(
                tool_calls=tool_calls,
                call_mcp_tool_func=call_mcp_tool
            )

            # Add progress text to full response and yield accumulated content
            full_response += progress_text
            if progress_text:
                yield filter_internal_tags(full_response)  # Yield full accumulated response

            # Add single user message with ALL tool results
            messages.append({
                "role": "user",
                "content": tool_results_content
            })

            # Smart reflection: Only add reflection prompt if results seem incomplete
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
                        {"type": "text", "text": "\n\n**SMART REFLECTION:** Based on the results so far, please evaluate:\n\n1. Do you have sufficient high-quality information to answer comprehensively?\n2. Are there important aspects that need more investigation?\n3. Would refining search terms or trying different databases help?\n\nIf confident with current information (found relevant studies/trials), proceed to synthesis with (**✅ ANSWER:**). Otherwise, use reflection markers (**🤔 REFLECTING:**) and search for missing information."}
                    ]
                    messages.append({
                        "role": "user",
                        "content": reflection_prompt
                    })
                    logger.info(f"Smart reflection triggered (low_conf:{low_conf_count}, high_conf:{high_conf_count}, results:{total_results})")
                else:
                    # High confidence - skip reflection and go straight to synthesis
                    logger.info(f"Skipping reflection - high confidence (low_conf:{low_conf_count}, high_conf:{high_conf_count}, results:{total_results})")
                    # Add a synthesis-only prompt
                    synthesis_prompt = [
                        {"type": "text", "text": "\n\n**HIGH CONFIDENCE RESULTS:** The search returned comprehensive information. Please proceed directly to synthesis with (**✅ SYNTHESIS:**) and provide a complete answer based on the findings."}
                    ]
                    messages.append({
                        "role": "user",
                        "content": synthesis_prompt
                    })
            else:
                # Subsequent iterations (tool_iteration > 1) - UPDATE existing synthesis without repeating workflow phases
                logger.info(f"Iteration {tool_iteration}: Updating synthesis with additional results")
                update_prompt = [
                    {"type": "text", "text": "\n\n**ADDITIONAL RESULTS:** You have gathered more information. Please UPDATE your previous synthesis by integrating these new findings. Do NOT repeat the planning/executing/reflecting phases - just provide an updated synthesis that incorporates both the previous and new information. Continue directly with the updated content, no phase markers needed."}
                ]
                messages.append({
                    "role": "user",
                    "content": update_prompt
                })

            # Second API call with tool results (with retry logic)
            logger.info("Starting second streaming API call with tool results...")
            logger.info(f"Messages array has {len(messages)} messages")
            logger.info(f"Last 3 messages: {json.dumps([{'role': m.get('role'), 'content_type': type(m.get('content')).__name__, 'content_len': len(str(m.get('content')))} for m in messages[-3:]], indent=2)}")
            # Log the actual tool results content
            logger.info(f"Tool results content ({len(tool_results_content)} items): {json.dumps(tool_results_content[:1], indent=2) if tool_results_content else 'EMPTY'}")  # Log first item only to avoid spam

            # Second streaming call for synthesis
            synthesis_response = ""
            additional_tool_calls = []

            # For subsequent iterations, use modified system prompt that doesn't require all phases
            iteration_system_prompt = system_prompt
            if tool_iteration > 1:
                iteration_system_prompt = """You are an AI assistant specializing in ALS (Amyotrophic Lateral Sclerosis) research.

You are continuing your research with additional results. Please integrate the new findings into an updated response.

IMPORTANT: Do NOT repeat the workflow phases (Planning/Executing/Reflecting/Synthesis) - you've already done those.
Simply provide updated content that incorporates both previous and new information.
Start your response directly with the updated information, no phase markers needed."""

            # Limit tools on subsequent iterations to prevent endless loops
            available_tools = tools if tool_iteration == 1 else []  # No more tools after first iteration

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

            full_response += synthesis_response
            # Yield the full accumulated response including planning, execution, and synthesis
            yield filter_internal_tags(full_response)

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

                    full_response += final_synthesis
                    # Yield the full accumulated response
                    yield filter_internal_tags(full_response)

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
                        call_mcp_tool_func=call_mcp_tool
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

                    # Set tool_calls for next iteration
                    tool_calls = additional_tool_calls
            else:
                # No more tool calls, exit loop
                tool_calls = []

        if tool_iteration >= max_tool_iterations:
            logger.warning(f"Reached maximum tool iterations ({max_tool_iterations})")

        # Force synthesis if we haven't provided one yet
        if tool_iteration > 0 and "✅ SYNTHESIS:" not in full_response:
            logger.warning(f"No synthesis found after {tool_iteration} iterations, forcing synthesis")

            # Add a forced synthesis prompt
            synthesis_prompt_content = [{"type": "text", "text": "You MUST now provide a ✅ SYNTHESIS phase. Synthesize whatever information you've gathered, even if searches were limited. If you couldn't find specific research, provide knowledge-based answers with appropriate caveats."}]
            messages.append({
                "role": "user",
                "content": synthesis_prompt_content
            })

            # Make final synthesis call without tools
            forced_synthesis = ""
            async for response_text, _, _ in stream_with_retry(
                client=client,
                messages=messages,
                tools=[],  # No tools - just synthesize
                system_prompt=system_prompt,
                max_retries=1,
                model=ANTHROPIC_MODEL,
                max_tokens=MAX_RESPONSE_TOKENS,
                stream_name="forced synthesis"
            ):
                forced_synthesis = response_text

            full_response += "\n\n" + forced_synthesis
            # Yield the full accumulated response with forced synthesis
            yield filter_internal_tags(full_response)

        # No final yield needed - response has already been yielded incrementally

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

    try:
        # Setup MCP servers
        logger.info("Setting up MCP servers...")
        await setup_mcp_servers()
        logger.info("MCP servers initialized successfully")

        # Start memory cleanup task
        cleanup_task = asyncio.create_task(cleanup_memory())
        logger.info("Memory cleanup task started")

    except Exception as e:
        logger.error(f"Failed to initialize MCP servers: {e}", exc_info=True)
        raise
    
    # Create Gradio interface with export button
    with gr.Blocks() as demo:
        gr.Markdown("# 🧬 ALSARA - ALS Agentic Research Assistant ")
        gr.Markdown("Ask questions about ALS research, treatments, and clinical trials. This agent searches PubMed, AACT clinical trials database, and other sources in real-time.")

        # Show LLM configuration status using unified client
        llm_status = f"🤖 **LLM Provider:** {client.get_provider_display_name()}"
        gr.Markdown(llm_status)

        with gr.Tabs():
            with gr.TabItem("Chat"):
                chatbot = gr.Chatbot(
                    height=600,
                    show_label=False,
                    allow_tags=True,  # Allow custom HTML tags from LLMs (Gradio 6 default)
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
                    label="Type your question or use voice input"
                )
            with gr.Column(scale=1):
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
            speak_btn = gr.Button("🔊 Read Last Response", variant="secondary", interactive=False)

        # Audio output component (initially hidden)
        with gr.Row(visible=False) as audio_row:
            audio_output = gr.Audio(
                label="🔊 Voice Output",
                type="filepath",
                autoplay=True,
                visible=True
            )

        gr.Examples(
            examples=[
                "Psilocybin trials and use in therapy",
                "Role of Omega-3 and omega-6 fatty acids in ALS treatment",
                "List the main genes that should be tested for ALS gene therapy eligibility",
                "What are the latest SOD1-targeted therapies in recent preprints?",
                "Find recruiting clinical trials for bulbar-onset ALS",
                "Explain the role of TDP-43 in ALS pathology",
                "What is the current status of tofersen clinical trials?",
                "Are there any new combination therapies being studied?",
                "What's the latest research on ALS biomarkers from the past 60 days?",
                "Search PubMed for recent ALS gene therapy research"
            ],
            inputs=msg
        )

        # Chat interface logic with improved error handling
        async def respond(message: str, history: Optional[List[Dict[str, str]]]) -> AsyncGenerator[List[Dict[str, str]], None]:
            history = history or []
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
                # Check if ElevenLabs server is available
                try:
                    server_tools = await mcp_manager.list_all_tools()
                    elevenlabs_available = any('elevenlabs' in tool for tool in server_tools.keys())
                    if not elevenlabs_available:
                        logger.error("ElevenLabs server not available in MCP tools")
                        return gr.update(visible=True), gr.update(
                            value=None,
                            label="⚠️ Voice service not available - Please set ELEVENLABS_API_KEY"
                        )
                except Exception as e:
                    logger.error(f"Failed to check ElevenLabs availability: {e}", exc_info=True)
                    return gr.update(visible=True), gr.update(
                        value=None,
                        label="⚠️ Voice service not available"
                    )

                # Remove phase markers from text
                clean_text = re.sub(r'\*\*[🎯🔧🤔✅].*?:\*\*', '', clean_text)
                # Call ElevenLabs text-to-speech through MCP
                logger.info(f"Calling ElevenLabs text-to-speech with {len(clean_text)} characters...")
                try:
                    result = await call_mcp_tool(
                        "elevenlabs__text_to_speech",
                        {"text": clean_text, "speed": 0.95}  # Slightly slower for clarity
                    )
                except Exception as e:
                    logger.error(f"MCP tool call failed: {e}", exc_info=True)
                    raise

                # Parse the result
                try:
                    result_data = json.loads(result) if isinstance(result, str) else result
                    # Check for API key error
                    if "ELEVENLABS_API_KEY not configured" in str(result):
                        logger.error("ElevenLabs API key not configured - found in result string")
                        return gr.update(visible=True), gr.update(
                            value=None,
                            label="⚠️ Voice service unavailable - Please set ELEVENLABS_API_KEY environment variable"
                        )

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
            respond, [msg, chatbot], [chatbot],
            api_name="chat"
        ).then(
            update_speak_button, None, [speak_btn]
        ).then(
            lambda: "", None, [msg]
        )

        # Add event handler for audio input
        audio_input.stop_recording(
            process_voice_input,
            inputs=[audio_input],
            outputs=[msg]
        ).then(
            lambda: None,
            outputs=[audio_input]  # Clear audio after processing
        )

        submit_btn.click(
            respond, [msg, chatbot], [chatbot],
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

        speak_btn.click(
            speak_last_response, [chatbot], [audio_row, audio_output],
            api_name="speak"
        )

    # Enable queue for streaming to work
    demo.queue()

    try:
        # Use environment variable for port, default to 7860 for HuggingFace
        port = int(os.environ.get("GRADIO_SERVER_PORT", 7860))
        demo.launch(
            server_name="0.0.0.0",
            server_port=port,
            share=False,
            ssr_mode=False  # Disable SSR for compatibility with async initialization
        )
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Error during launch: {e}", exc_info=True)
    finally:
        # Cleanup
        logger.info("Cleaning up resources...")
        await cleanup_mcp_servers()

if __name__ == "__main__":
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
