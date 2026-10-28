"""One way to say a candidate's years of experience wherever it is shown (the summary, the qualification analysis,
the candidate page): to the nearest half year. The same CV showed as 5.75, ~5.8, "5-8" and, in the AI's own summary,
"approximately 3 years"."""
import math


def nearest_half(years):
    # Halves round up, as on the page (JavaScript's Math.round): Python's round() takes 10.5 to 10.
    return math.floor(float(years) * 2 + 0.5) / 2


def about_years(years) -> str:
    """'about 5 years', 'about 5.5 years', 'about 8 months'; '' when unknown."""
    if years is None:
        return ''
    half = nearest_half(years)
    if half < 1:
        months = max(1, round(float(years) * 12))
        return f"about {months} month{'s' if months != 1 else ''}"
    number = int(half) if half == int(half) else half
    return f"about {number} year{'' if half == 1 else 's'}"
