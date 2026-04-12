#!/usr/bin/env python3
"""
Helper functions to consolidate duplicate code in als_agent_app.py
Refactored to improve efficiency and reduce redundancy
"""

import asyncio
import httpx
import logging
import os
from typing import AsyncGenerator, List, Dict, Any, Optional, Tuple
from llm_client import UnifiedLLMClient

logger = logging.getLogger(__name__)


async def stream_with_retry(
    client,
    messages: List[Dict],
    tools: List[Dict],
    system_prompt: str,
    max_retries: int = 2,
    model: str = None,
    max_tokens: int = 8192,
    stream_name: str = "API call",
    temperature: float = 0.7
) -> AsyncGenerator[Tuple[str, List[Dict], str], None]:
    """
    Simplified wrapper that delegates to UnifiedLLMClient.

    The client parameter can be:
    - An Anthropic client (for backward compatibility)
    - A UnifiedLLMClient instance
    - None (will create a UnifiedLLMClient)

    Yields: (response_text, tool_calls, provider_used) tuples
    """

    # If client is None or is an Anthropic client, use UnifiedLLMClient
    if client is None or not hasattr(client, 'stream'):
        # Create or get a UnifiedLLMClient instance
        llm_client = UnifiedLLMClient()

        logger.info(f"Using {llm_client.get_provider_display_name()} for {stream_name}")

        try:
            # Use the unified client's stream method
            async for text, tool_calls, provider in llm_client.stream(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature
            ):
                yield (text, tool_calls, provider)
        finally:
            # Clean up if we created the client
            await llm_client.cleanup()

    else:
        # Client is already a UnifiedLLMClient
        logger.info(f"Using provided {client.get_provider_display_name()} for {stream_name}")

        async for text, tool_calls, provider in client.stream(
            messages=messages,
            tools=tools,
            system_prompt=system_prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature
        ):
            yield (text, tool_calls, provider)


async def execute_tool_calls(
    tool_calls: List[Dict],
    call_mcp_tool_func
) -> Tuple[str, List[Dict]]:
    """
    Execute tool calls and collect results.
    Consolidates duplicate tool execution logic.
    Now includes self-correction hints for zero results.

    Returns: (progress_text, tool_results_content)
    """
    progress_text = ""
    tool_results_content = []
    zero_result_tools = []

    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["input"]

        # Single, clean execution marker with search info
        tool_display = tool_name.replace('__', ' → ')

        # Show key search parameters
        search_info = ""
        if "query" in tool_args:
            search_info = f" `{tool_args['query'][:50]}{'...' if len(tool_args['query']) > 50 else ''}`"
        elif "condition" in tool_args:
            search_info = f" `{tool_args['condition'][:50]}{'...' if len(tool_args['condition']) > 50 else ''}`"

        progress_text += f"\n🔧 **Searching:** {tool_display}{search_info}\n"

        # Call MCP tool
        tool_result = await call_mcp_tool_func(tool_name, tool_args)

        # Check for zero results to enable self-correction
        if isinstance(tool_result, str):
            result_lower = tool_result.lower()
            if any(phrase in result_lower for phrase in [
                "no results found", "0 results", "no papers found",
                "no trials found", "no preprints found", "not found",
                "zero results", "no matches"
            ]):
                zero_result_tools.append((tool_name, tool_args))

                # Add self-correction hint to the result
                tool_result += "\n\n**SELF-CORRECTION HINT:** No results found with this query. Consider:\n"
                tool_result += "1. Broadening search terms (remove qualifiers)\n"
                tool_result += "2. Using alternative terminology or synonyms\n"
                tool_result += "3. Searching related concepts\n"
                tool_result += "4. Checking for typos in search terms"

        # Add to results array
        tool_results_content.append({
            "type": "tool_result",
            "tool_use_id": tool_call["id"],
            "content": tool_result
        })

    return progress_text, tool_results_content


def build_assistant_message(
    text_content: str,
    tool_calls: List[Dict],
    strip_markers: List[str] = None
) -> List[Dict]:
    """
    Build assistant message content with text and tool uses.
    Consolidates duplicate message building logic.

    Args:
        text_content: Text content to include
        tool_calls: List of tool calls to include
        strip_markers: Optional list of text markers to strip from content

    Returns: List of content blocks for assistant message
    """
    assistant_content = []

    # Process text content
    if text_content and text_content.strip():
        processed_text = text_content

        # Strip any specified markers
        if strip_markers:
            for marker in strip_markers:
                processed_text = processed_text.replace(marker, "")

        processed_text = processed_text.strip()

        if processed_text:
            assistant_content.append({
                "type": "text",
                "text": processed_text
            })

    # Add tool uses
    for tc in tool_calls:
        assistant_content.append({
            "type": "tool_use",
            "id": tc["id"],
            "name": tc["name"],
            "input": tc["input"]
        })

    return assistant_content


def should_continue_iterations(
    iteration_count: int,
    max_iterations: int,
    tool_calls: List[Dict]
) -> bool:
    """
    Check if tool iterations should continue.
    Centralizes iteration control logic.
    """
    if not tool_calls:
        return False

    if iteration_count >= max_iterations:
        logger.warning(f"Reached maximum tool iterations ({max_iterations})")
        return False

    return True