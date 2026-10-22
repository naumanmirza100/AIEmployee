"""Keep a demo company's email on the server: mail for demo addresses goes to a practice mail server.

A showcase on the live site runs a made-up company whose people, leads and candidates all have addresses under
DEMO_MAIL_DOMAIN (for example ayesha@crestline.demo.payperproject.com). The site's own email (invitations, alerts,
replies to customers) would otherwise go out through the real mail account and bounce, or worse reach someone.
With DEMO_MAIL_DOMAIN set, settings make this the email backend:

    a recipient under DEMO_MAIL_DOMAIN   the practice server at DEMO_MAIL_HOST:DEMO_MAIL_PORT (plain SMTP, no login)
    anyone else                          the backend the site would have used anyway (DEMO_MAIL_REAL_BACKEND)

A message to both kinds of recipient is split, each copy addressed only to its own side. Unset, nothing changes.
"""
import copy
from email.utils import parseaddr

from django.conf import settings
from django.core.mail import get_connection
from django.core.mail.backends.base import BaseEmailBackend


def is_demo_address(address) -> bool:
    domain = settings.DEMO_MAIL_DOMAIN
    if not domain:
        return False
    host = parseaddr(address or '')[1].rpartition('@')[2].strip().lower()
    return host == domain or host.endswith('.' + domain)


def _addressed_to(message, keep):
    """A copy of the message for only the recipients `keep` accepts, or None when none are left."""
    to, cc, bcc = ([a for a in field if keep(a)] for field in (message.to, message.cc, message.bcc))
    if not (to or cc or bcc):
        return None
    part = copy.copy(message)
    part.to, part.cc, part.bcc = to, cc, bcc
    return part


class DemoRoutingBackend(BaseEmailBackend):
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.real = get_connection(settings.DEMO_MAIL_REAL_BACKEND, fail_silently=fail_silently, **kwargs)
        self.demo = self._demo_connection()

    def _demo_connection(self):
        return get_connection(
            'django.core.mail.backends.smtp.EmailBackend', fail_silently=self.fail_silently,
            host=settings.DEMO_MAIL_HOST, port=settings.DEMO_MAIL_PORT, username='', password='',
            use_tls=False, use_ssl=False,
        )

    def close(self):
        self.real.close()
        self.demo.close()

    def send_messages(self, email_messages):
        demo, real = [], []
        for message in email_messages:
            demo.append(_addressed_to(message, is_demo_address))
            real.append(_addressed_to(message, lambda a: not is_demo_address(a)))
        demo, real = [m for m in demo if m], [m for m in real if m]
        sent = (self.demo.send_messages(demo) or 0) if demo else 0
        return sent + ((self.real.send_messages(real) or 0) if real else 0)
