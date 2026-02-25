# Generated migration: SavedGraphPrompt for AI graph save/favorites

from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ('Frontline_agent', '0012_ticket_company'),
        ('core', '0035_add_frontline_agent_module'),
    ]

    operations = [
        migrations.CreateModel(
            name='SavedGraphPrompt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('prompt', models.TextField()),
                ('chart_type', models.CharField(choices=[('bar', 'Bar Chart'), ('pie', 'Pie Chart'), ('line', 'Line Chart'), ('area', 'Area Chart')], default='bar', max_length=20)),
                ('tags', models.JSONField(blank=True, default=list)),
                ('is_favorite', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(default=timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='frontline_saved_graph_prompts', to='core.companyuser')),
            ],
            options={
                'verbose_name': 'Saved Graph Prompt',
                'verbose_name_plural': 'Saved Graph Prompts',
                'ordering': ['-is_favorite', '-updated_at'],
            },
        ),
    ]
