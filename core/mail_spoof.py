"""Signs that an incoming email is not what it shows (21 Nov 2026, the test report's Reply Draft 1 and CRM Sync 1).

An email from `"billing@bank.com" <attacker@evil.example>` asking to "update the bank details for your next payment"
was listed as from billing@bank.com, answered with an AI draft that agreed to the change (the reply going to the
attacker), and put into the CRM as a contact named "billing@bank.com". A change of bank or payment details asked for
by email is the most common invoice fraud. Read from what is stored, no AI call.
"""
import re

_ADDRESS = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
_PAYMENT_THING = re.compile(r'\b(bank|banking|payment|account|iban|swift|beneficiary|remittance|wire)\s+'
                            r'(details?|information|info|number|instructions?)\b', re.I)
_CHANGE = re.compile(r'\b(change[ds]?|changing|update[ds]?|updating|new|different|replace[ds]?)\b', re.I)


def disguised_as(from_name, from_email) -> str:
    """The address a display name shows when it is not the real sender's ('billing@bank.com'), else ''."""
    found = _ADDRESS.search(from_name or '')
    if found and found.group(0).lower() != (from_email or '').strip().lower():
        return found.group(0)
    return ''


def looks_like_an_address(name) -> bool:
    return bool(_ADDRESS.search(name or ''))


def asks_to_change_payment_details(subject, body='') -> bool:
    """Whether the email asks to change bank or payment details (subject and the start of the body)."""
    text = f'{subject or ""}\n{(body or "")[:4000]}'
    return bool(_PAYMENT_THING.search(text) and _CHANGE.search(text))


def warning(from_name, from_email, subject, body='') -> str:
    """One sentence for the screen, or ''."""
    parts = []
    shown = disguised_as(from_name, from_email)
    if shown:
        parts.append(f'The name shown is the address {shown}, but this came from {from_email}.')
    if asks_to_change_payment_details(subject, body):
        parts.append('It asks to change bank or payment details: check with someone you know by phone before '
                     'changing anything.')
    return ' '.join(parts)
