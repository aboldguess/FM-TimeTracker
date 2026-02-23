"""Input normalization helpers for authentication-related text fields.

This module centralizes conservative, explicit cleanup steps for user-provided
login identifiers before schema validation. The goal is to reduce false
validation failures caused by invisible or compatibility Unicode characters
while avoiding broad transformations that could change user intent.
"""

from __future__ import annotations

import unicodedata

# Explicit invisible code points commonly copied from password managers,
# messaging apps, and rich text editors. These are not meaningful in email
# addresses and can be abused for visual spoofing or to bypass exact matching.
_ZERO_WIDTH_CHARS = {
    "\u200b",  # ZERO WIDTH SPACE
    "\u200c",  # ZERO WIDTH NON-JOINER
    "\u200d",  # ZERO WIDTH JOINER
    "\u2060",  # WORD JOINER
    "\ufeff",  # ZERO WIDTH NO-BREAK SPACE / BOM
}


def normalize_login_email_input(raw_email: str | None) -> str | None:
    """Normalize login email input before validation.

    Steps are intentionally narrow and documented for security reviewability:
    1) Trim leading/trailing whitespace to avoid accidental form-entry noise.
    2) Apply NFKC normalization so compatibility forms (for example full-width
       ASCII lookalikes) are normalized to canonical equivalents.
    3) Remove invisible/control code points that are not valid email content
       and can cause spoofing, parser discrepancies, or hard-to-debug failures.
    """
    if raw_email is None:
        return None

    # Strip boundary whitespace first so validators don't reject valid addresses
    # that were pasted with surrounding spaces.
    cleaned = raw_email.strip()

    # Normalize Unicode compatibility variants to reduce confusable and
    # representation-mismatch issues before we inspect code points.
    cleaned = unicodedata.normalize("NFKC", cleaned)

    sanitized_chars: list[str] = []
    for char in cleaned:
        category = unicodedata.category(char)

        # Drop explicit zero-width characters and all Unicode control/format
        # characters (Cc/Cf), which are not valid email content and can be used
        # for hidden-text attacks or validation bypass tricks.
        if char in _ZERO_WIDTH_CHARS or category in {"Cc", "Cf"}:
            continue

        sanitized_chars.append(char)

    return "".join(sanitized_chars)
