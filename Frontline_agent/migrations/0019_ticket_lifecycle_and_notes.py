from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('Frontline_agent', '0018_llmusage'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='snoozed_until',
            field=models.DateTimeField(blank=True, db_index=True, null=True,
                                       help_text='If set and in the future, ticket is snoozed and hidden from queues.'),
        ),
        migrations.AddField(
            model_name='ticket',
            name='sla_paused_at',
            field=models.DateTimeField(blank=True, null=True,
                                       help_text='If set, the SLA clock is currently paused since this time.'),
        ),
        migrations.AddField(
            model_name='ticket',
            name='sla_paused_accumulated_seconds',
            field=models.IntegerField(default=0,
                                      help_text='Total accumulated paused seconds across all pause/resume cycles.'),
        ),
        migrations.AddField(
            model_name='ticket',
            name='last_triaged_at',
            field=models.DateTimeField(blank=True, null=True,
                                       help_text='When triage was last run (create or re-triage on update).'),
        ),
        migrations.AddIndex(
            model_name='ticket',
            index=models.Index(fields=['snoozed_until'], name='fl_ticket_snooze_idx'),
        ),
        migrations.CreateModel(
            name='TicketNote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('body', models.TextField()),
                ('is_internal', models.BooleanField(default=True, help_text='True = private agent note. Reserved False for future customer-visible comments.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('author', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                             related_name='frontline_ticket_notes', to=settings.AUTH_USER_MODEL)),
                ('ticket', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                             related_name='notes', to='Frontline_agent.ticket')),
            ],
            options={
                'ordering': ['created_at'],
                'indexes': [models.Index(fields=['ticket', 'created_at'], name='fl_note_ticket_ct_idx')],
            },
        ),
    ]
