#!/usr/bin/env python3
"""
ElevenLabs MCP Server for Voice Capabilities
Provides text-to-speech and speech-to-text for ALS Research Agent

This server enables voice accessibility features crucial for ALS patients
who may have limited mobility but retain cognitive function.
"""

from mcp.server.fastmcp import FastMCP
import httpx
import logging
import os
import base64
import json
from typing import Optional, Dict, Any
from pathlib import Path
import sys

# Add parent directory to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared import config
from shared.http_client import get_http_client

# Configure logging — force=True so we override any root handler FastMCP installed
logging.basicConfig(level=logging.INFO, force=True)
logger = logging.getLogger(__name__)

# Initialize MCP server
mcp = FastMCP("elevenlabs-voice")

# ElevenLabs API configuration
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"

# Default voice settings optimized for clarity (important for ALS patients)
DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel voice (clear and calm)
DEFAULT_MODEL = "eleven_turbo_v2_5"  # Turbo v2.5 - Fastest model available (40% faster than v2)

# Voice settings for accessibility
VOICE_SETTINGS = {
    "stability": 0.5,  # Balanced for speed and clarity (turbo model)
    "similarity_boost": 0.5,  # Balanced setting for faster processing
    "style": 0.0,  # Neutral style for clarity
    "use_speaker_boost": True  # Enhanced clarity
}


@mcp.tool()
async def text_to_speech(
    text: str,
    voice_id: Optional[str] = None,
    output_format: str = "mp3_44100_128",
    speed: float = 1.0
) -> str:
    """Convert text to speech optimized for ALS patients.

    Args:
        text: Text to convert to speech (research findings, paper summaries, etc.)
        voice_id: ElevenLabs voice ID (defaults to clear, calm voice)
        output_format: Audio format (mp3_44100_128, mp3_44100_192, pcm_16000, etc.)
        speed: Speech rate (0.5-2.0, default 1.0 - can be slower for clarity)

    Returns:
        Base64 encoded audio data and metadata
    """
    try:
        if not ELEVENLABS_API_KEY:
            return json.dumps({
                "status": "error",
                "error": "ELEVENLABS_API_KEY not configured",
                "message": "Please set your ElevenLabs API key in .env file"
            }, indent=2)

        # Limit text length to avoid ElevenLabs API timeouts
        # Testing shows 2500 chars is safe, 5000 chars times out
        max_length = 2500
        if len(text) > max_length:
            logger.warning(f"Text truncated from {len(text)} to {max_length} characters to avoid timeout")
            # Try to truncate at a sentence boundary
            truncated = text[:max_length]
            last_period = truncated.rfind('.')
            last_newline = truncated.rfind('\n')
            # Use the latest sentence/paragraph boundary
            boundary = max(last_period, last_newline)
            if boundary > max_length - 500:  # If there's a boundary in the last 500 chars
                text = truncated[:boundary + 1]
            else:
                text = truncated + "..."

        voice_id = voice_id or DEFAULT_VOICE_ID

        # Prepare the request
        url = f"{ELEVENLABS_API_BASE}/text-to-speech/{voice_id}"

        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        }

        # Adjust voice settings for speed
        adjusted_settings = VOICE_SETTINGS.copy()
        if speed < 1.0:
            # Slower speech - increase stability for clarity
            adjusted_settings["stability"] = min(1.0, adjusted_settings["stability"] + 0.1)

        payload = {
            "text": text,
            "model_id": DEFAULT_MODEL,
            "voice_settings": adjusted_settings
        }

        logger.info(f"Converting text to speech: {len(text)} characters")

        # Set timeout based on text length (with 2500 char limit, 45s should be enough)
        timeout = 45.0
        logger.info(f"Using timeout of {timeout} seconds")

        # Use shared HTTP client for connection pooling
        client = get_http_client(timeout=timeout)
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()

        # Get the audio data
        audio_data = response.content

        # Encode to base64 for transmission
        audio_base64 = base64.b64encode(audio_data).decode('utf-8')

        # Return structured response
        result = {
            "status": "success",
            "audio_base64": audio_base64,
            "format": output_format,
            "duration_estimate": len(text) / 150 * 60,  # Rough estimate: 150 words/min
            "text_length": len(text),
            "voice_id": voice_id,
            "message": "Audio generated successfully. Use the audio_base64 field to play the audio."
        }

        logger.info(f"Successfully generated {len(audio_data)} bytes of audio")
        return json.dumps(result, indent=2)

    except httpx.HTTPStatusError as e:
        logger.error(f"ElevenLabs API error: {e}")
        if e.response.status_code == 401:
            return json.dumps({
                "status": "error",
                "error": "Authentication failed",
                "message": "Check your ELEVENLABS_API_KEY"
            }, indent=2)
        elif e.response.status_code == 429:
            return json.dumps({
                "status": "error",
                "error": "Rate limit exceeded",
                "message": "Please wait before trying again"
            }, indent=2)
        else:
            return json.dumps({
                "status": "error",
                "error": f"API error: {e.response.status_code}",
                "message": str(e)
            }, indent=2)

    except Exception as e:
        logger.error(f"Unexpected error in text_to_speech: {e}")
        return json.dumps({
            "status": "error",
            "error": "Text-to-speech error",
            "message": str(e)
        }, indent=2)


