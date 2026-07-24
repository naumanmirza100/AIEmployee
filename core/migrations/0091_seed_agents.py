# Seeds the Agent catalogue from the lists that were previously hardcoded in
# core/models.py (AGENT_CHOICES / MODULE_CHOICES / AGENT_DEFAULT_PROVIDER) and
# mirrored by hand in the frontend. From here on the table is the source of truth.

from django.db import migrations


AGENTS = [
    {
        'slug': 'recruitment_agent',
        'name': 'Recruitment Agent',
        'description': 'AI-powered recruitment solution to automate CV screening, candidate matching, and interview scheduling.',
        'default_provider': 'groq',
        'sort_order': 10,
        'features': [
            'Automated CV parsing and screening',
            'AI-powered candidate matching',
            'Interview scheduling automation',
            'Email follow-ups and reminders',
            'Job-specific slot management',
            'Real-time candidate tracking',
        ],
    },
    {
        'slug': 'marketing_agent',
        'name': 'Marketing Agent',
        'description': 'Complete marketing automation platform with email campaigns, lead generation, and performance analytics.',
        'default_provider': 'groq',
        'sort_order': 20,
        'features': [
            'Automated email campaigns',
            'Lead generation & enrichment',
            'Campaign performance tracking',
            'A/B testing capabilities',
            'Social media integration',
            'Advanced analytics dashboard',
        ],
    },
    {
        'slug': 'project_manager_agent',
        'name': 'Project Manager Agent',
        'description': 'Intelligent project management with AI task prioritization, timeline generation, and team coordination.',
        'default_provider': 'groq',
        'sort_order': 30,
        'features': [
            'AI task prioritization',
            'Automated timeline & Gantt charts',
            'Project pilot & planning',
            'Knowledge base Q&A',
            'Team collaboration tools',
            'Progress tracking & reports',
        ],
    },
    {
        'slug': 'frontline_agent',
        'name': 'Frontline Agent',
        'description': 'AI-powered customer support system with automated ticket resolution, knowledge base Q&A, and document processing.',
        'default_provider': 'openai',
        'sort_order': 40,
        'features': [
            'Automated ticket classification & resolution',
            'Knowledge base Q&A from documents',
            'Document upload & processing',
            'Multi-channel support (chat, email, web)',
            'Proactive notifications & follow-ups',
            'Analytics & performance tracking',
        ],
    },
    {
        'slug': 'operations_agent',
        'name': 'Operations Agent',
        'description': 'Internal ops and analysis workhorse for document processing, summarization, analytics dashboards, and knowledge Q&A.',
        'default_provider': 'groq',
        'sort_order': 50,
        'features': [
            'Document processing & parsing (PDF, DOCX, Excel)',
            'AI-powered document summarization & insights',
            'Analytics dashboards & trend detection',
            'Knowledge base Q&A with source citations',
            'Automated report & memo generation',
            'Proactive anomaly & threshold alerts',
        ],
    },
    {
        'slug': 'ai_sdr_agent',
        'name': 'AI SDR Agent',
        'description': 'Automated sales development rep with AI lead scoring, multi-step outreach sequences, meeting scheduling, and pipeline analytics.',
        'default_provider': 'groq',
        'sort_order': 60,
        'features': [
            'AI lead scoring (Hot / Warm / Cold)',
            'Multi-step outreach sequences',
            'Personalized AI email drafting',
            'Meeting scheduling & AI prep notes',
            'Pipeline funnel analytics',
            'CRM-ready lead management',
        ],
    },
    {
        'slug': 'reply_draft_agent',
        'name': 'Reply Draft Agent',
        'description': 'AI-assisted email reply drafting with human-in-the-loop review. Drafts replies from incoming emails, you edit and approve before sending.',
        'default_provider': 'groq',
        'sort_order': 70,
        'features': [
            'AI-generated reply drafts from inbox',
            'Tone selection (professional, casual, empathetic)',
            'Regenerate with custom instructions',
            'Inline edit before approving',
            'Proper email threading (In-Reply-To)',
            'Full version history of regenerations',
        ],
    },
    {
        'slug': 'hr_agent',
        'name': 'HR Support Agent',
        'description': 'Employee-facing HR assistant — answers policy questions, runs onboarding/offboarding workflows, processes HR documents, and books HR meetings.',
        'default_provider': 'groq',
        'sort_order': 80,
        'features': [
            'Knowledge Q&A from your handbook & policies',
            'Confidentiality-aware retrieval (IC vs manager vs HR)',
            'Onboarding & offboarding SOP automation',
            'HR document processing (offer letters, contracts, payslips)',
            'Birthday, anniversary & probation reminders',
            'Typed HR meetings (1:1, performance review, exit, grievance)',
        ],
    },
    {
        'slug': 'exec_meeting_agent',
        'name': 'AI Executive Meeting Assistant',
        'description': 'Full meeting lifecycle management — schedule, take notes, prioritize tasks, auto-plan your calendar, draft documents, and get proactive reminders.',
        'default_provider': 'groq',
        'sort_order': 90,
        'features': [
            'Natural language meeting scheduling',
            'AI meeting notes & action item extraction',
            'Smart task prioritization & workload analysis',
            'Calendar auto-planning & free slot suggestions',
            'AI document authoring (agenda, minutes, briefings)',
            'Proactive reminders & daily digest',
        ],
    },
]


def seed_agents(apps, schema_editor):
    Agent = apps.get_model('core', 'Agent')
    for row in AGENTS:
        # update_or_create keeps this re-runnable and safe if a row already exists.
        Agent.objects.update_or_create(
            slug=row['slug'],
            defaults={
                'name': row['name'],
                'description': row['description'],
                'features': row['features'],
                'default_provider': row['default_provider'],
                'sort_order': row['sort_order'],
                'is_active': True,
                'is_purchasable': True,
            },
        )


def unseed_agents(apps, schema_editor):
    Agent = apps.get_model('core', 'Agent')
    Agent.objects.filter(slug__in=[r['slug'] for r in AGENTS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0090_agent_alter_adminpricingconfig_agent_name_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_agents, unseed_agents),
    ]
