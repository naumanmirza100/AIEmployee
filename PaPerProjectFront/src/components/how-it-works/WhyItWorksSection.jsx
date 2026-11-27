import React from 'react';
import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Users, Rocket, HeartHandshake, Scale } from 'lucide-react';
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

const WhyItWorksSection = () => {
  const { t } = useTranslation();
  const whyItWorksFeatures = [
    { icon: Users, title: "Elite Vetted Teams", description: "Rigorous vetting means you only work with proven, high-performing development companies." },
    { icon: Rocket, title: "Proactive Management", description: "We don't just solve problems—we prevent them from happening with dedicated oversight." },
    { icon: HeartHandshake, title: "Total Accountability", description: "We are your single point of contact and responsibility. The buck stops with us, always." },
    { icon: Scale, title: "Fixed, Fair Pricing", description: "The price we quote is the price you pay. No hidden fees, no scope creep, no surprises." },
  ];
  return (
    <section className="py-20 md:py-28 bg-foreground text-background">
      <div className="container mx-auto px-4 md:px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.3 }}
          className="text-center mb-16"
        >
          <h2 className="text-4xl md:text-5xl font-bold tracking-tight">{t('how_it_works_why_title')}</h2>
           <p className="max-w-3xl mx-auto mt-4 text-lg text-slate-300">
            {t('how_it_works_why_subtitle')}
          </p>
        </motion.div>
        <motion.div
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.1 }}
          className="grid sm:grid-cols-2 lg:grid-cols-4 gap-8 max-w-7xl mx-auto"
        >
          {whyItWorksFeatures.map((feature, index) => (
            <motion.div key={index} variants={itemVariants} className="h-full">
              <Card className="text-center p-8 bg-slate-800/50 border-slate-700 hover:bg-slate-800 transition-colors duration-300 h-full flex flex-col items-center rounded-xl shadow-lg">
                <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-primary/20">
                  <feature.icon className="h-8 w-8 text-primary" />
                </div>
                <CardHeader className="p-0 pt-6 pb-2">
                  <CardTitle className="text-xl font-bold text-white">{feature.title}</CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  <p className="text-slate-300">{feature.description}</p>
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
};

export default WhyItWorksSection;