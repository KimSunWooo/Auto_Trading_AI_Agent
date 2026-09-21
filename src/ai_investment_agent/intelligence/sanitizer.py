from __future__ import annotations

import re

from ai_investment_agent.domain.event_intelligence import ParsedDocument, SanitizedDocument
from ai_investment_agent.intelligence.text import normalize_whitespace

# Patterns that treat document text as an instruction to the model.
_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "INSTRUCTION_OVERRIDE",
        re.compile(
            r"ignore\s+(all\s+)?(previous|prior|above|your)\s+(instructions|rules|guidelines|policy)",
            re.IGNORECASE,
        ),
    ),
    (
        "INSTRUCTION_OVERRIDE",
        re.compile(r"disregard\s+(your|all)\s+(rules|guidelines|instructions|policy)", re.IGNORECASE),
    ),
    (
        "INSTRUCTION_OVERRIDE",
        re.compile(r"이전\s*(지시|명령|프롬프트).{0,16}무시", re.IGNORECASE),
    ),
    ("ROLE_HIJACK", re.compile(r"^\s*system\s*:", re.IGNORECASE | re.MULTILINE)),
    ("ROLE_HIJACK", re.compile(r"<\|im_start\|>", re.IGNORECASE)),
    ("ROLE_HIJACK", re.compile(r"\[/?INST\]", re.IGNORECASE)),
    ("ROLE_HIJACK", re.compile(r"you\s+are\s+now\s+(a|an|the)\b", re.IGNORECASE)),
    (
        "FORCED_LABEL",
        re.compile(r"classify\s+(this\s+)?as\s+(positive|negative|buy|sell)", re.IGNORECASE),
    ),
    (
        "FORCED_LABEL",
        re.compile(r"(긍정|부정)\s*(으로|로)\s*분류", re.IGNORECASE),
    ),
    (
        "TRADE_COMMAND",
        re.compile(r"\b(buy|sell)\s+now\b", re.IGNORECASE),
    ),
    (
        "TRADE_COMMAND",
        re.compile(r"recommend\s+(a\s+)?(strong\s+)?(buy|sell)", re.IGNORECASE),
    ),
    (
        "TRADE_COMMAND",
        re.compile(r"(무조건|지금\s*당장|즉시)\s*(매수|매도)\s*(하라|해라)?", re.IGNORECASE),
    ),
    (
        "TRADE_COMMAND",
        re.compile(r"(매수|매도)\s*하라", re.IGNORECASE),
    ),
    ("OUTPUT_HIJACK", re.compile(r"output\s+only\b", re.IGNORECASE)),
)


class EventSanitizer:
    """Strips instruction-like spans. Remaining text is still untrusted data."""

    def sanitize(self, parsed: ParsedDocument) -> SanitizedDocument:
        title, title_flags, title_spans = _scrub(parsed.title)
        text, text_flags, text_spans = _scrub(parsed.text)
        return SanitizedDocument(
            raw_id=parsed.raw_id,
            title=normalize_whitespace(title),
            text=normalize_whitespace(text),
            language=parsed.language,
            injection_flags=list(dict.fromkeys(title_flags + text_flags)),
            stripped_spans=title_spans + text_spans,
            is_untrusted=True,
        )


def _scrub(text: str) -> tuple[str, list[str], list[str]]:
    flags: list[str] = []
    spans: list[str] = []
    output = text or ""
    for flag, pattern in _RULES:
        def _replace(match: re.Match[str], *, current_flag: str = flag) -> str:
            flags.append(current_flag)
            spans.append(match.group(0))
            return " "
        output = pattern.sub(_replace, output)
    return output, flags, spans
