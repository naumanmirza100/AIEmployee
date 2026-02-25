# Generated manually for AI Graph Generator (Marketing)

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketing_agent', '0026_rename_marketing_a_campaig_c04f71_idx_ppp_marketi_campaig_2b624b_idx_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='SavedGraphPrompt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(help_text='User-friendly title for the prompt', max_length=255)),
                ('prompt', models.TextField(help_text='The natural language prompt for graph generation')),
                ('chart_type', models.CharField(
                    choices=[
                        ('bar', 'Bar Chart'),
                        ('pie', 'Pie Chart'),
                        ('line', 'Line Chart'),
                        ('area', 'Area Chart'),
                        ('scatter', 'Scatter Plot'),
                        ('heatmap', 'Heat Map'),
                    ],
                    default='bar',
                    help_text='Type of chart this prompt generates',
                    max_length=20,
                )),
                ('tags', models.JSONField(blank=True, default=list, help_text='Tags for categorizing and searching prompts (e.g. dashboard)')),
                ('is_favorite', models.BooleanField(default=False, help_text='Whether this prompt is marked as favorite')),
                ('run_count', models.IntegerField(default=0, help_text='Number of times this prompt has been run')),
                ('last_run_at', models.DateTimeField(blank=True, null=True, help_text='Last time this prompt was executed')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(
                    help_text='User who saved this prompt (company user mapped to User)',
                    on_delete=models.deletion.CASCADE,
                    related_name='marketing_saved_graph_prompts',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'ppp_marketing_agent_savedgraphprompt',
                'ordering': ['-is_favorite', '-updated_at'],
                'verbose_name': 'Marketing Saved Graph Prompt',
                'verbose_name_plural': 'Marketing Saved Graph Prompts',
            },
        ),
        migrations.AddIndex(
            model_name='savedgraphprompt',
            index=models.Index(fields=['created_by', 'is_favorite'], name='ppp_marketi_created_8a1b2c_idx'),
        ),
        migrations.AddIndex(
            model_name='savedgraphprompt',
            index=models.Index(fields=['created_by', '-created_at'], name='ppp_marketi_created_9b2c3d_idx'),
        ),
    ]
