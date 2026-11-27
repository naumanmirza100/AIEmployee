import React, { useState } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { DatePicker } from '@/components/ui/date-picker';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { useToast } from "@/components/ui/use-toast";
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Wand2, FileText, Users, Calendar, Wallet, Globe, Shield, BarChart, GitBranch, CheckCircle, Lock } from 'lucide-react';

const FormSection = ({ title, description, children }) => (
  <motion.div
    className="space-y-6"
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.5 }}
  >
    <div className="pb-4 border-b border-border">
      <h3 className="text-xl font-semibold font-heading text-foreground">{title}</h3>
      {description && <p className="text-sm text-muted-foreground mt-1">{description}</p>}
    </div>
    <div className="space-y-8">{children}</div>
  </motion.div>
);

const TalentRequestForm = () => {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { register, handleSubmit, control, formState: { errors } } = useForm();

  const onSubmit = (data) => {
    console.log(data);
    toast({
      title: "🚀 Request Sent!",
      description: "Our AI is analyzing your request to create an instant shortlist. We'll be in touch shortly.",
    });
  };

  const handleGenerateJD = () => {
    toast({
      title: "✨ AI Job Description Generated!",
      description: "We've created a draft job description based on your summary. Feel free to edit it.",
    });
  };

  return (
    <Card className="w-full max-w-4xl mx-auto shadow-2xl rounded-2xl overflow-hidden">
      <CardHeader className="bg-secondary/30 p-6">
        <CardTitle className="text-2xl font-bold text-foreground">Request Vetted Talent</CardTitle>
        <CardDescription>Fill out the form below, and our AI will instantly start shortlisting the perfect team for your project.</CardDescription>
      </CardHeader>
      <CardContent className="p-6 sm:p-8">
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-12">
          <FormSection title="Job / Talent Request" description="This information powers our instant shortlisting AI.">
            <div className="space-y-2">
              <Label htmlFor="roleSummary">Role Summary & Objectives *</Label>
              <Textarea
                id="roleSummary"
                placeholder="Describe the main responsibilities, key objectives, and what success looks like for this role..."
                className={`min-h-[120px] ${errors.roleSummary ? 'border-destructive' : ''}`}
                {...register("roleSummary", { required: "Role summary is required." })}
              />
              {errors.roleSummary && <p className="text-sm font-medium text-destructive">{errors.roleSummary.message}</p>}
              <div className="flex justify-end mt-2">
                <Button type="button" variant="outline" size="sm" onClick={handleGenerateJD}>
                  <Wand2 className="mr-2 h-4 w-4" />
                  AI-Generate Job Description
                </Button>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <Label htmlFor="mustHaveSkills">Must-Have Skills *</Label>
                <Input id="mustHaveSkills" placeholder="e.g., React, Node.js, AWS" {...register("mustHaveSkills", { required: "Must-have skills are required." })} className={errors.mustHaveSkills ? 'border-destructive' : ''} />
                {errors.mustHaveSkills && <p className="text-sm font-medium text-destructive">{errors.mustHaveSkills.message}</p>}
              </div>
              <div className="space-y-2">
                <Label htmlFor="niceToHaveSkills">Nice-to-Have Skills</Label>
                <Input id="niceToHaveSkills" placeholder="e.g., GraphQL, Kubernetes" {...register("niceToHaveSkills")} />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="space-y-2">
                <Label htmlFor="level">Seniority Level *</Label>
                <Controller name="level" control={control} rules={{ required: "Seniority level is required." }} render={({ field }) => (
                  <Select onValueChange={field.onChange} defaultValue={field.value}>
                    <SelectTrigger className={errors.level ? 'border-destructive' : ''}><SelectValue placeholder="Select level" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="mid">Mid-level</SelectItem>
                      <SelectItem value="senior">Senior</SelectItem>
                      <SelectItem value="lead">Lead / Principal</SelectItem>
                      <SelectItem value="team">Full Team</SelectItem>
                    </SelectContent>
                  </Select>
                )} />
                {errors.level && <p className="text-sm font-medium text-destructive">{errors.level.message}</p>}
              </div>
              <div className="space-y-2">
                <Label htmlFor="headcount">Headcount *</Label>
                <Input id="headcount" type="number" placeholder="e.g., 2" {...register("headcount", { required: "Headcount is required.", valueAsNumber: true })} className={errors.headcount ? 'border-destructive' : ''} />
                {errors.headcount && <p className="text-sm font-medium text-destructive">{errors.headcount.message}</p>}
              </div>
              <div className="space-y-2">
                <Label htmlFor="startDate">Target Start Date *</Label>
                <Controller name="startDate" control={control} rules={{ required: "Start date is required." }} render={({ field }) => <DatePicker date={field.value} setDate={field.onChange} placeholder="Select a date" />} />
                {errors.startDate && <p className="text-sm font-medium text-destructive">{errors.startDate.message}</p>}
              </div>
            </div>
          </FormSection>

          <FormSection title="Sourcing & Budget">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <Label htmlFor="sourcingModel">Region / Time-Zone (Sourcing Model) *</Label>
                <Controller name="sourcingModel" control={control} rules={{ required: "Sourcing model is required." }} render={({ field }) => (
                  <Select onValueChange={field.onChange} defaultValue={field.value}>
                    <SelectTrigger className={errors.sourcingModel ? 'border-destructive' : ''}><SelectValue placeholder="Select sourcing model" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="onshore">Onshore (Same Country)</SelectItem>
                      <SelectItem value="nearshore">Nearshore (Similar Time-Zone)</SelectItem>
                      <SelectItem value="offshore">Offshore (Global)</SelectItem>
                    </SelectContent>
                  </Select>
                )} />
                {errors.sourcingModel && <p className="text-sm font-medium text-destructive">{errors.sourcingModel.message}</p>}
              </div>
              <div className="space-y-2">
                <Label htmlFor="budget">Budget Band (Optional, per month)</Label>
                <div className="relative">
                  <Wallet className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input id="budget" placeholder="e.g., $10,000 - $15,000" className="pl-10" {...register("budget")} />
                </div>
              </div>
            </div>
          </FormSection>

          <FormSection title="Security & Compliance Needs">
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">Select all that apply to your project.</p>
              <div className="flex items-center space-x-2">
                <Checkbox id="pii" {...register("compliance.pii")} />
                <Label htmlFor="pii" className="font-normal">Handles PII / PHI data</Label>
              </div>
              <div className="flex items-center space-x-2">
                <Checkbox id="soc2" {...register("compliance.soc2")} />
                <Label htmlFor="soc2" className="font-normal">SOC 2 Compliance Required</Label>
              </div>
              <div className="flex items-center space-x-2">
                <Checkbox id="iso" {...register("compliance.iso")} />
                <Label htmlFor="iso" className="font-normal">ISO 27001 Compliance Required</Label>
              </div>
            </div>
          </FormSection>

          <FormSection title="Always-on Compliance & Trust" description="We handle compliance so you can focus on building.">
            <div className="space-y-4">
              <div className="flex items-start gap-3 p-4 bg-secondary/30 rounded-lg">
                <CheckCircle className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" />
                <div>
                  <h4 className="font-semibold text-foreground">Automated KYC/KYB & Sanctions Screening</h4>
                  <p className="text-sm text-muted-foreground">We screen all companies and beneficial owners against global watchlists, aligned with the OFAC Framework for Sanctions Compliance.</p>
                </div>
              </div>
              <div className="flex items-start gap-3 p-4 bg-secondary/30 rounded-lg">
                <CheckCircle className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" />
                <div>
                  <h4 className="font-semibold text-foreground">NIST-Aligned Identity Verification</h4>
                  <p className="text-sm text-muted-foreground">At the offer stage, all candidates undergo digital identity and liveness checks (NIST 800-63 IAL2/AAL2) to prevent fraud.</p>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-4 p-4 bg-blue-500/10 rounded-lg border border-blue-500/20">
                <Lock className="h-8 w-8 text-blue-500 flex-shrink-0" />
                <p className="text-sm text-blue-200">Your request is confidential. Talent identities are only revealed after an NDA is executed.</p>
            </div>
          </FormSection>

          <div className="flex justify-end pt-6 border-t border-border">
            <Button type="submit" size="lg" className="font-bold w-full sm:w-auto">
              Get My Instant Shortlist
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
};

export default TalentRequestForm;