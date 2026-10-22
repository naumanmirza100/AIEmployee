import React, { useState, useRef, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { API_BASE_URL } from '@/config/apiConfig';
import { withParentOrigin } from '@/utils/embedOrigin';
import { Send, Loader2, MessageCircle } from 'lucide-react';

/**
 * Embeddable chat widget page. Load in iframe: /embed/chat?key=WIDGET_KEY
 * No auth; uses public API with widget_key.
 *
 * It reads the company's saved widget settings (colours, font, pre-chat form, opening
 * hours) from the public config address. It used to read none of them, so the colours a
 * company chose never reached its chat, and a visitor who asked for a person left no
 * address for the reply.
 */
const HEX = /^#[0-9a-fA-F]{3,8}$/;
const colour = (value) => (typeof value === 'string' && HEX.test(value) ? value : null);
const MAX_HISTORY = 10;

// The AI answers in markdown. Shown as plain text, its ** and ## appeared as they were.
const markdownComponents = {
  a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" className="underline" />,
  p: ({ node, ...props }) => <p {...props} className="mb-2 last:mb-0" />,
  ul: ({ node, ...props }) => <ul {...props} className="list-disc pl-5 mb-2 last:mb-0 space-y-0.5" />,
  ol: ({ node, ...props }) => <ol {...props} className="list-decimal pl-5 mb-2 last:mb-0 space-y-0.5" />,
  h1: ({ node, ...props }) => <p {...props} className="font-semibold mb-1" />,
  h2: ({ node, ...props }) => <p {...props} className="font-semibold mb-1" />,
  h3: ({ node, ...props }) => <p {...props} className="font-semibold mb-1" />,
  code: ({ node, ...props }) => <code {...props} className="rounded bg-black/10 px-1" />,
};

export default function FrontlineEmbedChatPage() {
  const [searchParams] = useSearchParams();
  const widgetKey = searchParams.get('key') || searchParams.get('widget_key') || '';
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState([]);
  const [error, setError] = useState('');
  const [config, setConfig] = useState(null);
  const [visitor, setVisitor] = useState({ name: '', email: '', phone: '', subject: '' });
  const [introDone, setIntroDone] = useState(false);
  // A hand-off with no address yet: { token } until the visitor leaves one.
  const [askEmail, setAskEmail] = useState(null);
  const [replyEmail, setReplyEmail] = useState('');
  const [savingEmail, setSavingEmail] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, askEmail]);

  useEffect(() => {
    if (!widgetKey) return;
    let gone = false;
    fetch(withParentOrigin(`${API_BASE_URL}/frontline/widget/public-config/?widget_key=${encodeURIComponent(widgetKey)}`))
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => { if (!gone && data?.data) setConfig(data.data); })
      .catch(() => {});
    return () => { gone = true; };
  }, [widgetKey]);

  const theme = config?.theme || {};
  const primary = colour(theme.primary_color);
  const headerBg = colour(theme.header_bg) || primary;
  const headerText = colour(theme.header_text_color) || (headerBg ? '#ffffff' : null);
  const userBubble = colour(theme.bubble_bg_user) || primary;
  const agentBubble = colour(theme.bubble_bg_agent);

  // Tell the page around us (frontline-widget.js) the colour, side and words for its button.
  useEffect(() => {
    if (!config || window.parent === window) return;
    window.parent.postMessage({
      type: 'frontline-widget-theme',
      color: primary,
      position: theme.position === 'bottom-left' ? 'bottom-left' : 'bottom-right',
      launcherText: typeof theme.launcher_text === 'string' ? theme.launcher_text.slice(0, 60) : '',
    }, '*');
  }, [config]); // eslint-disable-line react-hooks/exhaustive-deps

  const preChat = config?.pre_chat_form?.enabled ? (config.pre_chat_form.fields || []) : [];
  const closed = config?.operating_hours?.enabled && config.operating_hours.is_open === false;

  const post = async (path, body) => {
    const res = await fetch(withParentOrigin(`${API_BASE_URL}${path}`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ widget_key: widgetKey, ...body }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.message || data.error || 'Request failed');
    return data;
  };

  const sendQuestion = async (e) => {
    e?.preventDefault();
    const q = question.trim();
    if (!q || !widgetKey) {
      setError(widgetKey ? 'Please enter a question.' : 'Invalid embed: missing key.');
      return;
    }
    setError('');
    const history = messages
      .filter((m) => !m.error && !m.notice)
      .slice(-MAX_HISTORY)
      .map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, { role: 'user', content: q }]);
    setQuestion('');
    setLoading(true);
    try {
      const data = await post('/frontline/public/qa/', {
        question: q,
        history,
        visitor_email: visitor.email.trim(),
        visitor_name: visitor.name.trim(),
      });
      if (data.status === 'closed') {
        setMessages((prev) => [...prev, { role: 'assistant', content: data.message, notice: true }]);
        return;
      }
      const result = data?.data || data || {};
      const answer = result.answer ?? 'No answer available.';
      setMessages((prev) => [...prev, { role: 'assistant', content: answer, hasVerified: !!result.has_verified_info }]);
      if (result.handoff_requested) {
        if (result.handoff_token) {
          setAskEmail({ token: result.handoff_token });
        } else if (visitor.email.trim()) {
          setMessages((prev) => [...prev, {
            role: 'assistant', notice: true,
            content: `A person from our team will reply to ${visitor.email.trim()}.`,
          }]);
        }
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Sorry, something went wrong: ${err.message}`, error: true },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const saveReplyEmail = async (e) => {
    e?.preventDefault();
    const email = replyEmail.trim();
    if (!email || !askEmail) return;
    setSavingEmail(true);
    try {
      const data = await post('/frontline/public/handoff-contact/', {
        handoff_token: askEmail.token, email, name: visitor.name.trim(),
      });
      setVisitor((v) => ({ ...v, email }));
      setAskEmail(null);
      setMessages((prev) => [...prev, { role: 'assistant', notice: true, content: data.message || 'Thank you.' }]);
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingEmail(false);
    }
  };

  if (!widgetKey) {
    return (
      <div className="min-h-[320px] flex items-center justify-center bg-muted/30 p-4">
        <p className="text-sm text-muted-foreground">Invalid embed. Missing widget key.</p>
      </div>
    );
  }

  const frameStyle = {
    fontFamily: theme.font_family || undefined,
    borderRadius: theme.border_radius || undefined,
  };
  const accent = primary ? { background: primary, color: '#ffffff' } : undefined;
  const needsIntro = preChat.length > 0 && !introDone;
  const introValid = !preChat.includes('email') || /\S+@\S+\.\S+/.test(visitor.email);

  return (
    <div className="flex flex-col h-[min(100vh,520px)] bg-background border border-border rounded-lg shadow-lg overflow-hidden" style={frameStyle}>
      {theme.css_overrides ? <style>{theme.css_overrides}</style> : null}
      <div
        className={`shrink-0 px-4 py-3 border-b ${headerBg ? '' : 'bg-muted/40'}`}
        style={headerBg ? { background: headerBg, color: headerText } : undefined}
      >
        <h2 className="text-sm font-semibold flex items-center gap-2">
          <MessageCircle className="h-4 w-4" />
          Ask us anything
        </h2>
        <p className={`text-xs mt-0.5 ${headerBg ? 'opacity-80' : 'text-muted-foreground'}`}>Answers from our knowledge base.</p>
      </div>

      {closed && (
        <div className="shrink-0 px-4 py-2 text-xs bg-amber-50 text-amber-900 border-b border-amber-200">
          {config.operating_hours.offline_message || "We're offline right now."}
        </div>
      )}

      {needsIntro ? (
        <form
          onSubmit={(e) => { e.preventDefault(); if (introValid) setIntroDone(true); }}
          className="flex-1 overflow-y-auto p-4 space-y-3"
        >
          <p className="text-sm text-muted-foreground">Before we start, so we can get back to you:</p>
          {preChat.map((field) => (
            <input
              key={field}
              type={field === 'email' ? 'email' : 'text'}
              required={field === 'email' || field === 'name'}
              placeholder={{ name: 'Your name', email: 'Your email', phone: 'Your phone', subject: 'What is it about?' }[field] || field}
              value={visitor[field] || ''}
              onChange={(e) => setVisitor((v) => ({ ...v, [field]: e.target.value }))}
              className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
          ))}
          <button type="submit" disabled={!introValid}
            className="w-full rounded-lg bg-primary text-primary-foreground py-2 text-sm font-medium disabled:opacity-50" style={accent}>
            Start chatting
          </button>
        </form>
      ) : (
        <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0">
          {messages.length === 0 && (
            <div className="text-center text-muted-foreground text-sm py-8">
              Type your question below and press Send.
            </div>
          )}
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${
                  msg.role === 'user'
                    ? 'bg-primary text-primary-foreground'
                    : msg.error
                      ? 'bg-destructive/10 text-destructive border border-destructive/20'
                      : msg.notice
                        ? 'bg-muted/60 border border-dashed text-muted-foreground'
                        : 'bg-muted border'
                }`}
                style={
                  msg.role === 'user' && userBubble ? { background: userBubble, color: '#ffffff' }
                    : msg.role !== 'user' && !msg.error && !msg.notice && agentBubble ? { background: agentBubble }
                      : undefined
                }
              >
                {msg.role === 'user' || msg.error ? (
                  <div className="whitespace-pre-wrap break-words">{msg.content}</div>
                ) : (
                  <div className="break-words">
                    <ReactMarkdown components={markdownComponents}>{msg.content || ''}</ReactMarkdown>
                  </div>
                )}
              </div>
            </div>
          ))}
          {askEmail && (
            <form onSubmit={saveReplyEmail} className="rounded-2xl border border-dashed p-3 space-y-2 text-sm">
              <p>Leave your email and a person from our team will reply.</p>
              <div className="flex gap-2">
                <input
                  type="email" required placeholder="you@example.com" value={replyEmail}
                  onChange={(e) => setReplyEmail(e.target.value)} disabled={savingEmail}
                  className="flex-1 min-w-0 rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
                <button type="submit" disabled={savingEmail || !replyEmail.trim()}
                  className="shrink-0 rounded-lg bg-primary text-primary-foreground px-3 text-sm disabled:opacity-50" style={accent}>
                  {savingEmail ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Send'}
                </button>
              </div>
            </form>
          )}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-muted border rounded-2xl px-4 py-2.5 flex items-center gap-2 text-sm">
                <Loader2 className="h-4 w-4 animate-spin" />
                Searching...
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      )}

      {!needsIntro && (
        <form onSubmit={sendQuestion} className="shrink-0 border-t p-3 bg-muted/30">
          {error && <p className="text-xs text-destructive mb-2">{error}</p>}
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="Type your question..."
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              disabled={loading}
              className="flex-1 min-w-0 rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <button
              type="submit"
              disabled={loading}
              className="shrink-0 rounded-lg bg-primary text-primary-foreground p-2 hover:opacity-90 disabled:opacity-50"
              style={accent}
              aria-label="Send"
            >
              {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
