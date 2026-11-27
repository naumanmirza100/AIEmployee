import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Send, BrainCircuit, AlertCircle } from 'lucide-react';
import { useToast } from "@/components/ui/use-toast";
import { useTranslation, Trans } from 'react-i18next';
import { sendPublicMessage } from '@/services/contactService';

const ComplaintsForm = () => {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [captcha, setCaptcha] = useState({ num1: 0, num2: 0, answer: '' });
  const [captchaError, setCaptchaError] = useState('');
  const [sending, setSending] = useState(false);

  const generateCaptcha = () => {
    const num1 = Math.floor(Math.random() * 10) + 1;
    const num2 = Math.floor(Math.random() * 10) + 1;
    setCaptcha({ num1, num2, answer: '' });
  };

  useEffect(() => {
    generateCaptcha();
  }, []);

  // It used to say "Complaint Submitted" and send nothing (26 Nov 2026, the PM's report). It now saves the message
  // for the team (POST /api/contact, shown under contact messages in the admin dashboard, titled "Complaint").
  const handleSubmit = async (e) => {
    e.preventDefault();
    const correctAnswer = captcha.num1 + captcha.num2;
    if (parseInt(captcha.answer, 10) !== correctAnswer) {
      setCaptchaError(t('complaints_captcha_error'));
      generateCaptcha();
      return;
    }

    setCaptchaError('');
    const formEl = e.target;
    const data = new FormData(formEl);
    setSending(true);
    try {
      const res = await sendPublicMessage({
        fullName: String(data.get('complaintName') || '').trim(),
        email: String(data.get('complaintEmail') || '').trim(),
        projectTitle: 'Complaint',
        message: String(data.get('complaintMessage') || '').trim(),
      });
      toast({
        title: "✅ Complaint Submitted",
        description: "Thank you for your message. We will review it and get back to you if necessary.",
        variant: "default",
      });
      formEl.reset();
      generateCaptcha();
    } catch (err) {
      toast({
        title: "Your complaint couldn't be sent",
        description: "Please try again, or email sales@laskontech.com.",
        variant: "destructive",
      });
    } finally {
      setSending(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.2 }}
      className="h-full"
    >
      <Card className="h-full flex flex-col shadow-xl border-destructive/20 rounded-2xl bg-card">
        <CardHeader>
          <div className="flex items-center gap-3">
            <AlertCircle className="h-8 w-8 text-destructive" />
            <CardTitle className="text-2xl md:text-3xl font-bold text-foreground">{t('complaints_title')}</CardTitle>
          </div>
          <CardDescription>
            <Trans i18nKey="complaints_desc">
              Please use this form to submit a complaint, or email <a href="mailto:sales@laskontech.com" className="font-semibold text-destructive hover:underline">sales@laskontech.com</a>.
            </Trans>
          </CardDescription>
        </CardHeader>
        <CardContent className="flex-grow flex flex-col">
          <form onSubmit={handleSubmit} className="space-y-6 flex-grow flex flex-col">
            <div className="flex-grow space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <Label htmlFor="complaint-name">{t('complaints_name_label')} <span className="text-destructive">*</span></Label>
                  <Input id="complaint-name" name="complaintName" type="text" placeholder="John Doe" className="mt-1" required maxLength={255} />
                </div>
                <div>
                  <Label htmlFor="complaint-email">{t('complaints_email_label')} <span className="text-destructive">*</span></Label>
                  <Input id="complaint-email" name="complaintEmail" type="email" placeholder="you@company.com" className="mt-1" required />
                </div>
              </div>
              <div>
                <Label htmlFor="complaint-message">{t('complaints_message_label')} <span className="text-destructive">*</span></Label>
                <textarea id="complaint-message" name="complaintMessage" placeholder="Please describe the issue in detail..." className="mt-1 flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 min-h-[120px]" required />
              </div>
              <div className="space-y-2 pt-2">
                <Label htmlFor="complaint-captcha" className="flex items-center gap-2">
                  <BrainCircuit className="h-5 w-5 text-destructive" />
                  {t('complaints_captcha_label', { num1: captcha.num1, num2: captcha.num2 })} <span className="text-destructive">*</span>
                </Label>
                <Input 
                  id="complaint-captcha" 
                  type="number" 
                  value={captcha.answer}
                  onChange={(e) => setCaptcha({ ...captcha, answer: e.target.value })}
                  placeholder={t('contact_form_captcha_answer_placeholder')}
                  required 
                  className="w-full md:w-1/2"
                />
                {captchaError && <p className="text-sm text-destructive">{captchaError}</p>}
              </div>
            </div>
            <div className="flex justify-end pt-2">
              <Button type="submit" disabled={sending} variant="destructive" size="lg" className="font-bold w-full md:w-auto shadow-lg shadow-destructive/30 hover:shadow-xl hover:shadow-destructive/40 transition-shadow">
                {t('complaints_button')} <Send className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </motion.div>
  );
};

export default ComplaintsForm;