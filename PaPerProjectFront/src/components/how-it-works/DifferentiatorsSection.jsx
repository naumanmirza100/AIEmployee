import React from 'react';
import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Moon, Map, FileText, Puzzle, Users2, TrendingUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.1, delayChildren: 0.2 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.5, ease: "easeOut" } },
};

const DifferentiatorsSection = () => {
  const { t } = useTranslation();
  const differentiators = [
      { icon: Moon, title: "Night & Weekend Delivery", description: "Activate extended delivery timelines so even urgent projects keep moving outside the 9–5.", badge: "Coming Soon" },
      { icon: Map, title: "Vision-to-Roadmap Service", description: "Upload your idea, and we'll turn it into a full roadmap, delivered phase-by-phase with clarity.", badge: "Coming Soon" },
      { icon: FileText, title: "Proof-of-Work Snapshot", description: "On delivery, get a breakdown of what was done and why, building trust and clarity." },
      { icon: Puzzle, title: "Strategic Add-On Suggestions", description: "We recommend complementary services like SEO or Marketing, pre-scoped and ready to go." },
      { icon: Users2, title: "Multi-Stakeholder Collaboration", description: "Add teammates or clients to collaborate with tailored permissions, comments, and updates.", badge: "Built In" },
      { icon: TrendingUp, title: "Auto-Optimization Post-Delivery", description: "We monitor performance post-launch and offer free improvements if anything underperforms (Free for 30 Days)." },
  ];
  return (
    <section className="py-20 md:py-28 bg-background">
      <div className="container mx-auto px-4 md:px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.3 }}
          className="text-center mb-16"
        >
          <h2 className="text-4xl md:text-5xl font-bold text-foreground">{t('how_it_works_differentiators_title')}</h2>
          <p className="max-w-3xl mx-auto mt-4 text-lg text-muted-foreground">
            {t('how_it_works_differentiators_subtitle')}
          </p>
        </motion.div>
        <motion.div
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.1 }}
          className="grid md:grid-cols-2 lg:grid-cols-3 gap-8 max-w-7xl mx-auto"
        >
          {differentiators.map((feature, index) => (
            <motion.div key={index} variants={itemVariants} className="h-full">
              <Card className="p-8 bg-card border shadow-lg hover:shadow-xl transition-shadow duration-300 h-full flex flex-col rounded-xl">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
                    <feature.icon className="h-6 w-6 text-primary" />
                  </div>
                  {feature.badge && (
                    <div className="text-xs font-bold uppercase tracking-wider text-pure-white bg-primary px-3 py-1 rounded-full">
                      {feature.badge}
                    </div>
                  )}
                </div>
                <CardHeader className="p-0 pb-2">
                  <CardTitle className="text-xl font-bold text-foreground">{feature.title}</CardTitle>
                </CardHeader>
                <CardContent className="p-0 flex-grow">
                  <p className="text-muted-foreground text-base">{feature.description}</p>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
};

export default DifferentiatorsSection;