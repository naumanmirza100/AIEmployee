import React from 'react';
import { motion } from 'framer-motion';
import ModuleCard from './ModuleCard';
import { 
  Users, 
  Megaphone, 
  FolderKanban
} from 'lucide-react';

const ModuleCardsSection = () => {
  // Gradient color mappings for inline styles
  const gradientColors = {
    'blue-500': '#3b82f6',
    'cyan-500': '#06b6d4',
    'purple-500': '#a855f7',
    'pink-500': '#ec4899',
    'green-500': '#22c55e',
    'emerald-500': '#10b981'
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
    }
  ];

  return (
    <section className="py-16 md:py-24 bg-gradient-to-b from-background via-secondary/20 to-background">
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
