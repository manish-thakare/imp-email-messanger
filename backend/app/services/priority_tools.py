"""Small, read-only LangChain tools shared with the second-pass classifier."""

import json

from app.core.email_constants import PRIORITY_RULES

try:
    from langchain_core.tools import tool
except ImportError:  # Keep rules and tests usable before optional dependencies are installed.
    def tool(function):
        return function


@tool
def get_priority_rule_catalog() -> str:
    """Return the reviewed weighted rule catalog for model context."""
    return json.dumps(
        [
            {
                "key": rule.key,
                "category": rule.category,
                "weight": rule.weight,
                "phrases": list(rule.phrases),
            }
            for rule in PRIORITY_RULES
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
