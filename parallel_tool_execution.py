#!/usr/bin/env python3
"""
Parallel tool execution optimization for ALS Research Agent
This module replaces sequential tool execution with parallel execution
to reduce response time by ~60-70% for multi-tool queries.
"""

import asyncio
from typing import List, Dict, Tuple, Any
import logging

logger = logging.getLogger(__name__)


async def execute_single_tool(
    tool_call: Dict,
    call_mcp_tool_func,
    index: int
) -> Tuple[int, str, Dict]:
    """
    Execute a single tool call asynchronously.
    Returns (index, progress_text, result_dict) to maintain order.
    """
    tool_name = tool_call["name"]
    tool_args = tool_call["input"]

    # Show search info in progress text
    tool_display = tool_name.replace('__', ' → ')
    search_info = ""
    if "query" in tool_args:
        search_info = f" `{tool_args['query'][:50]}{'...' if len(tool_args['query']) > 50 else ''}`"
    elif "condition" in tool_args:
        search_info = f" `{tool_args['condition'][:50]}{'...' if len(tool_args['condition']) > 50 else ''}`"

    try:
        # Call MCP tool
        start_time = asyncio.get_event_loop().time()
        tool_result = await call_mcp_tool_func(tool_name, tool_args)
        elapsed = asyncio.get_event_loop().time() - start_time

        logger.info(f"Tool {tool_name} completed in {elapsed:.2f}s")

        # Check for zero results to provide clear indicators
        has_results = True
        results_count = 0

        if isinstance(tool_result, str):
            result_lower = tool_result.lower()

            # Check for specific result counts
            import re
            count_matches = re.findall(r'found (\d+) (?:papers?|trials?|preprints?|results?)', result_lower)
            if count_matches:
                results_count = int(count_matches[0])

            # Check for no results
            if any(phrase in result_lower for phrase in [
                "no results found", "0 results", "no papers found",
                "no trials found", "no preprints found", "not found",
                "zero results", "no matches"
            ]) or results_count == 0:
                has_results = False

        # Create clear success/failure indicator
        if has_results:
            if results_count > 0:
                progress_text = f"\n✅ **Found {results_count} results:** {tool_display}{search_info}"
            else:
                progress_text = f"\n✅ **Success:** {tool_display}{search_info}"
        else:
            progress_text = f"\n⚠️ **No results:** {tool_display}{search_info} - will try alternatives"

        # Add timing for long operations
        if elapsed > 5:
            progress_text += f" (took {elapsed:.1f}s)"

        # Check for zero results to enable self-correction
        if not has_results:
                # Add self-correction hint to the result
                tool_result += "\n\n**SELF-CORRECTION HINT:** No results found with this query. Consider:\n"
                tool_result += "1. Broadening search terms (remove qualifiers)\n"
                tool_result += "2. Using alternative terminology or synonyms\n"
                tool_result += "3. Searching related concepts\n"
                tool_result += "4. Checking for typos in search terms"

        result_dict = {
            "type": "tool_result",
            "tool_use_id": tool_call["id"],
            "content": tool_result
        }

        return index, progress_text, result_dict

    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {e}")

        # Clear failure indicator for errors
        progress_text = f"\n❌ **Failed:** {tool_display}{search_info} - {str(e)[:50]}"

        error_result = {
            "type": "tool_result",
            "tool_use_id": tool_call["id"],
            "content": f"Error executing tool: {str(e)}"
        }
        return index, progress_text, error_result


async def execute_tool_calls_parallel(
    tool_calls: List[Dict],
    call_mcp_tool_func
) -> Tuple[str, List[Dict]]:
    """
    Execute tool calls in parallel and collect results.
    Maintains the original order of tool calls in results.

    Returns: (progress_text, tool_results_content)
    """
    if not tool_calls:
        return "", []

    # Track execution time for progress reporting
    start_time = asyncio.get_event_loop().time()

    # Log parallel execution
    logger.info(f"Executing {len(tool_calls)} tools in parallel")

    # Create tasks for parallel execution
    tasks = [
        execute_single_tool(tool_call, call_mcp_tool_func, i)
        for i, tool_call in enumerate(tool_calls)
    ]

    # Execute all tasks in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Sort results by index to maintain original order
    sorted_results = sorted(
        [r for r in results if not isinstance(r, Exception)],
        key=lambda x: x[0]
    )

    # Combine results with progress summary
    completed_count = len(sorted_results)
    total_count = len(tool_calls)

    # Create progress summary with timing info
    elapsed_time = asyncio.get_event_loop().time() - start_time

    if elapsed_time > 5:
        timing_info = f" in {elapsed_time:.1f}s"
    else:
        timing_info = ""

    progress_text = f"\n📊 **Search Progress:** Completed {completed_count}/{total_count} searches{timing_info}\n"

    tool_results_content = []

    for index, prog_text, result_dict in sorted_results:
        progress_text += prog_text
        tool_results_content.append(result_dict)

    # Handle any exceptions
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Task {i} failed with exception: {result}")
            # Add error result for failed tasks
            if i < len(tool_calls):
                tool_results_content.insert(i, {
                    "type": "tool_result",
                    "tool_use_id": tool_calls[i]["id"],
                    "content": f"Tool execution failed: {str(result)}"
                })

    return progress_text, tool_results_content


# Backward compatibility wrapper
async def execute_tool_calls_optimized(
    tool_calls: List[Dict],
    call_mcp_tool_func,
    parallel: bool = True
) -> Tuple[str, List[Dict]]:
    """
    Execute tool calls with optional parallel execution.

    Args:
        tool_calls: List of tool calls to execute
        call_mcp_tool_func: Function to call MCP tools
        parallel: If True, execute tools in parallel; if False, execute sequentially

    Returns: (progress_text, tool_results_content)
    """
    if parallel and len(tool_calls) > 1:
        # Use parallel execution for multiple tools
        return await execute_tool_calls_parallel(tool_calls, call_mcp_tool_func)
    else:
        # Fall back to sequential execution (import from original)
        from refactored_helpers import execute_tool_calls
        return await execute_tool_calls(tool_calls, call_mcp_tool_func)


def estimate_time_savings(num_tools: int, avg_tool_time: float = 3.5) -> Dict[str, float]:
    """
    Estimate time savings from parallel execution.

    Args:
        num_tools: Number of tools to execute
        avg_tool_time: Average time per tool in seconds

    Returns: Dictionary with timing estimates
    """
    sequential_time = num_tools * avg_tool_time
    # Parallel time is roughly the time of the slowest tool plus overhead
    parallel_time = avg_tool_time + 0.5  # 0.5s overhead for coordination

    savings = sequential_time - parallel_time
    savings_percent = (savings / sequential_time) * 100 if sequential_time > 0 else 0

    return {
        "sequential_time": sequential_time,
        "parallel_time": parallel_time,
        "time_saved": savings,
        "savings_percent": savings_percent
    }


# Test the optimization
if __name__ == "__main__":
    # Test time savings estimation
    for n in [2, 3, 4, 5]:
        estimates = estimate_time_savings(n)
        print(f"\n{n} tools:")
        print(f"  Sequential: {estimates['sequential_time']:.1f}s")
        print(f"  Parallel: {estimates['parallel_time']:.1f}s")
        print(f"  Savings: {estimates['time_saved']:.1f}s ({estimates['savings_percent']:.0f}%)")