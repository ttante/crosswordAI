"""Baseline AI safety and rights checks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PolicyFinding:
    code: str
    severity: str
    message: str


@dataclass(frozen=True, slots=True)
class PolicyResult:
    status: str
    findings: list[PolicyFinding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "passed"


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    blocked_codes: frozenset[str] = frozenset(
        {
            "prompt_injection",
            "long_quote",
            "lyrics_like_excerpt",
            "script_like_excerpt",
            "long_prose_excerpt",
            "secret_like_value",
        }
    )
    warn_codes: frozenset[str] = frozenset({"email"})

    @classmethod
    def from_registry_payload(cls, payload: dict[str, object]) -> "PolicyConfig":
        return cls(
            blocked_codes=frozenset(str(code) for code in payload.get("blocks", [])),
            warn_codes=frozenset(str(code) for code in payload.get("warns", [])),
        )


class BaselineSafetyScanner:
    """Deterministic first-pass checks before any model sees content."""

    def __init__(self, policy_config: PolicyConfig | None = None) -> None:
        self.policy_config = policy_config or PolicyConfig()

    def scan(self, text: str) -> PolicyResult:
        findings: list[PolicyFinding] = []
        if _looks_like_prompt_injection(text):
            findings.append(
                PolicyFinding(
                    "prompt_injection",
                    "high",
                    "Source text appears to contain instructions aimed at the model.",
                )
            )
        if _LONG_QUOTE_RE.search(text):
            findings.append(
                PolicyFinding(
                    "long_quote",
                    "high",
                    "Source text contains a long quoted passage that should not be stored as evidence.",
                )
            )
        if _looks_like_lyrics(text):
            findings.append(
                PolicyFinding(
                    "lyrics_like_excerpt",
                    "high",
                    "Source text resembles a multi-line lyric excerpt.",
                )
            )
        if _looks_like_script(text):
            findings.append(
                PolicyFinding(
                    "script_like_excerpt",
                    "high",
                    "Source text resembles a script/dialogue excerpt.",
                )
            )
        if _looks_like_long_prose_excerpt(text):
            findings.append(
                PolicyFinding(
                    "long_prose_excerpt",
                    "high",
                    "Source text resembles a long copyrighted prose excerpt.",
                )
            )
        if _SECRET_RE.search(text):
            findings.append(
                PolicyFinding("secret_like_value", "high", "Source text contains a secret-like token.")
            )
        if _EMAIL_RE.search(text):
            findings.append(PolicyFinding("email", "medium", "Source text contains an email address."))

        status = "quarantined" if any(f.code in self.policy_config.blocked_codes for f in findings) else "passed"
        return PolicyResult(status, findings)


def _looks_like_prompt_injection(text: str) -> bool:
    lowered = text.lower()
    needles = [
        "ignore previous instructions",
        "system prompt",
        "developer message",
        "you are now",
        "disregard the above",
        "reveal your instructions",
    ]
    return any(needle in lowered for needle in needles)


_LONG_QUOTE_RE = re.compile(r'"[^"]{280,}"')
_SECRET_RE = re.compile(r"(sk-[A-Za-z0-9_-]{20,}|api[_-]?key\s*[:=]\s*[A-Za-z0-9_-]{16,})", re.I)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def _looks_like_lyrics(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 8:
        return False
    short_lines = [line for line in lines if len(line) <= 80]
    has_marker = any(line.lower().strip("[]:") in {"verse", "chorus", "bridge", "hook"} for line in lines)
    return len(short_lines) / len(lines) >= 0.8 and (has_marker or len(lines) >= 12)


def _looks_like_script(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    speaker_lines = [line for line in lines if re.match(r"^[A-Z][A-Z0-9 _-]{1,30}:\s+.+", line)]
    return len(speaker_lines) >= 4


def _looks_like_long_prose_excerpt(text: str) -> bool:
    if len(text) < 1800:
        return False
    paragraph_count = len([part for part in text.split("\n\n") if len(part.strip()) > 250])
    chapter_marker = bool(re.search(r"\bchapter\s+(?:[0-9ivxlcdm]+|one|two|three|four|five)\b", text, re.I))
    return paragraph_count >= 3 or chapter_marker
