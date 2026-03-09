"""vCard (.vcf) parser for importing Apple Contacts.

Apple Contacts exports as vCard 3.0. This parser handles the common fields
without requiring any external dependencies.

To export from Apple Contacts:
  1. Open Contacts app on macOS
  2. Select All (Cmd+A)
  3. File > Export > Export vCard...
  4. Save the .vcf file
"""

import re
from typing import List

from models import Contact


def _unfold_lines(raw: str) -> str:
    """vCard spec: long lines are folded with CRLF + whitespace. Unfold them."""
    return re.sub(r'\r?\n[ \t]', '', raw)


def _decode_value(value: str) -> str:
    """Handle common vCard encoding quirks."""
    # Unescape backslash-escaped characters
    value = value.replace('\\n', ' ').replace('\\,', ',').replace('\\;', ';')
    return value.strip()


def _extract_field(lines: List[str], prefix: str) -> str:
    """Extract first matching field value from vCard lines.
    Handles parameters like TEL;type=CELL:+1234567890
    """
    for line in lines:
        upper = line.upper()
        if upper.startswith(prefix.upper()):
            # Find the colon that separates field name/params from value
            colon_idx = line.index(':')
            return _decode_value(line[colon_idx + 1:])
    return ""


def _extract_name(lines: List[str]) -> str:
    """Extract a display name. Prefer FN (formatted name), fall back to N."""
    fn = _extract_field(lines, "FN")
    if fn:
        return fn

    # N field format: Last;First;Middle;Prefix;Suffix
    n = _extract_field(lines, "N")
    if n:
        parts = n.split(';')
        last = parts[0] if len(parts) > 0 else ""
        first = parts[1] if len(parts) > 1 else ""
        name = f"{first} {last}".strip()
        if name:
            return name

    return ""


def parse_vcf(file_path: str) -> List[Contact]:
    """Parse a .vcf file and return a list of Contacts.

    Handles multi-contact .vcf files (Apple exports all contacts into one file).
    Skips entries that have no usable name, phone, or email.
    """
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        raw = f.read()

    raw = _unfold_lines(raw)

    contacts = []
    # Split into individual vCard blocks
    blocks = re.split(r'(?i)BEGIN:VCARD', raw)

    for block in blocks:
        if not block.strip():
            continue

        lines = [l.strip() for l in block.split('\n') if l.strip()]

        name = _extract_name(lines)
        phone = _extract_field(lines, "TEL")
        email = _extract_field(lines, "EMAIL")
        org = _extract_field(lines, "ORG")

        # Skip contacts with no useful identifying info
        if not name and not phone and not email:
            continue

        # Clean up org (vCard uses semicolons as separators)
        if org:
            org = org.rstrip(';').strip()

        contacts.append(Contact(
            name=name,
            phone=phone,
            email=email,
            organization=org,
        ))

    return contacts
