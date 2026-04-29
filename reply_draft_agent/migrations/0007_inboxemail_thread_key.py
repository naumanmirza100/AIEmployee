# Generated for thread grouping in the Reply Draft Agent.
#
# Adds InboxEmail.thread_key + index, then backfills the column for any
# rows already in the table so the inbox view groups historical mail
# instead of showing every existing message as its own thread.

from django.db import migrations, models


def _backfill_thread_keys(apps, schema_editor):
    """Populate thread_key for every existing InboxEmail row.

    Uses the same compute_thread_key() static method the live model
    exposes — but importing from the live module is unsafe inside a
    migration (model state may differ), so we duplicate the small
    helper inline. Keep this in sync with InboxEmail.compute_thread_key
    if the algorithm changes.
    """
    import hashlib
    import re

    InboxEmail = apps.get_model('reply_draft_agent', 'InboxEmail')

    def _compute(references, in_reply_to, subject, from_email, to_email, max_len=120):
        refs = (references or '').strip()
        if refs:
            first = refs.split()[0].strip().lstrip('<').rstrip('>')
            if first:
                return ('root:' + first)[:max_len]
        irt = (in_reply_to or '').strip().lstrip('<').rstrip('>')
        if irt:
            return ('irt:' + irt)[:max_len]
        subj = (subject or '').strip()
        subj = re.sub(r'^(?:\s*(?:re|fwd?|aw)\s*:\s*)+', '', subj, flags=re.IGNORECASE)
        subj = re.sub(r'\s+', ' ', subj).strip().lower()
        pair = sorted(filter(None, [(from_email or '').strip().lower(), (to_email or '').strip().lower()]))
        seed = (subj + '|' + '|'.join(pair)).encode('utf-8', 'ignore')
        digest = hashlib.sha1(seed).hexdigest()[:24]
        return ('subj:' + digest)[:max_len]

    # Iterate in chunks so the backfill scales — `iterator` avoids
    # loading every row into memory on installations with large inboxes.
    qs = InboxEmail.objects.all().only(
        'id', 'references', 'in_reply_to', 'subject', 'from_email', 'to_email', 'thread_key'
    )
    batch = []
    for row in qs.iterator(chunk_size=500):
        if row.thread_key:
            continue
        row.thread_key = _compute(
            row.references, row.in_reply_to, row.subject,
            row.from_email, row.to_email,
        )
        batch.append(row)
        if len(batch) >= 500:
            InboxEmail.objects.bulk_update(batch, ['thread_key'])
            batch = []
    if batch:
        InboxEmail.objects.bulk_update(batch, ['thread_key'])


def _noop_reverse(apps, schema_editor):
    """No reverse — dropping the column already removes the data."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('reply_draft_agent', '0006_inboxattachment'),
    ]

    operations = [
        migrations.AddField(
            model_name='inboxemail',
            name='thread_key',
            field=models.CharField(
                blank=True, db_index=True, default='', max_length=120,
                help_text='Stable key shared by every message in the same conversation.',
            ),
        ),
        migrations.AddIndex(
            model_name='inboxemail',
            index=models.Index(
                fields=['email_account', 'thread_key'],
                name='ppp_rda_inboxemail_acct_thread_idx',
            ),
        ),
        migrations.RunPython(_backfill_thread_keys, _noop_reverse),
    ]
