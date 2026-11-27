
import React from 'react';
import { Helmet } from 'react-helmet';
import { motion } from 'framer-motion';
import ComplaintsForm from '@/components/contact/ComplaintsForm';
import { Mail, Phone, MapPin } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import ContactOptions from '@/components/contact/ContactOptions';

const ContactInfoBar = () => {
    const { t } = useTranslation();
    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.4 }}
            className="bg-card border-t border-b"
        >
            <div className="container mx-auto px-4 md:px-6 py-12">
                <div className="grid md:grid-cols-2 gap-8 text-center max-w-3xl mx-auto">
                    <div className="flex flex-col items-center gap-3">
                        <div className="p-3 bg-primary/10 rounded-full"><Mail className="h-6 w-6 text-primary" /></div>
                        <div>
                            <p className="font-semibold text-foreground">{t('contact_info_inquiries', 'General Inquiries')}</p>
                            <a href="mailto:sales@laskontech.com" className="text-muted-foreground hover:text-primary transition-colors">sales@laskontech.com</a>
                        </div>
                    </div>
                    <div className="flex flex-col items-center gap-3">
                        <div className="p-3 bg-primary/10 rounded-full"><Phone className="h-6 w-6 text-primary" /></div>
                        <div>
                            <p className="font-semibold text-foreground">{t('contact_info_phone', 'Call Us')}</p>
                            <a href="tel:+447466436417" className="text-muted-foreground hover:text-primary transition-colors">+44 7466 436417</a>
                        </div>
                    </div>
                </div>
            </div>
        </motion.div>
    );
}


const ContactPage = () => {
  const { t } = useTranslation();
  return (
    <div>
      <Helmet>
        <title>{t('title_contact', 'Contact Us')} | Pay Per Project</title>
        <meta name="description" content={t('meta_desc_contact', 'Get in touch with PayPerProject for project inquiries, support, or to get an AI-powered project estimate.')} />
      </Helmet>
      
      <ContactOptions />
      
      <ContactInfoBar />

      <section className="py-16 md:py-24 bg-background">
        <div className="container mx-auto px-4 md:px-6">
          <div className="grid lg:grid-cols-5 gap-12 items-start">
             <div className="lg:col-span-3">
               <h3 className="text-3xl font-bold mb-6 text-foreground">{t('contact_complaints_title', 'File a Complaint')}</h3>
               <p className="text-muted-foreground mb-6">{t('contact_complaints_desc', 'If you have any issues or are unsatisfied with our service, please let us know. We take all feedback seriously.')}</p>
               <ComplaintsForm />
            </div>
            <div className="lg:col-span-2 flex flex-col gap-8 mt-8 lg:mt-0">
               <motion.div
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.5, delay: 0.2 }}
                className="bg-card p-6 rounded-lg border shadow-sm"
              >
                <h3 className="text-2xl font-bold mb-6 text-foreground">{t('contact_hours_title', 'Business Hours')}</h3>
                <div className="space-y-3 text-muted-foreground">
                    <p className="flex justify-between"><span className="font-semibold text-foreground">{t('contact_hours_weekdays', 'Weekdays:')}</span> <span>9:00 AM - 6:00 PM</span></p>
                    <p className="flex justify-between"><span className="font-semibold text-foreground">{t('contact_hours_weekends', 'Saturday:')}</span> <span>10:00 AM - 2:00 PM</span></p>
                    <p className="flex justify-between"><span className="font-semibold text-foreground">{t('contact_hours_sunday', 'Sunday:')}</span> <span>{t('contact_hours_closed', 'Closed')}</span></p>
                </div>
              </motion.div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

export default ContactPage;
