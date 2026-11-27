import React from 'react';
import { Link } from 'react-router-dom';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Star, CheckCircle, XCircle, ArrowRight, UserCircle, MinusCircle } from 'lucide-react';
import { useTranslation, Trans } from 'react-i18next';

const SocialProof = () => {
  const { t, i18n } = useTranslation();
  const comparisonData = [
    { feature: t('social_proof_compare_feature_matching'), us: t('social_proof_compare_value_us_matching'), others: t('social_proof_compare_value_others_matching'), freelancer: t('social_proof_compare_value_freelancer_matching') },
    { feature: t('social_proof_compare_feature_pricing'), us: t('social_proof_compare_value_us_pricing'), others: t('social_proof_compare_value_others_pricing'), freelancer: t('social_proof_compare_value_freelancer_pricing') },
    { feature: t('social_proof_compare_feature_pm'), us: t('social_proof_compare_value_us_pm'), others: t('social_proof_compare_value_others_pm'), freelancer: t('social_proof_compare_value_freelancer_pm') },
    { feature: t('social_proof_compare_feature_qa'), us: t('social_proof_compare_value_us_qa'), others: t('social_proof_compare_value_others_qa'), freelancer: t('social_proof_compare_value_freelancer_qa') },
    { feature: t('social_proof_compare_feature_fees'), us: t('social_proof_compare_value_us_fees'), others: t('social_proof_compare_value_others_fees'), freelancer: t('social_proof_compare_value_freelancer_fees') },
    { feature: t('social_proof_compare_feature_support'), us: t('social_proof_compare_value_us_support'), others: t('social_proof_compare_value_others_support'), freelancer: t('social_proof_compare_value_freelancer_support') },
    { feature: t('social_proof_compare_feature_vetting'), us: t('social_proof_compare_value_us_vetting'), others: t('social_proof_compare_value_others_vetting'), freelancer: t('social_proof_compare_value_freelancer_vetting') },
    { feature: t('social_proof_compare_feature_accountability'), us: t('social_proof_compare_value_us_accountability'), others: t('social_proof_compare_value_others_accountability'), freelancer: t('social_proof_compare_value_freelancer_accountability') },
    { feature: t('social_proof_compare_feature_scalability'), us: t('social_proof_compare_value_us_scalability'), others: t('social_proof_compare_value_others_scalability'), freelancer: t('social_proof_compare_value_freelancer_scalability') },
    { feature: t('social_proof_compare_feature_guarantee'), us: t('social_proof_compare_value_us_guarantee'), others: t('social_proof_compare_value_others_guarantee'), freelancer: t('social_proof_compare_value_freelancer_guarantee') },
  ];

  



  return (
    <section className="py-16 md:py-24 bg-secondary/30">
      <div className="container mx-auto px-4 md:px-6">
        <div className="space-y-20">
          {/* The logo wall (Google, Microsoft, Amazon… shown as clients) and the reviews, which were generated from
              random names, are gone (27 Nov 2026): neither was real. The comparison below stays. */}
          <div className="max-w-6xl mx-auto">
            <h3 className="text-3xl font-bold text-center mb-8 font-heading">{t('social_proof_compare_title')}</h3>
            <Card className="shadow-lg overflow-hidden border rounded-xl">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-secondary/40 hover:bg-secondary/40">
                      <TableHead className="w-[250px] text-base font-semibold text-foreground">{t('social_proof_compare_feature')}</TableHead>
                      <TableHead className="text-center text-gradient font-bold text-base">{t('social_proof_compare_ppp')}</TableHead>
                      <TableHead className="text-center text-base font-semibold text-foreground">{t('social_proof_compare_freelancers')}</TableHead>
                      <TableHead className="text-center text-base font-semibold text-foreground">{t('social_proof_compare_others')}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {comparisonData.map((row, index) => (
                      <TableRow key={index} className="hover:bg-secondary/20">
                        <TableCell className="font-semibold text-foreground">{row.feature}</TableCell>
                        <TableCell className="text-center">
                          <span className="flex items-center justify-center gap-2 font-semibold text-green-600">
                            <CheckCircle className="h-5 w-5 shrink-0" /> {row.us}
                          </span>
                        </TableCell>
                        <TableCell className="text-center">
                          <span className="flex items-center justify-center gap-2 text-muted-foreground">
                            <MinusCircle className="h-5 w-5 shrink-0" /> {row.freelancer}
                          </span>
                        </TableCell>
                        <TableCell className="text-center">
                          <span className="flex items-center justify-center gap-2 text-muted-foreground">
                            <XCircle className="h-5 w-5 shrink-0" /> {row.others}
                          </span>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </section>
  );
};

export default SocialProof;