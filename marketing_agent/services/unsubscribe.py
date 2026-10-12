"""The unsubscribe link in every Marketing campaign email.

Marketing emails carried no unsubscribe link and no List-Unsubscribe header. The
only way out was to reply and have the reply read as an unsubscribe, which needs
the mailbox's inbox sync to be working. AI SDR and Frontline each had a link;
Marketing had none.

The link is signed and names the company and the address, nothing else, so it
keeps working whatever happens to the campaign or the lead afterwards. Opening
it shows a page with a button; only pressing the button (a POST) unsubscribes,
because mail scanners open links. Mail programs' one-click unsubscribe sends that
same POST. The address goes on the company's do-not-email list
(core/do_not_email.py), which every Marketing and AI SDR send asks first.
"""
import logging

from django.conf import settings
from django.core import signing

from core import do_not_email
from marketing_agent.services.do_not_email import company_id_for_campaign

logger = logging.getLogger(__name__)

_SALT = 'marketing-unsubscribe'
#: What every unsubscribe address contains. The link rewriting leaves these alone.
PATH = '/api/marketing/unsubscribe/'


def _server() -> str:
    """Where this server is reached from outside: the page is served by the API itself."""
    return (getattr(settings, 'SITE_URL', '') or getattr(settings, 'BACKEND_URL', '') or '').rstrip('/')


def make_token(company_id, email) -> str:
    return signing.dumps({'c': company_id, 'm': (email or '').strip()}, salt=_SALT)


def read_token(token):
    """(company id, address) for a link of ours, else None."""
    try:
        claims = signing.loads(token, salt=_SALT)
        company_id, email = claims['c'], (claims['m'] or '').strip()
    except (signing.BadSignature, KeyError, TypeError, AttributeError):
        return None
    return (company_id, email) if company_id and email else None


def url_for(campaign, email) -> str:
    """The link for one recipient of one campaign, or '' when none can be made.

    None can be made when the campaign's company cannot be told (there is then
    no list to put the address on) or when the server does not know its own
    address."""
    email = (email or '').strip()
    company_id = company_id_for_campaign(campaign)
    server = _server()
    if not (email and company_id and server):
        if email and company_id:
            logger.warning('No unsubscribe link added: SITE_URL / BACKEND_URL is not set.')
        return ''
    return f'{server}{PATH}{make_token(company_id, email)}/'


def html_footer(url) -> str:
    return (
        '<p style="font-size:11px;color:#888;margin:16px 0 0 0;">'
        "Don't want these emails? "
        f'<a href="{url}" style="color:#888;text-decoration:underline;">Unsubscribe</a>'
        '</p>'
    )


def text_footer(url) -> str:
    return f"\n\n--\nDon't want these emails? Unsubscribe: {url}"


def headers(url) -> dict:
    """RFC 8058: lets Gmail, Outlook and others show their own Unsubscribe button."""
    return {'List-Unsubscribe': f'<{url}>', 'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click'}


def unsubscribe(company_id, email) -> bool:
    return do_not_email.block(company_id, email, do_not_email.UNSUBSCRIBED, source='marketing',
                              note='Used the unsubscribe link in a campaign email')
