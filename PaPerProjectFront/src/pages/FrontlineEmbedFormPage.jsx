import React, { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { API_BASE_URL } from '@/config/apiConfig';
import { Loader2, Send, CheckCircle } from 'lucide-react';

/**
 * Embeddable web form. Load in iframe: /embed/form?key=WIDGET_KEY
 * Submit creates a ticket via public API. Optional: "Ask a question" shows answer inline.
 */
export default function FrontlineEmbedFormPage() {
  const [searchParams] = useSearchParams();
  const widgetKey = searchParams.get('key') || searchParams.get('widget_key') || '';
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [question, setQuestion] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [askLoading, setAskLoading] = useState(false);
  const [answer, setAnswer] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!widgetKey) {
      setSubmitError('Invalid embed: missing key.');
      return;
    }
    setSubmitError('');
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE_URL}/frontline/public/submit/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          widget_key: widgetKey,
          name: name.trim(),
          email: email.trim(),
          message: message.trim(),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || data.error || 'Submit failed');
      setSubmitSuccess(true);
      setName('');
      setEmail('');
      setMessage('');
    } catch (err) {
      setSubmitError(err.message || 'Failed to submit');
    } finally {
      setSubmitting(false);
    }
  };

  const handleAsk = async (e) => {
    e.preventDefault();
    const q = question.trim();
    if (!q || !widgetKey) return;
    setAnswer('');
    setAskLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/frontline/public/qa/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, widget_key: widgetKey }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || data.error || 'Request failed');
      setAnswer(data?.data?.answer ?? data?.answer ?? 'No answer available.');
    } catch (err) {
      setAnswer(`Sorry, something went wrong: ${err.message}`);
    } finally {
      setAskLoading(false);
    }
  };

  if (!widgetKey) {
    return (
      <div className="min-h-[320px] flex items-center justify-center bg-muted/30 p-4">
        <p className="text-sm text-muted-foreground">Invalid embed. Missing widget key.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col max-w-md mx-auto min-h-[min(100vh,560px)] bg-background border border-border rounded-lg shadow-lg overflow-hidden">
      <div className="shrink-0 px-4 py-3 border-b bg-muted/40">
        <h2 className="text-sm font-semibold">Contact us</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Send a message or ask a quick question below.</p>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {submitSuccess ? (
          <div className="flex items-center gap-2 text-green-600 dark:text-green-400 text-sm">
            <CheckCircle className="h-5 w-5 shrink-0" />
            <span>Thank you. We&apos;ll get back to you soon.</span>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
                className="w-full rounded-lg border bg-background px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="your@email.com"
                className="w-full rounded-lg border bg-background px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">Message</label>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="How can we help?"
                rows={4}
                required
                className="w-full rounded-lg border bg-background px-3 py-2 text-sm resize-none"
              />
            </div>
            {submitError && <p className="text-xs text-destructive">{submitError}</p>}
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-lg bg-primary text-primary-foreground py-2.5 text-sm font-medium flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              {submitting ? 'Sending...' : 'Send message'}
            </button>
          </form>
        )}

        <hr className="border-border" />
        <div>
          <h3 className="text-xs font-semibold text-muted-foreground mb-2">Quick question</h3>
          <form onSubmit={handleAsk} className="flex gap-2">
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask a question..."
              disabled={askLoading}
              className="flex-1 min-w-0 rounded-lg border bg-background px-3 py-2 text-sm"
            />
            <button
              type="submit"
              disabled={askLoading}
              className="shrink-0 rounded-lg bg-muted px-3 py-2 text-sm font-medium hover:bg-muted/80 disabled:opacity-50"
            >
              {askLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Ask'}
            </button>
          </form>
          {answer && (
            <div className="mt-2 p-3 rounded-lg bg-muted border text-sm whitespace-pre-wrap">{answer}</div>
          )}
        </div>
      </div>
    </div>
  );
}
