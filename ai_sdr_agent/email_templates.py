"""Rendering the HTML email templates users write (SDREmailTemplate) for one lead.

A template's subject and HTML use the same variables as campaign steps, plus {unsubscribe_url}. Lead and sender
values are HTML-escaped as they go into the HTML: they come from imports, providers and free text. The plain-text
version every email is sent with is made from the HTML. A template with no {unsubscribe_url} gets a small footer with
the campaign's postal address and an unsubscribe link, so no email goes out without one.
"""
import html as _html
import re

VARIABLES = (
    'first_name', 'last_name', 'full_name', 'company_name', 'job_title', 'company_industry', 'company_location',
    'sender_name', 'sender_title', 'sender_company', 'unsubscribe_url',
)
_PLACEHOLDER = re.compile(r'\{([a-z_]+)\}')


def unknown_variables(*texts) -> list:
    """The {placeholders} in ``texts`` that are not variables: they would reach the lead as typed."""
    found = set()
    for text in texts:
        found.update(m for m in _PLACEHOLDER.findall(text or '') if m not in VARIABLES)
    return sorted(f'{{{m}}}' for m in found)


def lead_values(lead, campaign, unsubscribe_url: str = '') -> dict:
    """What each variable stands for, for this lead and this campaign's sender."""
    first = lead.first_name or (lead.display_name.split()[0] if lead.display_name else 'there')
    return {
        'first_name': first,
        'last_name': lead.last_name or '',
        'full_name': lead.display_name or first,
        'company_name': lead.company_name or 'your company',
        'job_title': lead.job_title or 'your role',
        'company_industry': lead.company_industry or 'your industry',
        'company_location': lead.company_location or '',
        'sender_name': (campaign.sender_name if campaign else '') or '',
        'sender_title': (campaign.sender_title if campaign else '') or '',
        'sender_company': (campaign.sender_company if campaign else '') or '',
        'unsubscribe_url': unsubscribe_url or '#',
    }


def _fill(text: str, values: dict, escape: bool) -> str:
    def one(m):
        if m.group(1) not in values:
            return m.group(0)
        value = str(values[m.group(1)])
        return _html.escape(value, quote=True) if escape else value
    return _PLACEHOLDER.sub(one, text or '')


def _footer(postal_address: str, unsubscribe_url: str) -> str:
    address = f'{_html.escape(postal_address)}<br/>' if postal_address else ''
    return ('<div style="margin:24px auto 0;max-width:600px;padding:0 16px;color:#9ca3af;font-size:12px;'
            'line-height:1.6;text-align:center;font-family:Helvetica,Arial,sans-serif;">'
            f'{address}Don\'t want to hear from us? '
            f'<a href="{_html.escape(unsubscribe_url or "#", quote=True)}" style="color:#6b7280;">Unsubscribe</a>'
            '</div>')


def html_to_text(html: str) -> str:
    """The plain-text version of an email: the words, links as "text (url)", blocks on their own lines."""
    text = re.sub(r'(?is)<(script|style|head|title)\b.*?</\1>', '', html or '')
    text = re.sub(r'(?is)<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                  lambda m: (lambda label, url: label if url in ('#', label) or url.startswith('#')
                             else f'{label} ({url})' if label else url)(
                      re.sub(r'<[^>]+>', '', m.group(2)).strip(), m.group(1).strip()), text)
    text = re.sub(r'(?i)<br\s*/?>', '\n', text)
    text = re.sub(r'(?i)</(p|div|tr|h[1-6]|li|table)>', '\n', text)
    text = re.sub(r'(?i)<li\b[^>]*>', '• ', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = _html.unescape(text)
    lines = [re.sub(r'[ \t\xa0]+', ' ', l).strip() for l in text.split('\n')]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def render(template_html: str, subject: str, lead, campaign, unsubscribe_url: str = '') -> tuple:
    """(subject, html, text) of a template for one lead, ready to send."""
    values = lead_values(lead, campaign, unsubscribe_url)
    body = _fill(template_html, values, escape=True)
    if '{unsubscribe_url}' not in (template_html or ''):
        footer = _footer(getattr(campaign, 'postal_address', '') or '', unsubscribe_url)
        body = re.sub(r'(?i)</body>', footer + '</body>', body, count=1) if re.search(r'(?i)</body>', body) \
            else body + footer
    rendered_subject = ' '.join(_fill(subject, values, escape=False).split())
    return rendered_subject, body, html_to_text(body)


STARTER_HTML = """<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f5f5f8;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f8;">
    <tr><td align="center" style="padding:32px 12px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
             style="max-width:600px;background:#ffffff;border:1px solid #ececf1;border-radius:14px;
                    font-family:Helvetica,Arial,sans-serif;">
        <tr><td style="height:4px;background:#7c3aed;border-radius:14px 14px 0 0;font-size:0;">&nbsp;</td></tr>
        <tr><td style="padding:28px 40px 8px;color:#7c3aed;font-size:12px;font-weight:700;letter-spacing:0.08em;
                       text-transform:uppercase;">{sender_company}</td></tr>
        <tr><td style="padding:12px 40px 8px;color:#1f2937;font-size:15px;line-height:1.7;">
          <p style="margin:0 0 16px;">Hi {first_name},</p>
          <p style="margin:0 0 16px;">Write your message to {company_name} here.</p>
          <p style="margin:0 0 16px;">Best,<br/>{sender_name}<br/>{sender_title}, {sender_company}</p>
        </td></tr>
      </table>
      <p style="margin:18px 0 0;color:#9ca3af;font-size:12px;font-family:Helvetica,Arial,sans-serif;">
        Don't want to hear from us? <a href="{unsubscribe_url}" style="color:#6b7280;">Unsubscribe</a>
      </p>
    </td></tr>
  </table>
</body>
</html>"""
