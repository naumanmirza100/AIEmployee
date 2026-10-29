"""Tracked links in Marketing emails.

A link is wrapped as /token?t=<token>&url=<destination>&s=<signature>. The click address used to redirect anyone to
any website, even with a made-up token (CO-125), and a destination with more than one parameter lost everything after
its first '&' because the '&' was left unencoded (CO-124). Now the whole destination is encoded, and it is signed
together with the email's token, so a click is sent on only to the address that was in that email.
"""
from urllib.parse import quote

from django.conf import settings
from django.utils.crypto import constant_time_compare, salted_hmac

SALT = 'marketing.click-link'


def signature(token, destination):
    return salted_hmac(SALT, f'{token}\n{destination}').hexdigest()[:32]


def wrap(base_url, token, destination):
    """The tracked address for one link of one email."""
    return (f"{base_url}/token?t={token}&url={quote(destination, safe='')}"
            f"&s={signature(token, destination)}")


def site_url(path):
    base = (getattr(settings, 'SITE_URL', '') or '').rstrip('/')
    return f"{base}{path if path.startswith('/') else '/' + path}"


def destination(request, send_history):
    """Where a click on a real email's link goes, or None when the link was not one the email carried.

    `url` arrives decoded once, as it was signed. A link from an email sent before signing has no `s`: it is still
    followed, since its token is real (the email went out), as the report advised for the change-over.
    """
    url = request.GET.get('url', '')
    sig = request.GET.get('s')
    if sig is not None and not constant_time_compare(sig, signature(send_history.tracking_token, url)):
        return None
    if not url or url.startswith('#'):
        return site_url(f'/marketing/campaigns/{send_history.campaign_id}/' if send_history.campaign_id else '/marketing/')
    if url.startswith(('http://', 'https://')):
        return url
    if url.startswith('/') and not url.startswith('//'):
        return site_url(url)
    return None
