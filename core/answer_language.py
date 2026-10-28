"""The line that asks for an answer in the asker's own language, put first in the answer prompt.

The AI readings (core/HR_agent/intent.py, operations_agent/intent.py, recruitment_agent/intent.py) restate each
question in English, and the documents are searched with that. The answer prompt then held mostly English text, and a
question asked in Roman Urdu was answered in English: HR's "ghar se kaam kitne din kar sakte hain?" on 28 Oct 2026,
Recruitment's the same day. A language line at the end of a prompt was ignored; first, it holds.

The reading says which language the message is in. Without that, the line was added whenever the restatement differed
from the words typed, which is every follow-up: an English follow-up after a Roman Urdu question was answered in Roman
Urdu (Operations' live run and the Recruitment film, 28 Oct 2026).
"""

LANGUAGES = ('english', 'roman_urdu', 'urdu', 'other')

_ROMAN_URDU = ('Roman Urdu (Urdu in Latin letters). The headings, the labels and every sentence are Roman Urdu, in this '
               'style (the <...> are filled from the records): "<subject> ke mutabiq <fact>. Tafseel: <details>."')
_SCRIPT = {
    'roman_urdu': _ROMAN_URDU,
    'urdu': 'Urdu, in Urdu script, headings and labels too.',
    'other': 'that same language and script.',
}


def normalize(value):
    """The reading's language as one of LANGUAGES, whatever its spelling ("English", "Roman Urdu", "en", "Hinglish");
    None when it gave none. On the live site the reading's "English" did not match "english", and the fallback line
    turned every English question into a Roman Urdu answer (28 Oct 2026)."""
    text = str(value or '').strip().lower().replace('-', ' ').replace('_', ' ')
    if not text or text in ('null', 'none', 'unknown'):
        return None
    if 'roman' in text or 'hinglish' in text or 'latin' in text:
        return 'roman_urdu'
    if 'urdu' in text or text == 'ur':
        return 'urdu'
    if text in ('english', 'en', 'eng'):
        return 'english'
    return 'other'


def _same_words(asked, english, share=0.8):
    """True when nearly every word of the question, in Latin letters, is in the English restatement: the question was
    English. A Roman Urdu question shares its English nouns with the restatement ("FinEdge contract mein critical
    problem ka response time kitna hai?" shares 6 words of 9), not its own words."""
    import re
    if any(ord(ch) > 127 for ch in asked):
        return False
    words = re.findall(r'[a-z]{3,}', asked.lower())
    if len(words) < 3:
        return False
    restated = set(re.findall(r'[a-z]{3,}', (english or '').lower()))
    return sum(w in restated for w in words) / len(words) >= share


def settle(asked, english, language):
    """The language to answer in: the reading's, put right where the text itself shows it. Urdu letters in the
    question are Urdu script (on the live site "دفتر کے نئے اوقات کیا ہیں؟" was read as Roman Urdu and answered so),
    and a question its English restatement keeps word for word is English."""
    language = normalize(language)
    if any('؀' <= ch <= 'ۿ' for ch in asked or ''):
        return 'urdu'
    if language in (None, 'roman_urdu', 'other') and _same_words(asked or '', english):
        return 'english'
    return language


def line(asked, english, language=None):
    """The LANGUAGE line. `language` is the reading's ("english", "roman_urdu", "urdu", "other"); for English it says
    to answer in English. Without a reading, '' for a question that is its own restatement, else the line asking for
    the language the person wrote in."""
    asked, english = (asked or '').strip(), (english or '').strip()
    if not asked:
        return ''
    language = settle(asked, english, language)
    if language is None:
        if not english or asked.lower() == english.lower():
            return ''
        # No example of any language here: the Roman Urdu one, first, made English questions come back in Roman Urdu.
        return (f'LANGUAGE: the person asked, in their own words: "{asked[:600]}". Write the whole answer in the '
                'language and script of those words. Names, numbers, amounts, dates and document titles stay as they '
                'are.\n\n')
    if language == 'english':
        # Said, not left out: with no line, an English question after a Roman Urdu answer was answered in Roman Urdu
        # too, the model carrying on in the conversation's language (Operations' clean run, 28 Oct 2026).
        return ('LANGUAGE: this question is in English. Write the whole answer in English, whatever language earlier '
                'messages in the conversation used.\n\n')
    return (f'LANGUAGE: the person asked, in their own words: "{asked[:600]}". Write the whole answer in '
            f'{_SCRIPT[language]} Names, numbers, amounts, dates and document titles stay as they are.\n\n')
