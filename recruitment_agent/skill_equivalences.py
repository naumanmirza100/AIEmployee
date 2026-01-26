"""
Shared skill equivalences and related-terms for matching job keywords to CV skills.
Node.js ↔ JavaScript, React ↔ ReactJS, etc. Used by Lead Qualification and Summarization.
"""

# Each key is a canonical form. Values are variants + related skills that should also match.
# E.g. "node.js" matches "javascript" because Node.js is built on JavaScript.
SKILL_EQUIVALENCES = {
    "llm": ["llms", "large language model", "language model"],
    "node": ["node.js", "nodejs", "javascript", "js"],
    "node.js": ["nodejs", "javascript", "js"],
    "nodejs": ["node.js", "javascript", "js"],
    "javascript": ["js", "ecmascript", "node.js", "nodejs"],
    "js": ["javascript", "ecmascript", "node.js", "nodejs"],
    "react": ["react.js", "reactjs"],
    "express": ["express.js", "expressjs"],
    "api": ["rest api", "restful", "graphql"],
    "mongodb": ["mongo"],
    "postgresql": ["postgres"],
    "typescript": ["ts"],
    "ts": ["typescript"],
    "python": ["py"],
    "django": ["django rest", "drf"],
    "vue": ["vue.js", "vuejs"],
    "angular": ["angularjs", "angular.js"],
    "aws": ["amazon web services"],
    "kubernetes": ["k8s"],
    "machine learning": ["ml", "machine-learning"],
    "artificial intelligence": ["ai"],
    "natural language processing": ["nlp"],
    "data science": ["data scientist", "datascience"],
}


def get_all_match_terms(keyword: str) -> set:
    """Return keyword + all equivalents/related terms (lowercase) for matching."""
    k = keyword.lower().strip()
    if not k:
        return set()
    out = {k}
    for canonical, variants in SKILL_EQUIVALENCES.items():
        if k == canonical or k in variants:
            out.add(canonical)
            out.update(variants)
            break
    return out


def skill_matches_keyword(skill_lower: str, keyword_lower: str) -> bool:
    """
    True if candidate skill matches job keyword (direct, equivalence, or substring).
    E.g. job "Node.js" matches skill "JavaScript"; job "JavaScript" matches skill "Node.js".
    """
    if not skill_lower or not keyword_lower:
        return False
    if skill_lower == keyword_lower:
        return True
    # Keyword's match set: what skills satisfy this job keyword
    kw_match = get_all_match_terms(keyword_lower)
    if skill_lower in kw_match:
        return True
    # Also check: skill's match set (e.g. skill "javascript" → variants include "node.js")
    skill_match = get_all_match_terms(skill_lower)
    if keyword_lower in skill_match:
        return True
    # Substring match
    if keyword_lower in skill_lower or skill_lower in keyword_lower:
        return True
    return False
