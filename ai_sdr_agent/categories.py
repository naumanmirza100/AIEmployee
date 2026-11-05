"""Which industry category (SDRLeadCategory) a new lead is filed under.

Nothing here is a fixed list: a category is made the first time an industry turns up in the data.

- A search (Apollo/Apify) files a lead under the industry that was searched for: the ICP's industries. With
  several, the one the lead's company matches; with none matching, the industry the provider reports.
- Leads with no search behind them (an import, a hand-added lead, Apify runs fetched as they are) are filed under
  their own industry: the CSV's Industry column, the form's Industry field, the provider's company industry.
- A category picked by hand in the screens wins over all of this (the views pass it in).
"""
from django.db import IntegrityError

MAX_NAME = 100


def clean_name(value) -> str:
    """One space between words, cut to the column's length."""
    return ' '.join(str(value or '').split())[:MAX_NAME]


def get_or_create_category(company_user, name, cache=None):
    """The user's category of that name (case-insensitive), made on first use. None for a blank name.

    ``cache`` (a dict) saves a query per lead when a batch files many leads under few categories.
    """
    from ai_sdr_agent.models import SDRLeadCategory

    name = clean_name(name)
    if not name:
        return None
    key = name.lower()
    if cache is not None and key in cache:
        return cache[key]
    cat = SDRLeadCategory.objects.filter(company_user=company_user, name__iexact=name).first()
    if cat is None:
        try:
            cat = SDRLeadCategory.objects.create(company_user=company_user, name=name)
        except IntegrityError:   # made by another request at the same moment
            cat = SDRLeadCategory.objects.get(company_user=company_user, name__iexact=name)
    if cache is not None:
        cache[key] = cat
    return cat


def industry_for_lead(searched_industries, lead_industry) -> str:
    """The industry name a lead is filed under (see the module docstring). '' when there is none."""
    searched = [clean_name(i) for i in (searched_industries or []) if clean_name(i)]
    own = clean_name(lead_industry)
    if len(searched) == 1:
        return searched[0]
    if searched and own:
        own_l = own.lower()
        for ind in searched:
            ind_l = ind.lower()
            if ind_l in own_l or own_l in ind_l:
                return ind
    return own or (searched[0] if searched else '')


def category_for_lead(company_user, searched_industries, lead_industry, cache=None):
    """The SDRLeadCategory for a new lead, or None when neither the search nor the lead names an industry."""
    return get_or_create_category(company_user, industry_for_lead(searched_industries, lead_industry), cache)
