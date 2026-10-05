# One do-not-email list per company, shared by every agent that does outreach
# (core.do_not_email).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0109_quickchat'),
    ]

    operations = [
        migrations.CreateModel(
            name='DoNotEmail',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.CharField(max_length=254)),
                ('reason', models.CharField(choices=[('unsubscribed', 'Unsubscribed'), ('bounced', 'Bounced'),
                                                     ('manual', 'Added by hand')],
                                            default='unsubscribed', max_length=20)),
                ('source', models.CharField(blank=True, default='', max_length=30)),
                ('note', models.CharField(blank=True, default='', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('added_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                               related_name='+', to='core.companyuser')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                              related_name='do_not_email', to='core.company')),
            ],
            options={
                'ordering': ['-created_at', '-id'],
                'unique_together': {('company', 'email')},
            },
        ),
    ]
