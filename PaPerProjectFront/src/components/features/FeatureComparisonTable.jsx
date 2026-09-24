import React from 'react';
import { motion } from 'framer-motion';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CheckCircle2, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const featureComparisonData = [
  { feature: 'Outcome-Based Scope Suggestions', payPerProject: true, traditional: false },
  { feature: 'Client Growth Mode (Post-Delivery Support)', payPerProject: true, traditional: false },
  { feature: 'Live Project Health Dashboard', payPerProject: true, traditional: false },
  { feature: 'Auto-IP Transfer & Digital Vault', payPerProject: true, traditional: false },
  { feature: 'One-Click Project Expansion', payPerProject: true, traditional: false },
  { feature: 'White-Labeled Client Portal for Agencies', payPerProject: true, traditional: false },
  { feature: '“Build With Me” Mode (Live Sessions)', payPerProject: true, traditional: true },
  { feature: 'Results Reporting / Impact Snapshot', payPerProject: true, traditional: false },
  { feature: 'Flexible Delivery Format Picker', payPerProject: true, traditional: true },
  { feature: 'Private File Vault with Lifetime Access', payPerProject: true, traditional: false },
  { feature: 'Smart SLA Breach Alerts + Make-Good Credit', payPerProject: true, traditional: false },
  { feature: 'Brief Clone & Launch Again', payPerProject: true, traditional: false },
  { feature: 'Unbeatable B2B Value', payPerProject: true, traditional: false },
  { feature: '15% Future Project Credits', payPerProject: true, traditional: false },
  { feature: 'Launch Now, Pay Later Option', payPerProject: true, traditional: false },
  { feature: 'Creator Miles Rewards Program', payPerProject: true, traditional: false },
  { feature: '"Build in Public" Discount', payPerProject: true, traditional: false },
  { feature: 'Project Insurance Guarantee', payPerProject: true, traditional: false },
];

const Check = () => <CheckCircle2 className="h-5 w-5 text-emerald-500 mx-auto" />;
const Cross = () => <XCircle className="h-5 w-5 text-rose-500 mx-auto" />;

const FeatureComparisonTable = () => {
  const { t } = useTranslation();
  return (
    <section className="py-16 md:py-24 bg-background">
      <div className="container mx-auto px-4 md:px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.3 }}
          className="text-center mb-12"
        >
          <h2 className="text-3xl md:text-5xl font-extrabold text-foreground tracking-tight">{t('feature_comparison_title')}</h2>
          <p className="max-w-3xl mx-auto mt-4 text-lg text-muted-foreground">
            {t('feature_comparison_subtitle')}
          </p>
        </motion.div>
        
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.3 }}
          className="hidden md:block bg-card rounded-2xl shadow-2xl shadow-slate-200/60 overflow-hidden border"
        >
          <Table className="min-w-full divide-y">
            <TableHeader className="bg-secondary/40">
              <TableRow>
                <TableHead className="py-5 px-6 text-left text-xs font-bold text-muted-foreground uppercase tracking-wider w-1/2">
                  {t('feature_comparison_feature')}
                </TableHead>
                <TableHead className="py-5 px-6 text-center text-xs font-bold text-pure-white uppercase tracking-wider w-1/4 bg-gradient-to-br from-primary to-purple-600">
                  {t('feature_comparison_ppp')}
                </TableHead>
                <TableHead className="py-5 px-6 text-center text-xs font-bold text-muted-foreground uppercase tracking-wider w-1/4">
                  {t('feature_comparison_traditional')}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody className="divide-y">
              {featureComparisonData.map((row, index) => (
                <TableRow key={index} className="hover:bg-secondary/30 transition-colors duration-200">
                  <TableCell className="py-5 px-6 font-semibold text-foreground text-base">{row.feature}</TableCell>
                  <TableCell className="py-5 px-6 text-center text-foreground bg-primary/5 border-l border-r border-primary/10">
                    {row.payPerProject ? <Check /> : <Cross />}
                  </TableCell>
                  <TableCell className="py-5 px-6 text-center text-muted-foreground">
                    {row.traditional ? <Check /> : <Cross />}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </motion.div>

        <div className="md:hidden space-y-4">
          {featureComparisonData.map((row, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.2 }}
              transition={{ delay: index * 0.05 }}
              className="bg-card rounded-xl shadow-lg border overflow-hidden"
            >
              <div className="p-4 bg-secondary/40 border-b">
                <h3 className="font-bold text-foreground text-base">{row.feature}</h3>
              </div>
              <div className="p-4 space-y-3">
                <div className="flex justify-between items-center bg-primary/10 p-3 rounded-lg">
                  <span className="font-semibold text-primary">{t('feature_comparison_ppp')}</span>
                  {row.payPerProject ? <Check /> : <Cross />}
                </div>
                <div className="flex justify-between items-center bg-secondary/40 p-3 rounded-lg">
                  <span className="font-semibold text-muted-foreground">{t('feature_comparison_traditional')}</span>
                  {row.traditional ? <Check /> : <Cross />}
                </div>
              </div>
            </motion.div>
          ))}
        </div>

      </div>
    </section>
  );
};

export default FeatureComparisonTable;