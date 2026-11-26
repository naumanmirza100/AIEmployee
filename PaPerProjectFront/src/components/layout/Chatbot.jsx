import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { MessageSquare, X, Send, Loader2, CheckCircle2 } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { sendPublicMessage } from '@/services/contactService';

// The public site's message box. It was a dummy "AI Assistant" whose Send only said "not implemented"
// (26 Nov 2026, the PM's report). It now sends the message to the team like the contact form does
// (POST /api/contact, listed under contact messages in the admin dashboard), and says so honestly.
const Chatbot = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [form, setForm] = useState({ fullName: '', email: '', message: '' });
  const [sending, setSending] = useState(false);
  const [sentTo, setSentTo] = useState('');
  const [error, setError] = useState('');

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSend = async (e) => {
    e.preventDefault();
    setError('');
    setSending(true);
    try {
      const res = await sendPublicMessage({ fullName: form.fullName.trim(), email: form.email.trim(), message: form.message.trim() });
      setSentTo(form.email.trim());
      setForm({ fullName: '', email: '', message: '' });
    } catch (err) {
      setError("Your message couldn't be sent. Please try again, or email info@payperproject.com.");
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      <div className="fixed bottom-6 right-6 z-50">
        <AnimatePresence>
          {!isOpen && (
            <motion.div
              initial={{ opacity: 0, scale: 0 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0 }}
              transition={{ duration: 0.3 }}
            >
              <Button
                size="lg"
                aria-label="Message us"
                className="rounded-full shadow-lg hover:shadow-xl transition-all duration-300 transform hover:scale-105 w-16 h-16"
                onClick={() => setIsOpen(true)}
              >
                <MessageSquare className="h-8 w-8" />
              </Button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 50, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 50, scale: 0.9 }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
            className="fixed bottom-6 right-6 z-50 w-[calc(100vw-2rem)] max-w-sm max-h-[85vh] bg-card border rounded-2xl shadow-2xl flex flex-col"
            role="dialog"
            aria-label="Message us"
          >
            <header className="flex items-center justify-between p-4 border-b">
              <h3 className="text-lg font-bold">Message us</h3>
              <Button variant="ghost" size="icon" aria-label="Close" onClick={() => setIsOpen(false)}>
                <X className="h-5 w-5" />
              </Button>
            </header>
            <div className="flex-grow p-4 overflow-y-auto">
              {sentTo ? (
                <div className="flex flex-col items-center text-center gap-3 py-6">
                  <CheckCircle2 className="h-10 w-10 text-emerald-600 dark:text-emerald-400" />
                  <p className="font-semibold text-foreground">Thanks, your message was sent.</p>
                  <p className="text-sm text-muted-foreground">We'll reply to {sentTo}.</p>
                  <Button variant="outline" size="sm" onClick={() => setSentTo('')}>Send another message</Button>
                </div>
              ) : (
                <form id="site-message-form" onSubmit={handleSend} className="flex flex-col gap-3">
                  <p className="text-sm text-muted-foreground">
                    Have a question about a project or our AI employees? Send us a message and we'll reply by email.
                  </p>
                  <Input id="site-message-name" aria-label="Your name" placeholder="Your name" value={form.fullName} onChange={set('fullName')} required maxLength={255} />
                  <Input id="site-message-email" aria-label="Your email" type="email" placeholder="you@company.com" value={form.email} onChange={set('email')} required />
                  <Textarea id="site-message-text" aria-label="Your message" placeholder="How can we help?" rows={4} value={form.message} onChange={set('message')} required maxLength={5000} />
                  {error && <p className="text-sm text-red-600 dark:text-red-400" role="alert">{error}</p>}
                  <Button type="submit" disabled={sending} className="self-end">
                    {sending ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Send className="h-4 w-4 mr-2" />}
                    {sending ? 'Sending…' : 'Send'}
                  </Button>
                </form>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
};

export default Chatbot;
