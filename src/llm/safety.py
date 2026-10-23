"""Clinical safety, prompt-injection defense, and disclaimer enforcement."""

from __future__ import annotations

import re
from typing import Tuple

from .schemas import DEFAULT_CLINICAL_DISCLAIMER

# Suspicious instruction-override phrases in user queries
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous\s+)?([a-z0-9_-]+\s+)?(instructions|rules|prompts|guidelines|directives)",
    r"disregard\s+(all\s+)?(previous\s+)?([a-z0-9_-]+\s+)?(instructions|rules|prompts|guidelines)",
    r"forget\s+(all\s+)?(previous\s+)?([a-z0-9_-]+\s+)?(instructions|rules|context)",
    r"system\s*:\s*override",
    r"bypass\s+(icmr|guidelines|safety|rules)",
    r"act\s+as\s+(an?\s+)?unrestricted",
    r"you\s+are\s+now\s+(a\s+)?doctor\s+who\s+can\s+prescribe",
    r"recommend\s+(an?\s+)?(experimental|unapproved|alternative)\s+(drug|medication|treatment|dose)",
    r"jailbreak",
    r"pretend\s+you\s+are\s+not\s+bound",
]

# Personal prescription requests
_PERSONAL_PRESCRIBE_PATTERNS = [
    r"what\s+should\s+i\s+(take|prescribe\s+myself|inject)",
    r"tell\s+me\s+what\s+pills\s+i\s+need",
    r"diagnose\s+my\s+symptoms",
    r"am\s+i\s+having\s+a\s+heart\s+attack",
]


class SafetyGuard:
    """Enforces clinical safety constraints and detects adversarial input."""

    @staticmethod
    def inspect_query_for_injection(query: str) -> Tuple[bool, str]:
        """Check whether the user query contains prompt injection or override attacks.

        Returns (is_adversarial, explanation).
        """
        lower_q = query.lower()
        for pattern in _INJECTION_PATTERNS:
            if re.search(pattern, lower_q):
                return True, "Adversarial prompt injection pattern detected in clinical query."
        return False, ""

    @staticmethod
    def sanitize_evidence_text(text: str) -> str:
        """Sanitize text inside retrieved evidence to neutralize instruction injection."""
        # Replace explicit instruction markers if any document text mimics AI prompts
        sanitized = re.sub(r"(?i)\b(system|assistant|user)\s*:", r"[\1]:", text)
        return sanitized

    @staticmethod
    def format_safe_advisory(answer: str, is_personal_query: bool = False) -> str:
        """Append clinical safety advisory to answer text if needed."""
        clean_ans = answer.strip()
        if is_personal_query:
            advice = (
                "\n\n[CLINICAL ADVISORY]: If you or someone you know is experiencing acute symptoms "
                "(such as persistent chest pain, breathlessness, or syncope), please contact emergency "
                "medical services or proceed to the nearest hospital immediately."
            )
            return clean_ans + advice
        return clean_ans
