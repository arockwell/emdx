"""Privacy filtering service for wiki synthesis.

Three-layer pipeline to ensure generated wiki articles don't leak
sensitive information, casual remarks, or temporal noise:

Layer 1: Pre-processing (regex/rules, zero cost)
Layer 2: Prompt construction for LLM synthesis gate
Layer 3: Post-processing validation of LLM output
"""

from __future__ import annotations

import re

# ── Layer 1: Pre-processing patterns ────────────────────────────────

# Credentials and secrets
_CREDENTIAL_PATTERNS = [
    re.compile(r"sk-ant-[a-zA-Z0-9-]{10,}"),  # Anthropic API keys
    re.compile(r"sk-[a-zA-Z0-9]{10,}"),  # OpenAI API keys
    re.compile(r"ghp_[a-zA-Z0-9]{10,}"),  # GitHub personal access tokens
    re.compile(r"gho_[a-zA-Z0-9]{10,}"),  # GitHub OAuth tokens
    re.compile(r"AKIA[A-Z0-9]{16}"),  # AWS access keys
    re.compile(r'(?:password|passwd|pwd)\s*[=:]\s*["\']?[^\s"\']{4,}', re.IGNORECASE),
    re.compile(r'(?:token|secret|api_key)\s*[=:]\s*["\']?[^\s"\']{8,}', re.IGNORECASE),
]

# Internal paths
_PATH_PATTERNS = [
    re.compile(r"/Users/[a-zA-Z0-9_-]+/"),  # macOS home dirs
    re.compile(r"/home/[a-zA-Z0-9_-]+/"),  # Linux home dirs
    re.compile(r"C:\\Users\\[a-zA-Z0-9_-]+\\"),  # Windows paths
]

# Internal IPs
_IP_PATTERNS = [
    re.compile(r"\b(?:10|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.\d{1,3}\.\d{1,3}\b"),
]

# Temporal references that are meaningless out of context
_TEMPORAL_PATTERNS = [
    re.compile(r"\b(?:today|tomorrow|yesterday|this morning|this afternoon)\b", re.IGNORECASE),
    re.compile(r"\b(?:this week|next week|last week|this sprint|next sprint)\b", re.IGNORECASE),
    re.compile(r"\b(?:right now|at the moment|currently working on)\b", re.IGNORECASE),
]

# Delegate boilerplate patterns
_DELEGATE_BOILERPLATE = [
    re.compile(r"^Research saved as \*\*#?\d+\*\*.*$", re.MULTILINE),
    re.compile(r"^Saved as #\d+\..*$", re.MULTILINE),
    re.compile(r"^Research complete\. Saved as.*$", re.MULTILINE),
    re.compile(r"^task_id:\d+ doc_ids:[\d,]+ synthesis_id:\d+$", re.MULTILINE),
    re.compile(r"worktree.*emdx-[\w-]+", re.IGNORECASE),
    re.compile(r"git worktree (?:add|remove|list).*$", re.MULTILINE),
]

# Draft/incomplete markers
_DRAFT_MARKERS = re.compile(
    r"\b(?:TODO|FIXME|HACK|XXX|WIP|TBD|PLACEHOLDER)\b",
    re.IGNORECASE,
)


def preprocess_content(content: str) -> tuple[str, list[str]]:
    """Apply Layer 1 pre-processing filters to document content.

    Redacts sensitive data, marks temporal references, and strips
    delegate boilerplate. Zero cost — pure regex.

    Args:
        content: Raw document content.

    Returns:
        Tuple of (filtered_content, warnings) where warnings lists
        any issues found (e.g., "redacted 2 API keys").
    """
    warnings: list[str] = []
    result = content

    # 1. Redact credentials
    cred_count = 0
    for pattern in _CREDENTIAL_PATTERNS:
        matches = pattern.findall(result)
        if matches:
            cred_count += len(matches)
            result = pattern.sub("[REDACTED]", result)
    if cred_count:
        warnings.append(f"redacted {cred_count} credential(s)")

    # 2. Redact internal paths (replace with generic)
    path_count = 0
    for pattern in _PATH_PATTERNS:
        matches = pattern.findall(result)
        if matches:
            path_count += len(matches)
            result = pattern.sub("~/", result)
    if path_count:
        warnings.append(f"anonymized {path_count} path(s)")

    # 3. Redact internal IPs
    ip_count = 0
    for pattern in _IP_PATTERNS:
        matches = pattern.findall(result)
        if matches:
            ip_count += len(matches)
            result = pattern.sub("[INTERNAL_IP]", result)
    if ip_count:
        warnings.append(f"redacted {ip_count} internal IP(s)")

    # 4. Mark temporal references
    for pattern in _TEMPORAL_PATTERNS:
        result = pattern.sub(lambda m: f"[TEMPORAL: {m.group()}]", result)

    # 5. Strip delegate boilerplate
    for pattern in _DELEGATE_BOILERPLATE:
        result = pattern.sub("", result)

    # 6. Clean up multiple blank lines left by stripping
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip(), warnings


