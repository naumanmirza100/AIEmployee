# Generated migration: SLA due date on Ticket + KB feedback model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Frontline_agent', '0013_savedgraphprompt'),
        ('core', '0035_add_frontline_agent_module'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='sla_due_at',
            field=models.DateTimeField(blank=True, help_text='Target response time for SLA; used for aging alerts', null=True),
        ),
        migrations.AddIndex(
            model_name='ticket',
            index=models.Index(fields=['sla_due_at'], name='Frontline_ticket_sla_due_idx'),
        ),
        migrations.CreateModel(
            name='KBFeedback',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('question', models.TextField(help_text='Question that was answered')),
                ('helpful', models.BooleanField(help_text='True = helpful, False = not helpful')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('company_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='frontline_kb_feedbacks', to='core.companyuser')),
                ('document', models.ForeignKey(blank=True, help_text='Document that was used for the answer (if any)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='kb_feedbacks', to='Frontline_agent.document')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='kbfeedback',
            index=models.Index(fields=['company_user', 'created_at'], name='Frontline_kb_company_idx'),
        ),
        migrations.AddIndex(
            model_name='kbfeedback',
            index=models.Index(fields=['document', 'helpful'], name='Frontline_kb_document_idx'),
        ),
    ]
