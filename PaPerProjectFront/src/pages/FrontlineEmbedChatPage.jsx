import React, { useState, useRef, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { API_BASE_URL } from '@/config/apiConfig';
import { Send, Loader2, MessageCircle } from 'lucide-react';

/**
 * Embeddable chat widget page. Load in iframe: /embed/chat?key=WIDGET_KEY
 * No auth; uses public API with widget_key.
 */
export default function FrontlineEmbedChatPage() {
  const [searchParams] = useSearchParams();
  const widgetKey = searchParams.get('key') || searchParams.get('widget_key') || '';
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState([]);
  const [error, setError] = useState('');
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendQuestion = async (e) => {
    e?.preventDefault();
    const q = question.trim();
    if (!q || !widgetKey) {
      setError(widgetKey ? 'Please enter a question.' : 'Invalid embed: missing key.');
      return;
    }
    setError('');
    setMessages((prev) => [...prev, { role: 'user', content: q }]);
    setQuestion('');
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/frontline/public/qa/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, widget_key: widgetKey }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.message || data.error || 'Request failed');
      }
      const answer = data?.data?.answer ?? data?.answer ?? 'No answer available.';
      const hasVerified = data?.data?.has_verified_info ?? data?.has_verified_info ?? false;
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: answer, hasVerified },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Sorry, something went wrong: ${err.message}`, error: true },
      ]);
    } finally {
      setLoading(false);
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
    <div className="flex flex-col h-[min(100vh,520px)] bg-background border border-border rounded-lg shadow-lg overflow-hidden">
      <div className="shrink-0 px-4 py-3 border-b bg-muted/40">
        <h2 className="text-sm font-semibold flex items-center gap-2">
          <MessageCircle className="h-4 w-4" />
          Ask us anything
        </h2>
        <p className="text-xs text-muted-foreground mt-0.5">Answers from our knowledge base.</p>
      </div>
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
                    : 'bg-muted border'
              }`}
            >
              <div className="whitespace-pre-wrap break-words">{msg.content}</div>
            </div>
          </div>
        ))}
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
            aria-label="Send"
          >
            {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
          </button>
        </div>
      </form>
    </div>
  );
}
