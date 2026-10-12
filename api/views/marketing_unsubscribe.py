"""The page behind the unsubscribe link in Marketing campaign emails.

Public: the signed link is the proof (marketing_agent/services/unsubscribe.py).
GET shows a button and changes nothing, because mail scanners and link previews
open every link in an email. POST unsubscribes; it is also what a mail program's
own one-click Unsubscribe sends (RFC 8058).
"""
import logging

from django.http import HttpResponse
from django.utils.html import escape
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from marketing_agent.services import unsubscribe as links

logger = logging.getLogger(__name__)


def _page(heading, message, *, button='', status=200):
    form = (
        '<form method="post" action="">'
        '<button type="submit" style="padding:12px 26px;border:0;border-radius:8px;background:#dc2626;'
        f'color:#fff;font-size:15px;font-weight:600;cursor:pointer;">{escape(button)}</button></form>'
    ) if button else ''
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{escape(heading)}</title></head>
<body style="margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:#0f172a;color:#e2e8f0;">
  <div style="max-width:480px;margin:8vh auto;padding:40px 32px;background:#1e293b;border-radius:16px;text-align:center;box-shadow:0 10px 40px rgba(0,0,0,.4);">
    <h1 style="margin:0 0 12px;font-size:22px;color:#f8fafc;">{escape(heading)}</h1>
    <p style="margin:0 0 24px;font-size:15px;line-height:1.6;color:#94a3b8;">{escape(message)}</p>
    {form}
  </div>
</body></html>"""
    return HttpResponse(html, status=status, content_type='text/html')


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def marketing_unsubscribe(request, token):
    target = links.read_token(token)
    if target is None:
        # Not 200: a mail program takes 200 from its one-click unsubscribe to mean "done".
        return _page('We could not unsubscribe you from this link',
                     'This link is not valid, so nothing has been changed. Please reply to the email you '
                     'received with the word "unsubscribe" and you will be taken off the list.', status=404)
    company_id, email = target

    if request.method == 'GET':
        return _page('Unsubscribe from these emails?', f'{email} will no longer receive emails from us.',
                     button='Unsubscribe')

    links.unsubscribe(company_id, email)
    logger.info('Marketing [UNSUBSCRIBE] company=%s address=%s', company_id, email)
    return _page("You've been unsubscribed", f"{email} won't receive any more emails from us.")