@mcp.tool()
async def create_audio_summary(
    content: str,
    summary_type: str = "research",
    max_duration: int = 60
) -> str:
    """Create an audio summary of research content optimized for listening.

    This tool reformats technical content into a more listenable format
    before converting to speech - important for complex medical research.

    Args:
        content: Research content to summarize (paper abstract, findings, etc.)
        summary_type: Type of summary - "research", "clinical", "patient-friendly"
        max_duration: Target duration in seconds (affects summary length)

    Returns:
        Audio summary with both text and audio versions
    """
    try:
        # Calculate target word count (assuming 150 words per minute)
        target_words = int((max_duration / 60) * 150)

        # Process content based on summary type
        if summary_type == "patient-friendly":
            # Simplify medical jargon for patients/families
            processed_text = _simplify_medical_content(content, target_words)
        elif summary_type == "clinical":
            # Focus on clinical relevance
            processed_text = _extract_clinical_relevance(content, target_words)
        else:  # research
            # Standard research summary
            processed_text = _create_research_summary(content, target_words)

        # Add intro for context
        intro = "Here's your audio research summary: "
        final_text = intro + processed_text

        # Convert to speech
        tts_result = await text_to_speech(
            text=final_text,
            speed=0.95  # Slightly slower for complex content
        )

        # Parse the TTS result
        tts_data = json.loads(tts_result)

        if tts_data.get("status") != "success":
            return tts_result  # Return error from TTS

        # Return enhanced result
        result = {
            "status": "success",
            "audio_base64": tts_data["audio_base64"],
            "text_summary": processed_text,
            "summary_type": summary_type,
            "word_count": len(processed_text.split()),
            "estimated_duration": tts_data["duration_estimate"],
            "format": tts_data["format"],
            "message": f"Audio summary created: {summary_type} format, ~{int(tts_data['duration_estimate'])} seconds"
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Error creating audio summary: {e}")
        return json.dumps({
            "status": "error",
            "error": "Summary creation error",
            "message": str(e)
        }, indent=2)


@mcp.tool()
async def list_voices() -> str:
    """List available voices optimized for medical/research content.

    Returns voices suitable for clear pronunciation of medical terminology.
    """
    try:
        if not ELEVENLABS_API_KEY:
            return json.dumps({
                "status": "error",
                "error": "ELEVENLABS_API_KEY not configured",
                "message": "Please set your ElevenLabs API key in .env file"
            }, indent=2)

        url = f"{ELEVENLABS_API_BASE}/voices"
        headers = {"xi-api-key": ELEVENLABS_API_KEY}

        # Use shared HTTP client for connection pooling
        client = get_http_client(timeout=10.0)
        response = await client.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()
        voices = data.get("voices", [])

        # Filter and rank voices for medical content
        recommended_voices = []
        for voice in voices:
            # Prefer clear, professional voices
            labels = voice.get("labels", {})
            if any(label in ["clear", "professional", "narration"] for label in labels.values()):
                recommended_voices.append({
                    "voice_id": voice["voice_id"],
                    "name": voice["name"],
                    "preview_url": voice.get("preview_url"),
                    "description": voice.get("description", ""),
                    "recommended_for": "medical_content"
                })

        # Add all other voices
        other_voices = []
        for voice in voices:
            if voice["voice_id"] not in [v["voice_id"] for v in recommended_voices]:
                other_voices.append({
                    "voice_id": voice["voice_id"],
                    "name": voice["name"],
                    "preview_url": voice.get("preview_url"),
                    "description": voice.get("description", "")
                })

        result = {
            "status": "success",
            "recommended_voices": recommended_voices[:5],  # Top 5 recommended
            "other_voices": other_voices[:10],  # Limit for clarity
            "total_voices": len(voices),
            "message": "Recommended voices are optimized for clear medical terminology pronunciation"
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"Error listing voices: {e}")
        return json.dumps({
            "status": "error",
            "error": "Failed to list voices",
            "message": str(e)
        }, indent=2)


@mcp.tool()
async def pronunciation_guide(
    medical_terms: list[str],
    include_audio: bool = True
) -> str:
    """Generate pronunciation guide for medical terms.

    Critical for ALS patients/caregivers learning about complex terminology.

    Args:
        medical_terms: List of medical terms to pronounce
        include_audio: Whether to include audio pronunciation

    Returns:
        Pronunciation guide with optional audio
    """
    try:
        results = []

        for term in medical_terms[:10]:  # Limit to prevent long processing
            # Create phonetic breakdown
            phonetic = _get_phonetic_spelling(term)

            # Create pronunciation text
            pronunciation_text = f"{term}. {phonetic}. {term}."

            result_entry = {
                "term": term,
                "phonetic": phonetic
            }

            if include_audio:
                # Generate audio
                tts_result = await text_to_speech(
                    text=pronunciation_text,
                    speed=0.8  # Slower for clarity
                )

                tts_data = json.loads(tts_result)
                if tts_data.get("status") == "success":
                    result_entry["audio_base64"] = tts_data["audio_base64"]

            results.append(result_entry)

        return json.dumps({
            "status": "success",
            "pronunciations": results,
            "message": f"Generated pronunciation guide for {len(results)} terms"
        }, indent=2)

    except Exception as e:
        logger.error(f"Error creating pronunciation guide: {e}")
        return json.dumps({
            "status": "error",
            "error": "Pronunciation guide error",
            "message": str(e)
        }, indent=2)


# Helper functions for content processing

def _simplify_medical_content(content: str, target_words: int) -> str:
    """Simplify medical content for patient understanding."""
    # This would ideally use NLP, but for now, basic simplification

    # First, strip references for cleaner audio
    content = _strip_references(content)

    # Common medical term replacements
    replacements = {
        "amyotrophic lateral sclerosis": "ALS or Lou Gehrig's disease",
        "motor neurons": "nerve cells that control muscles",
        "neurodegeneration": "nerve cell damage",
        "pathogenesis": "disease development",
        "etiology": "cause",
        "prognosis": "expected outcome",
        "therapeutic": "treatment",
        "pharmacological": "drug-based",
        "intervention": "treatment",
        "mortality": "death rate",
        "morbidity": "illness rate"
    }

    simplified = content.lower()
    for term, replacement in replacements.items():
        simplified = simplified.replace(term, replacement)

    # Truncate to target length
    words = simplified.split()
    if len(words) > target_words:
        words = words[:target_words]
        simplified = " ".join(words) + "..."

    return simplified.capitalize()


def _extract_clinical_relevance(content: str, target_words: int) -> str:
    """Extract clinically relevant information."""
    # Focus on treatment, outcomes, and practical implications

    # First, strip references for cleaner audio
    content = _strip_references(content)

    # Look for key clinical phrases
    clinical_markers = [
        "treatment", "therapy", "outcome", "survival", "progression",
        "clinical trial", "efficacy", "safety", "adverse", "benefit",
        "patient", "dose", "administration"
    ]

    sentences = content.split(". ")
    relevant_sentences = []

    for sentence in sentences:
        if any(marker in sentence.lower() for marker in clinical_markers):
            relevant_sentences.append(sentence)

    result = ". ".join(relevant_sentences)

    # Truncate to target length
    words = result.split()
    if len(words) > target_words:
        words = words[:target_words]
        result = " ".join(words) + "..."

    return result


def _create_research_summary(content: str, target_words: int) -> str:
    """Create a research-focused summary."""
    # Extract key findings and implications

    # First, strip references section if present
    content = _strip_references(content)

    # Simply truncate for now (could be enhanced with NLP)
    words = content.split()
    if len(words) > target_words:
        words = words[:target_words]
        content = " ".join(words) + "..."

    return content


def _strip_references(content: str) -> str:
    """Remove references section and citations from content for audio reading."""
    import re

    # Extract only synthesis content if it's marked
    synthesis_match = re.search(r'✅\s*SYNTHESIS:?\s*(.*?)(?=##?\s*References|##?\s*Bibliography|$)',
                               content, flags=re.DOTALL | re.IGNORECASE)
    if synthesis_match:
        content = synthesis_match.group(1)

    # Remove References section (multiple possible formats)
    patterns_to_remove = [
        r'##?\s*References.*$',  # ## References or # References to end
        r'##?\s*Bibliography.*$',  # Bibliography section
        r'##?\s*Citations.*$',  # Citations section
        r'##?\s*Works Cited.*$',  # Works Cited section
        r'##?\s*Key References.*$',  # Key References section
    ]

    for pattern in patterns_to_remove:
        content = re.sub(pattern, '', content, flags=re.DOTALL | re.IGNORECASE)

    # Remove inline citations like [1], [2,3], [PMID: 12345678]
    content = re.sub(r'\[[\d,\s]+\]', '', content)  # [1], [2,3], etc.
    content = re.sub(r'\[PMID:\s*\d+\]', '', content)  # [PMID: 12345678]
    content = re.sub(r'\[NCT\d+\]', '', content)  # [NCT12345678]

    # Remove URLs for cleaner audio
    content = re.sub(r'https?://[^\s\)]+', '', content)
    content = re.sub(r'www\.[^\s\)]+', '', content)

    # Remove PMID/DOI/NCT references
    content = re.sub(r'PMID:\s*\d+', '', content)
    content = re.sub(r'DOI:\s*[^\s]+', '', content)
    content = re.sub(r'NCT\d{8}', '', content)

    # Remove markdown formatting that sounds awkward in audio
    content = re.sub(r'\*\*(.*?)\*\*', r'\1', content)  # Remove bold
    content = re.sub(r'\*(.*?)\*', r'\1', content)  # Remove italic
    content = re.sub(r'`(.*?)`', r'\1', content)  # Remove inline code
    content = re.sub(r'#{1,6}\s*', '', content)  # Remove headers
    content = re.sub(r'^[-*+]\s+', '', content, flags=re.MULTILINE)  # Remove bullet points
    content = re.sub(r'^\d+\.\s+', '', content, flags=re.MULTILINE)  # Remove numbered lists

    # Replace markdown links with just the text
    content = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', content)

    # Clean up extra whitespace
    content = re.sub(r'\s+', ' ', content)
    content = re.sub(r'\n{3,}', '\n\n', content)

    return content.strip()


def _get_phonetic_spelling(term: str) -> str:
    """Generate phonetic spelling for medical terms."""
    # Basic phonetic rules for medical terms
    # This could be enhanced with a medical pronunciation dictionary

    phonetic_map = {
        "amyotrophic": "AM-ee-oh-TROH-fik",
        "lateral": "LAT-er-al",
        "sclerosis": "skleh-ROH-sis",
        "tdp-43": "T-D-P forty-three",
        "riluzole": "RIL-you-zole",
        "edaravone": "ed-AR-a-vone",
        "tofersen": "TOE-fer-sen",
        "neurofilament": "NUR-oh-FIL-a-ment",
        "astrocyte": "AS-tro-site",
        "oligodendrocyte": "oh-li-go-DEN-dro-site"
    }

    term_lower = term.lower()
    if term_lower in phonetic_map:
        return phonetic_map[term_lower]

    # Basic syllable breakdown for unknown terms
    # This is very simplified and could be improved
    syllables = []
    current = ""
    for char in term:
        if char in "aeiouAEIOU" and current:
            syllables.append(current + char)
            current = ""
        else:
            current += char
    if current:
        syllables.append(current)

    return "-".join(syllables).upper()


if __name__ == "__main__":
    # Check for API key
    if not ELEVENLABS_API_KEY:
        logger.warning("ELEVENLABS_API_KEY not set in environment")
        logger.warning("Voice features will be limited without API key")
        logger.info("Get your API key at: https://elevenlabs.io")

    # Run the MCP server
    mcp.run(transport="stdio")