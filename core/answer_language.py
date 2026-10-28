"""The line that asks for an answer in the asker's own language, put first in the answer prompt.

The AI readings (core/HR_agent/intent.py, operations_agent/intent.py, …) restate each question in English, and the
documents are searched with that. The answer prompt then held mostly English text, and a question asked in Roman Urdu
was answered in English: HR's "ghar se kaam kitne din kar sakte hain?" on 28 Oct 2026, Recruitment's the same day
(fixed there in recruitment_qa_agent._answer_prompt). A language line at the end of a prompt was ignored; first, it
holds.
"""


def line(asked, english):
    """'' when the question was asked in English (the restatement is the question itself), else the LANGUAGE line."""
    asked, english = (asked or '').strip(), (english or '').strip()
    if not asked or not english or asked.lower() == english.lower():
        return ''
    return (f'LANGUAGE: the person asked, in their own words: "{asked[:600]}". Write the whole answer in that same '
            'language and script: Roman Urdu (Urdu in Latin letters) if that is how they wrote, English if English. '
            'In Roman Urdu the headings, the labels and every sentence are Roman Urdu, in this style (the <...> are '
            'filled from the documents): "<subject> ke mutabiq <fact>. Tafseel: <details>." Names, numbers, amounts, '
            'dates and document titles stay as they are.\n\n')
