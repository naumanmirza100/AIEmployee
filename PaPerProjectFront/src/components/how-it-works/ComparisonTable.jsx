import React from 'react';
import { motion } from 'framer-motion';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CheckCircle2, XCircle, MinusCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const comparisonData = [
  {
    feature: "Matching Process",
    payPerProject: "Instant, AI-powered matching to vetted teams",
    freelancers: "Manual search, interviews, and screening",
    marketplaces: "Bidding wars and endless profile reviews",
  },
  {
    feature: "Pricing Model",
    payPerProject: "Fixed, upfront price. No surprises.",
    freelancers: "Hourly rates, prone to scope creep",
    marketplaces: "Hourly or fixed, but with hidden fees",
  },
  {
    feature: "Project Management",
    payPerProject: "Dedicated PM included",
    freelancers: "Client manages everything",
    marketplaces: "Client manages, platform offers minimal tools",
  },
  {
    feature: "Quality Assurance",
    payPerProject: "Internal QA team on every project",
    freelancers: "Self-policed, quality varies wildly",
    marketplaces: "Relies on reviews, no proactive QA",
  },
  {
    feature: "Client Platform Fees",
    payPerProject: "0% - All-inclusive price",
    freelancers: "N/A (but has other overheads)",
    marketplaces: "5-20% on top of project cost",
  },
  {
    feature: "Support",
    payPerProject: "Dedicated project & success manager",
    freelancers: "Directly with freelancer only",
    marketplaces: "Generic platform customer service",
  },
  {
    feature: "Vetting",
    payPerProject: "Rigorous 2% acceptance rate for teams",
    freelancers: "Client's responsibility to vet",
    marketplaces: "Basic identity checks, skill tests optional",
  },
  {
    feature: "Accountability",
    payPerProject: "Single point of contact, we own the outcome",
    freelancers: "Individual accountability, can disappear",
    marketplaces: "Limited to platform dispute resolution",
  },
  {
    feature: "Scalability",
    payPerProject: "Seamlessly scale team size on demand",
    freelancers: "Difficult, requires new hiring process",
    marketplaces: "Difficult, requires multiple new hires",
  },
  {
    feature: "Guarantee",
    payPerProject: "100% Project Success Guarantee",
    freelancers: "No guarantee, high risk",
    marketplaces: "Basic payment protection only",
  },
];

const Check = () => <CheckCircle2 className="h-6 w-6 text-emerald-500 mx-auto" />;
const Cross = () => <XCircle className="h-6 w-6 text-rose-500 mx-auto" />;
const Neutral = () => <MinusCircle className="h-6 w-6 text-slate-400 mx-auto" />;

const ComparisonTable = () => {
  const { t } = useTranslation();
  return (
    <section className="py-20 md:py-28 bg-background">
      <div className="container mx-auto px-4 md:px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.3 }}
          className="text-center mb-16"
        >
          <h2 className="text-4xl md:text-5xl font-bold text-foreground font-heading">{t('how_it_works_comparison_title')}</h2>
          <p className="max-w-3xl mx-auto mt-4 text-lg text-muted-foreground">
            {t('how_it_works_comparison_subtitle')}
          </p>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.3 }}
          className="bg-card rounded-xl shadow-2xl overflow-hidden border"
        >
          <Table className="min-w-full divide-y">
            <TableHeader className="bg-secondary/40">
              <TableRow>
                <TableHead className="py-5 px-6 text-left text-xs font-bold text-muted-foreground uppercase tracking-wider w-[25%]">Feature</TableHead>
                <TableHead className="py-5 px-6 text-center text-xs font-bold text-pure-white uppercase tracking-wider w-[25%] bg-gradient-to-br from-primary to-purple-600">Pay Per Project</TableHead>
                <TableHead className="py-5 px-6 text-center text-xs font-bold text-muted-foreground uppercase tracking-wider w-[25%]">Hiring Freelancers</TableHead>
                <TableHead className="py-5 px-6 text-center text-xs font-bold text-muted-foreground uppercase tracking-wider w-[25%]">Agency / Marketplace</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody className="divide-y">
              {comparisonData.map((row, index) => (
                <TableRow key={index} className="hover:bg-secondary/30 transition-colors duration-200">
                  <TableCell className="py-5 px-6 font-semibold text-foreground text-base">{row.feature}</TableCell>
                  <TableCell className="py-5 px-6 text-center text-foreground bg-primary/5 border-l border-r border-primary/10">
                    <div className="flex flex-col items-center justify-center h-full">
                      <Check />
                      <span className="text-sm text-muted-foreground mt-2">{row.payPerProject}</span>
                    </div>
                  </TableCell>
                  <TableCell className="py-5 px-6 text-center text-muted-foreground">
                     <div className="flex flex-col items-center justify-center h-full">
                      <Cross />
                      <span className="text-sm mt-2">{row.freelancers}</span>
                    </div>
                  </TableCell>
                  <TableCell className="py-5 px-6 text-center text-muted-foreground">
                     <div className="flex flex-col items-center justify-center h-full">
                      <Neutral />
                      <span className="text-sm mt-2">{row.marketplaces}</span>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </motion.div>
      </div>
    </section>
  );
};

export default ComparisonTable;