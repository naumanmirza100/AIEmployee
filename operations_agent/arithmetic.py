"""Sums the AI writes out, checked and corrected here (24 Nov 2026, the test report's Operations 1, decision D14).

"What was our total revenue across July, August and September 2026?" was answered PKR 129,500,000 on all three tries,
with the three months listed right beside it (41,300,000 + 43,050,000 + 44,800,000), which add up to 129,150,000. The
figures were right; the adding was the AI's. Q&A and Authoring now show the working as "A + B + C = total" (or
"(A + B) / 2 = average"), and every such line is worked out again here: a wrong result is replaced, wherever it is
written in the answer.
"""
import re
from decimal import Decimal, InvalidOperation

# A figure as written: 41,300,000 / 2,352.00 / 12.5, optionally with a currency or unit just before it
# (PKR, USD, Rs., $) and a % after it.
_NUM = r'(?:[A-Z]{3}\s?|Rs\.?\s?|[$€£]\s?)?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|(?:[A-Z]{3}\s?|Rs\.?\s?|[$€£]\s?)?\d+(?:\.\d+)?%?'
_SUM = re.compile(
    r'(?P<open>\(\s*)?(?P<terms>(?:\*\*)?(?:' + _NUM + r')(?:\*\*)?(?:\s*\+\s*(?:\*\*)?(?:' + _NUM + r')(?:\*\*)?)+)'
    r'(?(open)\s*\)\s*/\s*(?P<count>\d+))\s*(?:=|is|equals)\s*(?:\*\*)?(?P<result>' + _NUM + r')(?:\*\*)?')

RULE = ("When the answer adds up, averages or compares figures, show the working once, on its own line, as "
        "\"A + B + C = total\" (or \"(A + B + C) / 3 = average\"), each figure as the documents write it, before "
        "giving the result.")


def _value(text):
    digits = re.sub(r'[^\d.]', '', text)
    try:
        return Decimal(digits)
    except InvalidOperation:
        return None


def _written_like(value, example):
    """`value` written the way `example` is: its currency, thousands commas, decimals and %."""
    prefix = re.match(r'^(?:[A-Z]{3}\s?|Rs\.?\s?|[$€£]\s?)?', example).group(0)
    number = example[len(prefix):].rstrip('%')
    places = len(number.split('.', 1)[1]) if '.' in number else 0
    text = f'{value:,.{places}f}' if ',' in number or value >= 10_000 else f'{value:.{places}f}'
    return prefix + text + ('%' if example.endswith('%') else '')


def check_sums(text):
    """(text, fixes): every written-out sum or average in `text` worked out again; a wrong result is replaced
    everywhere it is written. `fixes` lists (wrong, right) pairs."""
    if not text:
        return text, []
    fixes = []
    for match in _SUM.finditer(text):
        terms = [_value(t) for t in re.findall(_NUM, re.sub(r'\*\*', '', match.group('terms')))]
        stated = _value(match.group('result'))
        if None in terms or stated is None or len(terms) < 2:
            continue
        right = sum(terms)
        if match.group('count'):
            count = int(match.group('count'))
            if not count:
                continue
            right = right / count
        places = len(match.group('result').rstrip('%').split('.', 1)[1]) if '.' in match.group('result') else 0
        right = right.quantize(Decimal(1).scaleb(-places)) if places else right.quantize(Decimal(1))
        if abs(right - stated) <= Decimal(1).scaleb(-places) / 2:
            continue
        wrong_text = match.group('result')
        fixes.append((wrong_text, _written_like(right, wrong_text)))
    def bare(figure):
        return re.sub(r'^(?:[A-Z]{3}\s?|Rs\.?\s?|[$€£]\s?)', '', figure)
    for wrong_text, right_text in fixes:
        text = re.sub(r'(?<![\d,.])' + re.escape(bare(wrong_text)) + r'(?![\d,]|\.\d)', bare(right_text), text)
    return text, fixes