def compute_draft_score(content: str) -> float:
    """Score how "drafty" a document is (0.0 = polished, 1.0 = rough draft).

    Based on density of TODO/WIP/TBD/FIXME markers.
    """
    words = content.split()
    if not words:
        return 0.0

    marker_count = len(_DRAFT_MARKERS.findall(content))
    # Normalize: 1 marker per 100 words = 0.5, 2+ per 100 = 1.0
    density = marker_count / (len(words) / 100)
    return min(density / 2.0, 1.0)


# ── Layer 2: Synthesis prompt construction ──────────────────────────

# Audience modes control what gets preserved vs filtered
AUDIENCE_MODES = {
    "me": {
        "description": "Personal wiki — keep everything including casual remarks",
        "filter_level": "minimal",
    },
    "team": {
        "description": "Team wiki — keep factual attributions, filter casual remarks",
        "filter_level": "moderate",
    },
    "public": {
        "description": "Public docs — remove all personal references",
        "filter_level": "strict",
    },
}


def build_privacy_prompt_section(audience: str = "team") -> str:
    """Build the privacy/filtering section of the synthesis prompt.

    This gets injected into the article generation prompt to guide
    the LLM on what to preserve vs filter.

    Args:
        audience: One of "me", "team", "public".

    Returns:
        Prompt section string.
    """
    if audience == "me":
        return (
            "## Content Filtering\n"
            "Minimal filtering — this is a personal wiki.\n"
            "- Remove any [REDACTED] or [INTERNAL_IP] markers\n"
            "- Convert [TEMPORAL: X] markers to approximate dates when possible\n"
            "- Keep all personal references and casual language\n"
        )

    if audience == "public":
        return (
            "## Content Filtering — STRICT\n"
            "This content will be publicly visible.\n\n"
            "REMOVE:\n"
            "- All personal names and references to specific people\n"
            "- All [REDACTED], [INTERNAL_IP], [TEMPORAL: X] markers and "
            "surrounding context\n"
            "- Internal tool names, team-specific jargon\n"
            "- Any content that reveals internal processes or architecture\n\n"
            "PRESERVE:\n"
            "- Technical concepts and patterns\n"
            "- Code examples (with anonymized paths)\n"
            "- Architecture decisions and rationale\n"
        )

    # Default: team
    return (
        "## Content Filtering\n"
        "This wiki is for the team. Apply these rules:\n\n"
        "PRESERVE:\n"
        "- Factual attributions: 'Alex proposed using materialized views'\n"
        "- Technical decisions and their rationale\n"
        "- Code snippets, commands, and configuration examples (verbatim)\n"
        "- Specific dates when relevant to decisions or timelines\n\n"
        "FILTER OUT:\n"
        "- Casual remarks about people: 'ask Sarah, she knows SQL'\n"
        "- Conversational context: 'hey can you make this for Bob'\n"
        "- [REDACTED] markers — omit the surrounding sentence\n"
        "- [INTERNAL_IP] markers — omit or replace with 'internal server'\n"
        "- [TEMPORAL: X] markers — omit unless the actual date is known\n"
        "- Delegate execution boilerplate (task IDs, worktree paths)\n"
        "- Draft markers (TODO, FIXME, WIP) unless they represent "
        "genuine open questions\n\n"
        "ATTRIBUTION TEST: For each mention of a person, ask: "
        "'Would a reader unfamiliar with the team find this useful "
        "for understanding WHY a decision was made?' If yes, keep it. "
        "If no, remove it.\n"
    )


# ── Layer 3: Post-processing validation ─────────────────────────────


def postprocess_validate(content: str) -> tuple[str, list[str]]:
    """Validate LLM-generated wiki content for leaked sensitive data.

    Scans the generated output for any credentials, IPs, or other
    sensitive content that survived the synthesis.

    Args:
        content: Generated wiki article content.

    Returns:
        Tuple of (cleaned_content, warnings) where warnings lists
        any issues found and fixed.
    """
    warnings: list[str] = []
    result = content

    # Re-check for credentials (LLM might have reconstructed them)
    for pattern in _CREDENTIAL_PATTERNS:
        if pattern.search(result):
            result = pattern.sub("[REDACTED]", result)
            warnings.append("post-scan: credential found in generated output")

    # Re-check for internal IPs
    for pattern in _IP_PATTERNS:
        if pattern.search(result):
            result = pattern.sub("[INTERNAL_IP]", result)
            warnings.append("post-scan: internal IP found in generated output")

    # Check for unfixed markers
    remaining_redacted = len(re.findall(r"\[REDACTED\]", result))
    if remaining_redacted:
        warnings.append(f"post-scan: {remaining_redacted} [REDACTED] marker(s) remain")

    remaining_temporal = len(re.findall(r"\[TEMPORAL:", result))
    if remaining_temporal:
        # Clean up temporal markers the LLM didn't handle
        result = re.sub(r"\[TEMPORAL:\s*([^\]]+)\]", r"\1", result)
        warnings.append(f"post-scan: cleaned {remaining_temporal} [TEMPORAL] marker(s)")

    return result, warnings
