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


def line(asked, english, language=None):
    """The LANGUAGE line. `language` is the reading's ("english", "roman_urdu", "urdu", "other"); for English it says
    to answer in English. Without a reading, '' for a question that is its own restatement, else the line asking for
    the language the person wrote in."""
    asked, english = (asked or '').strip(), (english or '').strip()
    if not asked:
        return ''
    if language not in LANGUAGES:
        if not english or asked.lower() == english.lower():
            return ''
        return (f'LANGUAGE: the person asked, in their own words: "{asked[:600]}". Write the whole answer in that same '
                f'language and script: {_ROMAN_URDU} English if they wrote English. Names, numbers, amounts, dates and '
                'document titles stay as they are.\n\n')
    if language == 'english':
        # Said, not left out: with no line, an English question after a Roman Urdu answer was answered in Roman Urdu
        # too, the model carrying on in the conversation's language (Operations' clean run, 28 Oct 2026).
        return ('LANGUAGE: this question is in English. Write the whole answer in English, whatever language earlier '
                'messages in the conversation used.\n\n')
    return (f'LANGUAGE: the person asked, in their own words: "{asked[:600]}". Write the whole answer in '
            f'{_SCRIPT[language]} Names, numbers, amounts, dates and document titles stay as they are.\n\n')
