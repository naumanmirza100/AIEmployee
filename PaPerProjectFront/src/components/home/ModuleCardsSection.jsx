import React from 'react';
import { motion } from 'framer-motion';
import ModuleCard from './ModuleCard';
import {
  Users,
  Megaphone,
  FolderKanban,
  Headphones,
  FileSearch,
  Reply,
  Target,
} from 'lucide-react';

const ModuleCardsSection = () => {
  // Gradient color mappings for inline styles
  const gradientColors = {
    'blue-500': '#3b82f6',
    'cyan-500': '#06b6d4',
    'purple-500': '#a855f7',
    'pink-500': '#ec4899',
    'green-500': '#22c55e',
    'emerald-500': '#10b981',
    'amber-500': '#f59e0b',
    'orange-500': '#f97316'
  };

  const modules = [
    {
      title: 'Recruitment Agent',
      moduleName: 'recruitment_agent',
      description: 'AI-powered recruitment solution to automate CV screening, candidate matching, and interview scheduling.',
      icon: Users,
      iconColor: 'text-blue-500',
      gradientFrom: gradientColors['blue-500'],
      gradientTo: gradientColors['cyan-500'],
      price: 99,
      pricePeriod: 'month',
      features: [
        'Automated CV parsing and screening',
        'AI-powered candidate matching',
        'Interview scheduling automation',
        'Email follow-ups and reminders',
        'Job-specific slot management',
        'Real-time candidate tracking'
      ],
      highlight: true,
    },
    {
      title: 'Marketing Agent',
      moduleName: 'marketing_agent',
      description: 'Complete marketing automation platform with email campaigns, lead generation, and performance analytics.',
      icon: Megaphone,
      iconColor: 'text-purple-500',
      gradientFrom: gradientColors['purple-500'],
      gradientTo: gradientColors['pink-500'],
      price: 149,
      pricePeriod: 'month',
      features: [
        'Automated email campaigns',
        'Lead generation & enrichment',
        'Campaign performance tracking',
        'A/B testing capabilities',
        'Social media integration',
        'Advanced analytics dashboard'
      ],
      highlight: false,
    },
    {
      title: 'Project Manager Agent',
      moduleName: 'project_manager_agent',
      description: 'Intelligent project management with AI task prioritization, timeline generation, and team coordination.',
      icon: FolderKanban,
      iconColor: 'text-green-500',
      gradientFrom: gradientColors['green-500'],
      gradientTo: gradientColors['emerald-500'],
      price: 199,
      pricePeriod: 'month',
      features: [
        'AI task prioritization',
        'Automated timeline & Gantt charts',
        'Project pilot & planning',
        'Knowledge base Q&A',
        'Team collaboration tools',
        'Progress tracking & reports'
      ],
      highlight: false,
    },
    {
      title: 'Frontline Agent',
      moduleName: 'frontline_agent',
      description: 'AI-powered customer support system with automated ticket resolution, knowledge base Q&A, and document processing.',
      icon: Headphones,
      iconColor: 'text-orange-500',
      gradientFrom: gradientColors['emerald-500'],
      gradientTo: gradientColors['green-500'],
      price: 149,
      pricePeriod: 'month',
      features: [
        'Automated ticket classification & resolution',
        'Knowledge base Q&A from documents',
        'Document upload & processing',
        'Multi-channel support (chat, email, web)',
        'Proactive notifications & follow-ups',
        'Analytics & performance tracking'
      ],
      highlight: false,
    },
    {
      title: 'Operations Agent',
      moduleName: 'operations_agent',
      description: 'Internal ops and analysis workhorse for document processing, summarization, analytics dashboards, and knowledge Q&A.',
      icon: FileSearch,
      iconColor: 'text-amber-500',
      gradientFrom: gradientColors['amber-500'],
      gradientTo: gradientColors['orange-500'],
      price: 179,
      pricePeriod: 'month',
      features: [
        'Document processing & parsing (PDF, DOCX, Excel)',
        'AI-powered document summarization & insights',
        'Analytics dashboards & trend detection',
        'Knowledge base Q&A with source citations',
        'Automated report & memo generation',
        'Proactive anomaly & threshold alerts'
      ],
      highlight: false,
    },
    {
      title: 'AI SDR Agent',
      moduleName: 'ai_sdr_agent',
      description: 'Automated sales development rep with AI lead scoring, multi-step outreach sequences, meeting scheduling, and pipeline analytics.',
      icon: Target,
      iconColor: 'text-rose-500',
      gradientFrom: '#f43f5e',
      gradientTo: '#a855f7',
      price: 199,
      pricePeriod: 'month',
      features: [
        'AI lead scoring (Hot / Warm / Cold)',
        'Multi-step outreach sequences',
        'Personalized AI email drafting',
        'Meeting scheduling & AI prep notes',
        'Pipeline funnel analytics',
        'CRM-ready lead management',
      ],
      highlight: false,
    },
    {
      title: 'Reply Draft Agent',
      moduleName: 'reply_draft_agent',
      description: 'AI-assisted email reply drafting with human-in-the-loop review. Drafts replies from incoming emails, you edit and approve before sending.',
      icon: Reply,
      iconColor: 'text-cyan-500',
      gradientFrom: gradientColors['cyan-500'],
      gradientTo: gradientColors['blue-500'],
      price: 79,
      pricePeriod: 'month',
      features: [
        'AI-generated reply drafts from inbox',
        'Tone selection (professional, casual, empathetic)',
        'Regenerate with custom instructions',
        'Inline edit before approving',
        'Proper email threading (In-Reply-To)',
        'Full version history of regenerations'
      ],
      highlight: false,
    }
  ];

  return (
    <section id="ai-modules" className="py-16 md:py-24 bg-gradient-to-b from-background via-secondary/20 to-background">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
          className="text-center mb-12 md:mb-16"
        >
          <h2 className="text-4xl md:text-5xl font-bold text-foreground font-heading mb-4">
            AI-Powered Modules
          </h2>
          <p className="text-lg md:text-xl text-muted-foreground max-w-3xl mx-auto">
            Choose the perfect AI agent for your business needs. Each module is designed to automate and optimize your workflows.
          </p>
        </motion.div>

        {/* Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 md:gap-8">
          {modules.map((module, index) => (
            <ModuleCard
              key={index}
              title={module.title}
              moduleName={module.moduleName}
              description={module.description}
              icon={module.icon}
              iconColor={module.iconColor}
              gradientFrom={module.gradientFrom}
              gradientTo={module.gradientTo}
              price={module.price}
              pricePeriod={module.pricePeriod}
              features={module.features}
              highlight={module.highlight}
            />
          ))}
        </div>

        {/* Additional Info */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, delay: 0.3 }}
          className="mt-12 text-center"
        >
          <p className="text-sm text-muted-foreground">
            All modules include 24/7 support, regular updates, and a 30-day money-back guarantee.
          </p>
        </motion.div>
      </div>
    </section>
  );
};

export default ModuleCardsSection;
