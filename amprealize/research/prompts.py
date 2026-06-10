"""Research prompts — delegates to ``amprealize.enterprise.research.prompts``.

When ``amprealize-enterprise`` is not installed, comprehension/evaluation
constants are empty and format helpers raise ``ImportError``.
"""

try:
    from amprealize.enterprise.research.prompts import (
        COMPREHENSION_SYSTEM_PROMPT,
        COMPREHENSION_USER_PROMPT,
        CONCLUSION_PROMPT,
        EVALUATION_SYSTEM_PROMPT,
        EVALUATION_USER_PROMPT,
        FIGURE_CAPTION_PROMPT,
        RECOMMENDATION_SYSTEM_PROMPT,
        RECOMMENDATION_USER_PROMPT,
        RESEARCH_SYSTEM_PROMPT,
        SECTION_PROMPT,
        SYNTHESIS_SYSTEM_PROMPT,
        TABLE_CAPTION_PROMPT,
        format_comprehension_prompt,
        format_evaluation_prompt,
        format_recommendation_prompt,
        format_research_prompt,
        format_section_prompt,
        format_synthesis_prompt,
    )
except ImportError:
    COMPREHENSION_SYSTEM_PROMPT = ""
    COMPREHENSION_USER_PROMPT = ""
    EVALUATION_SYSTEM_PROMPT = ""
    EVALUATION_USER_PROMPT = ""
    RECOMMENDATION_SYSTEM_PROMPT = ""
    RECOMMENDATION_USER_PROMPT = ""
    RESEARCH_SYSTEM_PROMPT = ""
    SYNTHESIS_SYSTEM_PROMPT = ""
    SECTION_PROMPT = ""
    CONCLUSION_PROMPT = ""
    FIGURE_CAPTION_PROMPT = ""
    TABLE_CAPTION_PROMPT = ""

    def format_comprehension_prompt(*args: object, **kwargs: object) -> str:
        raise ImportError("Research prompts require amprealize-enterprise[research]")

    def format_evaluation_prompt(*args: object, **kwargs: object) -> str:
        raise ImportError("Research prompts require amprealize-enterprise[research]")

    def format_recommendation_prompt(*args: object, **kwargs: object) -> str:
        raise ImportError("Research prompts require amprealize-enterprise[research]")

    def format_research_prompt(*args: object, **kwargs: object) -> str:
        raise ImportError("Research prompts require amprealize-enterprise[research]")

    def format_synthesis_prompt(*args: object, **kwargs: object) -> str:
        raise ImportError("Research prompts require amprealize-enterprise[research]")

    def format_section_prompt(*args: object, **kwargs: object) -> str:
        raise ImportError("Research prompts require amprealize-enterprise[research]")
