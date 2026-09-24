import React from 'react';
import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { ArrowRight, HelpCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const QuizCTASection = () => {
  const { t } = useTranslation();
  return (
    <section className="py-20 md:py-28 bg-background">
      <div className="container mx-auto px-4 md:px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.3 }}
          className="bg-card rounded-xl shadow-xl border p-8 md:p-12 flex flex-col md:flex-row items-center justify-between gap-8"
        >
          <div className="flex-shrink-0">
            <div className="flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-br from-primary to-purple-600 text-pure-white shadow-lg">
              <HelpCircle className="h-10 w-10" />
            </div>
          </div>
          <div className="text-center md:text-left flex-grow">
            <h2 className="text-2xl md:text-3xl font-bold text-foreground">{t('how_it_works_quiz_cta_title')}</h2>
            <p className="mt-2 text-lg text-muted-foreground">
              {t('how_it_works_quiz_cta_subtitle')}
            </p>
          </div>
          <div className="flex-shrink-0">
            <Button asChild size="lg">
              <Link to="/quiz">
                {t('how_it_works_quiz_cta_button')}
                <ArrowRight className="ml-3 h-5 w-5" />
              </Link>
            </Button>
          </div>
        </motion.div>
      </div>
    </section>
  );
};

export default QuizCTASection;