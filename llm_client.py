#!/usr/bin/env python3
"""
Unified LLM Client - Single interface for all LLM providers
Handles Anthropic, SambaNova, and automatic fallback logic internally
"""

import os
import logging
import asyncio
import httpx
from typing import AsyncGenerator, List, Dict, Any, Optional, Tuple
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class UnifiedLLMClient:
    """
    Unified client that abstracts all LLM provider logic.
    Provides a single, clean interface to the application.
    """

    def __init__(self):
        """Initialize the unified client with automatic provider selection"""
        self.primary_client = None
        self.fallback_router = None
        self.provider_name = None
        self.config = self._load_configuration()
        self._initialize_providers()

    def _load_configuration(self) -> Dict[str, Any]:
        """Load configuration from environment variables"""
        return {
            "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
            "use_fallback": os.getenv("USE_FALLBACK_LLM", "false").lower() == "true",
            "provider_preference": os.getenv("LLM_PROVIDER_PREFERENCE", "auto"),
            "default_model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"),
            "fallback_model": os.getenv("ANTHROPIC_FALLBACK_MODEL", "claude-sonnet-4-20250514"),
            "max_retries": int(os.getenv("LLM_MAX_RETRIES", "2")),
            "is_hf_space": os.getenv("SPACE_ID") is not None,
            "enable_smart_routing": os.getenv("ENABLE_SMART_ROUTING", "false").lower() == "true"
        }

    def _initialize_providers(self):
        """Initialize LLM providers based on configuration"""

        # Try to initialize Anthropic first
        if self.config["anthropic_api_key"]:
            try:
                self.primary_client = AsyncAnthropic(api_key=self.config["anthropic_api_key"])
                self.provider_name = "Anthropic Claude"
                logger.info("Anthropic client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Anthropic client: {e}")
                self.primary_client = None

        # Initialize fallback if needed
        if self.config["use_fallback"] or not self.primary_client:
            try:
                from llm_providers import llm_router
                self.fallback_router = llm_router

                if not self.primary_client:
                    self.provider_name = "SambaNova Llama 3.3 70B"
                    logger.info("Using SambaNova as primary provider")
                else:
                    logger.info("SambaNova fallback configured for automatic failover")

            except ImportError:
                logger.warning("Fallback LLM provider not available")

                if not self.primary_client:
                    self._raise_configuration_error()

    def _raise_configuration_error(self):
        """Raise appropriate error for missing configuration"""
        if self.config["is_hf_space"]:
            raise ValueError(
                "🚨 No LLM provider configured!\n\n"
                "Option 1: Add your Anthropic API key as a Space secret:\n"
                "1. Go to your Space Settings\n"
                "2. Add secret: ANTHROPIC_API_KEY = your_key\n\n"
                "Option 2: Enable free SambaNova fallback:\n"
                "Add secret: USE_FALLBACK_LLM = true"
            )
        else:
            raise ValueError(
                "No LLM provider configured.\n\n"
                "Option 1: Add to .env file:\n"
                "ANTHROPIC_API_KEY=your_api_key_here\n\n"
                "Option 2: Enable free SambaNova:\n"
                "USE_FALLBACK_LLM=true"
            )

    async def stream(
        self,
        messages: List[Dict],
        tools: List[Dict] = None,
        system_prompt: str = None,
        model: str = None,
        max_tokens: int = 8192,
        temperature: float = 0.7
    ) -> AsyncGenerator[Tuple[str, List[Dict], str], None]:
        """
        Stream responses from the LLM with automatic fallback.

        This is the main interface - it handles all provider selection,
        retries, and fallback logic internally.

        Yields: (response_text, tool_calls, provider_used)
        """

        # Use default model if not specified
        if model is None:
            model = self.config["default_model"]

        # Track which provider we're using
        provider_used = self.provider_name

        # Determine provider order based on preference
        use_anthropic_first = True
        if self.config["provider_preference"] == "cost_optimize" and self.fallback_router:
            # With cost_optimize, prefer SambaNova first
            use_anthropic_first = False

        # Apply smart routing if enabled
        if self.config.get("enable_smart_routing", False) and self.primary_client and self.fallback_router:
            # Extract the last user message for analysis
            last_message = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    if isinstance(msg.get("content"), str):
                        last_message = msg["content"]
                    elif isinstance(msg.get("content"), list):
                        # Extract text from content blocks
                        for block in msg["content"]:
                            if isinstance(block, dict) and block.get("type") == "text":
                                last_message = block.get("text", "")
                                break
                    break

            if last_message:
                # Classify the query
                query_type = self.classify_query_complexity(
                    last_message,
                    len(tools) if tools else 0
                )

                # Override provider preference based on classification
                if query_type == "simple":
                    if use_anthropic_first:
                        logger.info(f"Smart routing: Directing simple query to Llama for cost savings: '{last_message[:80]}...'")
                    use_anthropic_first = False
                elif query_type == "complex":
                    if not use_anthropic_first:
                        logger.info(f"Smart routing: Directing complex query to Claude for better quality: '{last_message[:80]}...'")
                    use_anthropic_first = True

        # Try first provider based on preference
        if use_anthropic_first and self.primary_client:
            try:
                async for result in self._stream_anthropic(
                    messages, tools, system_prompt, model, max_tokens, temperature
                ):
                    yield result
                return  # Success, exit
            except Exception as e:
                is_overloaded = (
                    (hasattr(e, 'status_code') and e.status_code in (429, 529, 503))
                    or 'overloaded' in str(e).lower()
                )

                # If primary model is overloaded, try fallback model before giving up
                fallback_model = self.config.get("fallback_model")
                if is_overloaded and fallback_model and fallback_model != model:
                    logger.warning(f"Model {model} overloaded, falling back to {fallback_model}")
                    try:
                        async for result in self._stream_anthropic(
                            messages, tools, system_prompt, fallback_model, max_tokens, temperature
                        ):
                            text, tc, _ = result
                            yield (text, tc, f"Anthropic Claude (fallback: {fallback_model})")
                        return
                    except Exception as fallback_err:
                        logger.warning(f"Fallback model {fallback_model} also failed: {fallback_err}")

                logger.warning(f"Primary provider failed: {e}")

                # Fall through to SambaNova fallback if available
                if not self.fallback_router:
                    raise

        # Try fallback provider
        if self.fallback_router:
            if not use_anthropic_first or not self.primary_client:
                logger.info("Using SambaNova as primary provider (cost_optimize mode)" if not use_anthropic_first else "Using fallback LLM provider")

            try:
                # Override provider preference to force SambaNova when smart routing decided to use it
                effective_preference = "cost_optimize" if not use_anthropic_first else self.config["provider_preference"]

                async for text, tool_calls, provider in self.fallback_router.stream_with_fallback(
                    messages=messages,
                    tools=tools or [],
                    system_prompt=system_prompt,
                    model=model,
                    max_tokens=max_tokens,
                    provider_preference=effective_preference
                ):
                    yield (text, tool_calls, provider)

                # If we used SambaNova first successfully with cost_optimize, we're done
                if not use_anthropic_first:
                    return

            except Exception as e:
                if not use_anthropic_first and self.primary_client:
                    # SambaNova failed in cost_optimize mode, try Anthropic
                    logger.warning(f"SambaNova failed in cost_optimize mode: {e}, falling back to Anthropic")
                    try:
                        async for result in self._stream_anthropic(
                            messages, tools, system_prompt, model, max_tokens, temperature
                        ):
                            yield result
                        return  # Success, exit
                    except Exception as anthropic_error:
                        logger.error(f"All LLM providers failed: SambaNova: {e}, Anthropic: {anthropic_error}")
                        raise RuntimeError("All LLM providers failed. Please check configuration.")
                else:
                    logger.error(f"All LLM providers failed: {e}")
                    raise RuntimeError("All LLM providers failed. Please check configuration.")
        else:
            raise RuntimeError("No LLM providers available")

    async def _stream_anthropic(
        self,
        messages: List[Dict],
        tools: List[Dict],
        system_prompt: str,
        model: str,
        max_tokens: int,
        temperature: float
    ) -> AsyncGenerator[Tuple[str, List[Dict], str], None]:
        """Stream from Anthropic with retry logic"""

        retry_delay = 1
        last_error = None

        # Skip system message if it's in messages array
        api_messages = messages[1:] if messages and messages[0].get("role") == "system" else messages

        # Use system prompt or extract from messages
        if not system_prompt and messages and messages[0].get("role") == "system":
            system_prompt = messages[0].get("content", "")

        for attempt in range(self.config["max_retries"] + 1):
            try:
                logger.info(f"Streaming from Anthropic (attempt {attempt + 1})")

                accumulated_text = ""
                tool_calls = []

                # Create the stream
                stream_params = {
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": api_messages,
                    "temperature": temperature
                }

                if system_prompt:
                    stream_params["system"] = system_prompt

                if tools:
                    stream_params["tools"] = tools

                async with self.primary_client.messages.stream(**stream_params) as stream:
                    async for event in stream:
                        if event.type == "content_block_start":
                            if event.content_block.type == "tool_use":
                                tool_calls.append({
                                    "id": event.content_block.id,
                                    "name": event.content_block.name,
                                    "input": {}
                                })

                        elif event.type == "content_block_delta":
                            if event.delta.type == "text_delta":
                                accumulated_text += event.delta.text
                                yield (accumulated_text, tool_calls, "Anthropic Claude")

                    # Get final message
                    final_message = await stream.get_final_message()

                    # Rebuild tool calls from final message
                    tool_calls.clear()
                    for block in final_message.content:
                        if block.type == "tool_use":
                            tool_calls.append({
                                "id": block.id,
                                "name": block.name,
                                "input": block.input
                            })
                        elif block.type == "text" and block.text:
                            if block.text not in accumulated_text:
                                accumulated_text += block.text

                    yield (accumulated_text, tool_calls, "Anthropic Claude")
                    return  # Success

            except (httpx.RemoteProtocolError, httpx.ReadError) as e:
                last_error = e
                logger.warning(f"Network error on attempt {attempt + 1}: {e}")

                if attempt < self.config["max_retries"]:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    raise

            except Exception as e:
                # Retry on overloaded/rate-limit errors (status 429, 529, 503)
                is_retryable = False
                if hasattr(e, 'status_code') and e.status_code in (429, 529, 503):
                    is_retryable = True
                elif 'overloaded' in str(e).lower() or 'rate_limit' in str(e).lower():
                    is_retryable = True

                if is_retryable and attempt < self.config["max_retries"]:
                    logger.warning(f"Retryable API error on attempt {attempt + 1}: {e}")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                    continue

                logger.error(f"Anthropic streaming error: {e}")
                raise

    def get_status(self) -> Dict[str, Any]:
        """Get current client status and configuration"""
        return {
            "primary_provider": "Anthropic" if self.primary_client else None,
            "fallback_enabled": bool(self.fallback_router),
            "current_provider": self.provider_name,
            "provider_preference": self.config["provider_preference"],
            "max_retries": self.config["max_retries"]
        }

    def is_using_llama_primary(self) -> bool:
        """Check if Llama/SambaNova is the primary provider"""
        # Check if cost_optimize preference is set and fallback is available
        if self.config.get("provider_preference") == "cost_optimize" and self.fallback_router:
            return True
        # Check if we have no Anthropic client and are using SambaNova
        if not self.primary_client and self.fallback_router:
            return True
        return False

    def classify_query_complexity(self, message: str, tools_count: int = 0) -> str:
        """
        Classify query as 'simple' or 'complex' based on content analysis.

        Args:
            message: The user's query text
            tools_count: Number of tools available for this query

        Returns:
            'simple' | 'complex' - The query classification
        """
        message_lower = message.lower()

        # Simple query indicators (good for Llama)
        simple_patterns = [
            "what is", "define", "when was", "who is", "list of",
            "how many", "name the", "what does", "explain what",
            "is there", "are there", "can you list", "tell me about",
            "what are the symptoms", "side effects of", "list the",
            "symptoms of", "treatment for", "causes of"
        ]

        # Complex query indicators (better for Claude)
        complex_patterns = [
            "analyze", "compare", "evaluate", "synthesize", "comprehensive",
            "all", "every", "detailed", "mechanism", "pathophysiology",
            "genotyping", "gene therapy", "combination therapy",
            "latest research", "recent studies", "cutting-edge",
            "molecular", "genetic mutation", "therapeutic pipeline",
            "clinical trial results", "meta-analysis", "systematic review",
            # Enhanced trial-related patterns
            "trials", "clinical trials", "studies", "clinical study",
            "NCT", "recruiting", "enrollment", "study protocol",
            "phase 1", "phase 2", "phase 3", "phase 4", "early phase",
            "investigational", "experimental", "novel treatment",
            "treatment pipeline", "research pipeline", "drug development"
        ]

        # Count pattern matches
        simple_score = sum(1 for pattern in simple_patterns if pattern in message_lower)
        complex_score = sum(1 for pattern in complex_patterns if pattern in message_lower)

        # Decision logic
        if complex_score > 0:
            # Any complex indicator suggests complex query
            return "complex"
        elif simple_score > 0 and len(message) < 150:
            # Simple pattern and short query
            return "simple"
        elif len(message) > 300:
            # Long queries are likely complex
            return "complex"
        elif tools_count > 8:
            # Many tools suggest complex analysis needed
            return "complex"
        else:
            # Default to complex for safety (better quality)
            return "complex" if self.primary_client else "simple"

    def get_provider_display_name(self) -> str:
        """Get a user-friendly provider status string"""
        if self.primary_client and self.fallback_router:
            # Both providers available
            if self.config["provider_preference"] == "cost_optimize":
                status = "SambaNova Llama 3.3 70B (primary, cost-optimized) with Anthropic Claude fallback"
            elif self.config["provider_preference"] == "quality_first":
                status = "Anthropic Claude (primary, quality-first) with SambaNova fallback"
            else:  # auto
                status = "Anthropic Claude (with SambaNova fallback)"
        elif self.primary_client:
            status = "Anthropic Claude"
        elif self.fallback_router:
            status = f"SambaNova Llama 3.3 70B ({self.config['provider_preference']} mode)"
        else:
            status = "Not configured"

        return status

    async def cleanup(self):
        """Clean up resources"""
        if self.fallback_router:
            try:
                await self.fallback_router.cleanup()
            except:
                pass

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.cleanup()


# Global instance (optional - can be created per request instead)
_global_client: Optional[UnifiedLLMClient] = None


def get_llm_client() -> UnifiedLLMClient:
    """Get or create the global LLM client instance"""
    global _global_client
    if _global_client is None:
        _global_client = UnifiedLLMClient()
    return _global_client


async def cleanup_global_client():
    """Clean up the global client instance"""
    global _global_client
    if _global_client:
        await _global_client.cleanup()
        _global_client = None