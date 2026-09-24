import React from 'react';
import { motion } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { useToast } from "@/components/ui/use-toast";
import { Gift, ArrowRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const ReferralProgram = () => {
  const { t } = useTranslation();
  const { toast } = useToast();

  const handleReferralClick = () => {
    toast({
      title: "🚀 Get Ready to Earn!",
      description: "Our referral program is launching soon. You'll be able to share and earn with just one click!",
    });
  };

  return (
    <section id="referral-program" className="py-16 md:py-24 bg-secondary/30">
      <div className="container mx-auto px-4 md:px-6">
        <motion.div
          initial={{ opacity: 0, y: 50 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.3 }}
          transition={{ duration: 0.7 }}
          className="bg-gradient-to-r from-primary to-purple-600 rounded-xl p-8 md:p-12 text-pure-white shadow-2xl flex flex-col md:flex-row items-center justify-between gap-8"
        >
          <div className="flex items-center gap-6">
            <div className="hidden md:block bg-white/20 p-4 rounded-full">
              <Gift className="h-10 w-10 text-white" />
            </div>
            <div>
              <h2 className="text-3xl md:text-4xl font-bold tracking-tight font-heading">Refer 2-3, Get a Free Project Scope</h2>
              <p className="mt-2 text-lg text-white/90">
                Turn your network into value. Get a free project scope worth up to £5000.
              </p>
            </div>
          </div>
          <div className="flex-shrink-0 mt-6 md:mt-0">
            <Button
              onClick={handleReferralClick}
              size="lg"
              className="bg-white text-primary hover:bg-gray-100 shadow-lg hover:shadow-xl"
            >
              {t('referral_button')}
              <ArrowRight className="ml-2 h-5 w-5" />
            </Button>
          </div>
        </motion.div>
      </div>
    </section>
  );
};

export default ReferralProgram;