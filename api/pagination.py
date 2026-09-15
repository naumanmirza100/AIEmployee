from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'limit'
    max_page_size = 100


def paginate(request, items, *, default_limit, max_limit):
    """Bound a list endpoint without changing its response shape (PERF-2).

    `DEFAULT_PAGINATION_CLASS` only engages for generic DRF views. The PM list
    endpoints are `@api_view` functions returning hand-built Responses, so
    pagination never applied and they returned every row — unbounded payload and
    latency that grows with the tenant.

    Callers keep their existing `data` exactly as it was and add the returned
    `meta` under a sibling `pagination` key, so current frontend code keeps
    working untouched while new code can page with `?limit=&offset=`.

    Defaults are deliberately generous. A silent cap is a regression — the
    company dashboard, for one, searches its project list client-side, so a
    project past the cap would simply vanish from search. So `default_limit` is
    set above realistic current data, `max_limit` bounds growth, and
    `has_more` / `total` make any truncation detectable rather than silent.

    `items` may be a QuerySet (sliced in the database) or a list.
    Returns (page_items, meta).
    """
    params = getattr(request, 'query_params', None) or request.GET

    def _int(name, fallback, lo):
        try:
            return max(lo, int(params.get(name, fallback)))
        except (TypeError, ValueError):
            return fallback

    limit = min(_int('limit', default_limit, 1), max_limit)
    offset = _int('offset', 0, 0)

    total = items.count() if hasattr(items, 'count') and not isinstance(items, list) else len(items)
    page = items[offset:offset + limit]
    if not isinstance(page, list):
        page = list(page)

    return page, {
        'limit': limit,
        'offset': offset,
        'total': total,
        'returned': len(page),
        'has_more': offset + len(page) < total,
    }
