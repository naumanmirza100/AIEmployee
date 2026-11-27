import React from 'react';
import { Button } from '@/components/ui/button';
import { useNavigate } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent } from '@/components/ui/card';

const ZeroFees = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <section className="py-16 md:py-24 bg-background">
      <div className="container mx-auto px-4 md:px-6 text-center">
          <div className="inline-block bg-primary/10 text-primary font-semibold py-1 px-3 rounded-full text-sm mb-4">
              {t('zero_fees_tagline')}
          </div>
          <h2 className="text-4xl font-bold text-foreground font-heading">{t('zero_fees_title')}</h2>
          <p className="max-w-2xl mx-auto mt-4 text-lg text-muted-foreground">
              {t('zero_fees_desc')}
          </p>
          <div className="mt-8 max-w-2xl mx-auto">
            <Card className="border-green-300/50 bg-green-500/10 rounded-xl p-4 mb-8 shadow-md">
                <CardContent className="p-2">
                    <p className="text-lg font-bold text-green-700 dark:text-green-300">{t('zero_fees_rate_title')}</p>
                    <p className="text-md text-green-800/80 dark:text-green-300/80">{t('zero_fees_rate_desc')}</p>
                </CardContent>
            </Card>
          </div>
          <div className="mt-8">
              <Button onClick={() => navigate('/start-project')} size="lg">
                  {t('zero_fees_button')}
                  <ArrowRight className="ml-2 h-5 w-5" />
              </Button>
          </div>
      </div>
    </section>
  );
};

export default ZeroFees;