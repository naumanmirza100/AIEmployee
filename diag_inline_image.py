"""Diagnose broken inline (body-embedded) image.

Run it as a Django management-shell command file so blank lines don't break
block parsing in the piped REPL:

    python manage.py shell -c "exec(open('diag_inline_image.py').read())"

Prints, for the latest InboxEmail rows that HAVE inline attachments:
  - body_html length + its full content (it's usually tiny)
  - every cid:/<img> ref found in the html
  - each attachment: size, content_type, is_inline, content_id, file exists,
    and whether it exceeds the 1 MB inline-embed cap.
"""
import re
from reply_draft_agent.models import InboxEmail, InboxAttachment

INLINE_CAP = 1024 * 1024

inline_email_ids = list(
    InboxAttachment.objects.filter(is_inline=True)
    .values_list('inbox_email_id', flat=True).distinct()
)
emails = InboxEmail.objects.filter(id__in=inline_email_ids).order_by('-received_at')[:5]

if not emails:
    print("NO inline attachments stored on any email. The 'simple' photo was "
          "NOT saved as an inline part -> extraction issue, not rendering.")

for m in emails:
    print("=" * 70)
    print("Email #%s subject=%r received=%s" % (m.id, m.subject, m.received_at))
    html = m.body_html or ''
    print("body_html len=%d" % len(html))
    print("body_html FULL >>>")
    print(html)
    print("<<< end body_html")
    print("cid refs:", re.findall(r'cid:\s*([^"\'>\s]+)', html, re.I))
    print("img tags:", re.findall(r'<img[^>]*>', html, re.I))
    print("-- attachments --")
    for att in m.attachments.all():
        try:
            exists = bool(att.file) and att.file.storage.exists(att.file.name)
        except Exception as e:
            exists = "ERR(%s)" % e
        print("  #%s %r | %sB (%.2f MB) | ct=%r | inline=%s | cid=%r | exists=%s | OVER_1MB=%s" % (
            att.id, att.filename, att.size_bytes, (att.size_bytes or 0)/1048576.0,
            att.content_type, att.is_inline, att.content_id, exists,
            (att.size_bytes or 0) > INLINE_CAP))
    print()

# Also show the newest email overall in case #164 had no inline row at all.
latest = InboxEmail.objects.order_by('-received_at').first()
if latest:
    print("#" * 70)
    print("NEWEST email overall: #%s subject=%r" % (latest.id, latest.subject))
    print("body_html len=%d" % len(latest.body_html or ''))
    print("body_html:", (latest.body_html or '')[:500])
    print("attachments:")
    for att in latest.attachments.all():
        print("  #%s %r inline=%s ct=%r cid=%r size=%sB" % (
            att.id, att.filename, att.is_inline, att.content_type,
            att.content_id, att.size_bytes))
