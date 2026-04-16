"""Enterprise research prompt templates.

Imported by OSS as:

    from amprealize.enterprise.research.prompts import (
        RESEARCH_SYSTEM_PROMPT,
        SYNTHESIS_SYSTEM_PROMPT,
        SECTION_PROMPT,
        CONCLUSION_PROMPT,
        FIGURE_CAPTION_PROMPT,
        TABLE_CAPTION_PROMPT,
        format_research_prompt,
        format_synthesis_prompt,
        format_section_prompt,
    )
"""

from __future__ import annotations


# --- Prompt constants ---

RESEARCH_SYSTEM_PROMPT = (
    "You are a research analyst. Analyze the provided sources and extract key findings."
)

SYNTHESIS_SYSTEM_PROMPT = (
    "You are a research synthesizer. Combine findings into a coherent narrative."
)

SECTION_PROMPT = (
    "Write a detailed section on the given topic using the provided source material."
)

CONCLUSION_PROMPT = (
    "Write a conclusion summarizing the key findings and recommendations."
)

FIGURE_CAPTION_PROMPT = (
    "Generate a descriptive caption for the given figure."
)

TABLE_CAPTION_PROMPT = (
    "Generate a descriptive caption for the given table."
)


# --- Format functions ---

def format_research_prompt(topic: str, sources: list[str] | None = None) -> str:
    """Format a research prompt with topic and optional sources."""
    parts = [RESEARCH_SYSTEM_PROMPT, f"\nTopic: {topic}"]
    if sources:
        parts.append("\nSources:\n" + "\n".join(f"- {s}" for s in sources))
    return "\n".join(parts)


def format_synthesis_prompt(findings: list[str]) -> str:
    """Format a synthesis prompt from a list of findings."""
    return SYNTHESIS_SYSTEM_PROMPT + "\n\nFindings:\n" + "\n".join(
        f"{i+1}. {f}" for i, f in enumerate(findings)
    )


def format_section_prompt(topic: str, material: str = "") -> str:
    """Format a section-writing prompt."""
    return f"{SECTION_PROMPT}\n\nTopic: {topic}\n\nMaterial:\n{material}"
