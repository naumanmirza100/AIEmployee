"""Accept / reject / counter-propose flow for HR meetings.

`HRMeeting.participants` was a plain M2M, so Django auto-created
``hr_agent_hrmeeting_participants`` with columns ``id`` / ``hrmeeting_id`` /
``employee_id``. This migration promotes that table to an explicit through
model (`HRMeetingParticipant`) so each attendee can carry their own response
state — without touching the existing rows.

Step 1 is therefore **state-only**: it tells Django "a model already lives at
that table" and re-points the M2M through it. No SQL runs, so existing
participant links survive. Steps 2-4 are ordinary schema changes that add the
new response columns, the meeting-level `response_status`, and the
`HRMeetingResponse` negotiation log.
"""
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr_agent', '0014_leave_withdrawn_status'),
    ]

    operations = [
        # --- 1. Adopt the auto-created M2M table as a real model ------------
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name='HRMeetingParticipant',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                                   serialize=False, verbose_name='ID')),
                        ('meeting', models.ForeignKey(
                            db_column='hrmeeting_id',
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name='participant_rows',
                            to='hr_agent.hrmeeting')),
                        ('employee', models.ForeignKey(
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name='hr_meeting_participations',
                            to='hr_agent.employee')),
                    ],
                    options={
                        'db_table': 'hr_agent_hrmeeting_participants',
                        'ordering': ['created_at'],
                        'unique_together': {('meeting', 'employee')},
                    },
                ),
                migrations.AlterField(
                    model_name='hrmeeting',
                    name='participants',
                    field=models.ManyToManyField(
                        blank=True,
                        related_name='hr_meetings_attending',
                        through='hr_agent.HRMeetingParticipant',
                        to='hr_agent.employee'),
                ),
            ],
        ),

        # --- 2. Per-participant response state ------------------------------
        migrations.AddField(
            model_name='hrmeetingparticipant',
            name='status',
            field=models.CharField(
                choices=[('pending', 'Pending'), ('accepted', 'Accepted'),
                         ('rejected', 'Rejected'), ('counter_proposed', 'Counter Proposed')],
                default='pending', max_length=20),
        ),
        migrations.AddField(
            model_name='hrmeetingparticipant',
            name='reason',
            field=models.TextField(blank=True, default='',
                                   help_text='Reason for rejection or counter-proposal.'),
        ),
        migrations.AddField(
            model_name='hrmeetingparticipant',
            name='counter_proposed_time',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='hrmeetingparticipant',
            name='responded_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='hrmeetingparticipant',
            name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),

        # --- 3. Meeting-level negotiation state -----------------------------
        migrations.AddField(
            model_name='hrmeeting',
            name='response_status',
            field=models.CharField(
                choices=[('pending', 'Pending'), ('accepted', 'Accepted'),
                         ('partially_accepted', 'Partially Accepted'),
                         ('rejected', 'Rejected'),
                         ('counter_proposed', 'Counter Proposed'),
                         ('withdrawn', 'Withdrawn')],
                default='pending',
                help_text='Derived from participant responses (or set directly by the organizer).',
                max_length=20),
        ),

        # --- 4. Negotiation log ---------------------------------------------
        migrations.CreateModel(
            name='HRMeetingResponse',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('responder_name', models.CharField(
                    blank=True, default='',
                    help_text='Snapshot of the responder name at response time.',
                    max_length=255)),
                ('responded_by', models.CharField(
                    choices=[('organizer', 'Organizer'), ('participant', 'Participant')],
                    default='organizer', max_length=20)),
                ('action', models.CharField(
                    choices=[('proposed', 'Proposed'), ('accepted', 'Accepted'),
                             ('rejected', 'Rejected'),
                             ('counter_proposed', 'Counter Proposed'),
                             ('withdrawn', 'Withdrawn')],
                    max_length=20)),
                ('proposed_time', models.DateTimeField(
                    blank=True, null=True,
                    help_text='New proposed time (counter-proposals only).')),
                ('reason', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('meeting', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='responses', to='hr_agent.hrmeeting')),
                ('responder', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='hr_meeting_responses',
                    help_text='Employee who responded. Null for HR-admin dashboard '
                              'operators who have no Employee row.',
                    to='hr_agent.employee')),
            ],
            options={'ordering': ['created_at']},
        ),
        migrations.AddIndex(
            model_name='hrmeetingresponse',
            index=models.Index(fields=['meeting', 'created_at'],
                               name='hr_meet_resp_meeting_idx'),
        ),
    ]
