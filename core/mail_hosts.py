"""Whether the server may connect to a company's mail server (21 Nov 2026, the test report's Marketing 1).

A company types its own SMTP and IMAP hosts. Marketing and Reply Draft connected to whatever was typed, so a company
admin could aim the server at its own network (127.0.0.1, the Docker network, the cloud's metadata address) and tell
from the "Test" button's error and timing which ports were open. AI SDR already refused that
(`ai_sdr_agent.agents.outreach_agent.validate_mail_server`: public hosts, mail ports); this applies the same check to
every mailbox, when it is saved, tested and connected to.

`ALLOW_PRIVATE_MAIL_HOSTS` (settings, from the environment; off by default) lets a local mail catcher such as GreenMail
on 127.0.0.1 through, for development and the test settings.
"""
from django.conf import settings


def mail_server_error(host, port=None, kind='smtp'):
    """A sentence saying why `host`:`port` must not be connected to, or None when it may."""
    if getattr(settings, 'ALLOW_PRIVATE_MAIL_HOSTS', False):
        return None
    from ai_sdr_agent.agents.outreach_agent import validate_mail_server
    try:
        return validate_mail_server(host, port, kind)
    except (TypeError, ValueError):
        return f'The {kind.upper()} port must be a number.'


class MailServerRefused(ValueError):
    """Raised where a connection is about to be made to a mail server that `mail_server_error` refuses."""


def check_mail_server(host, port=None, kind='smtp'):
    """Raise MailServerRefused when `host`:`port` must not be connected to."""
    error = mail_server_error(host, port, kind)
    if error:
        raise MailServerRefused(error)
