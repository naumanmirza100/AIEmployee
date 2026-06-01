import React, { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { API_BASE_URL } from '@/config/apiConfig';
import { Loader2, Star, CheckCircle, XCircle } from 'lucide-react';

/**
 * Public CSAT submit page. Reached via the link in the post-ticket survey
 * email at /embed/csat?t=<token>. No auth — the token in the URL
 * authenticates the submit against TicketSatisfaction.token.
 *
 * Same look + spacing as FrontlineEmbedFormPage so it feels native to the
 * widget brand. Single-page, single-action: rate 1-5 stars + optional comment.
 */
export default function FrontlineEmbedCsatPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('t') || searchParams.get('token') || '';
  const [hovered, setHovered] = useState(0);
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e?.preventDefault?.();
    if (!token) {
      setError('Invalid link — missing token. Use the link from your email.');
      return;
    }
    if (!rating || rating < 1 || rating > 5) {
      setError('Please pick a rating from 1 to 5 stars.');
      return;
    }
    setError('');
    setSubmitting(true);
    try {
      const resp = await fetch(`${API_BASE_URL}/frontline/csat/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, rating, comment: comment.trim() }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data?.message || `Submit failed (${resp.status})`);
      setSubmitted(true);
    } catch (err) {
      setError(err.message || 'Submit failed. Please try again or contact support.');
    } finally {
      setSubmitting(false);
    }
  };

  const ratingLabels = ['', 'Very dissatisfied', 'Dissatisfied', 'Neutral', 'Satisfied', 'Very satisfied'];

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-gradient-to-br from-slate-900 via-violet-950/40 to-slate-900">
      <div className="w-full max-w-md rounded-2xl border border-white/10 bg-black/40 backdrop-blur-sm p-6 shadow-xl">
        {submitted ? (
          <div className="text-center py-8">
            <CheckCircle className="h-12 w-12 text-emerald-400 mx-auto mb-3" />
            <h1 className="text-xl font-semibold text-white mb-1">Thanks for your feedback!</h1>
            <p className="text-sm text-white/60">
              Your rating helps us improve. You can close this tab.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            <h1 className="text-xl font-semibold text-white mb-1">How did we do?</h1>
            <p className="text-sm text-white/55 mb-6">
              Take a few seconds to rate your support experience.
            </p>

            <div className="flex items-center justify-center gap-1 mb-2">
              {[1, 2, 3, 4, 5].map((n) => {
                const active = (hovered || rating) >= n;
                return (
                  <button key={n} type="button"
                    onMouseEnter={() => setHovered(n)}
                    onMouseLeave={() => setHovered(0)}
                    onClick={() => setRating(n)}
                    disabled={submitting}
                    aria-label={`${n} star${n > 1 ? 's' : ''}`}
                    className={`p-1.5 rounded-md transition-colors ${
                      submitting ? 'cursor-not-allowed' : 'hover:bg-white/[0.04]'
                    }`}>
                    <Star className={`h-8 w-8 transition-colors ${
                      active ? 'fill-amber-400 text-amber-400' : 'text-white/30'
                    }`} />
                  </button>
                );
              })}
            </div>
            <p className="text-center text-xs text-white/50 h-4 mb-5">
              {hovered ? ratingLabels[hovered] : (rating ? ratingLabels[rating] : '')}
            </p>

            <label className="block text-sm text-white/70 mb-1.5">
              Anything you'd like to add? <span className="text-white/40 text-xs">(optional)</span>
            </label>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={3}
              maxLength={1000}
              placeholder="What worked? What could have been better?"
              disabled={submitting}
              className="w-full rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-white placeholder:text-white/30 focus:outline-none focus:ring-1 focus:ring-violet-400/50 resize-none"
            />

            {error && (
              <div className="mt-3 flex items-start gap-2 rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
                <XCircle className="h-4 w-4 mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={submitting || !rating}
              className="mt-5 w-full inline-flex items-center justify-center gap-2 rounded-lg bg-violet-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-violet-500 disabled:bg-violet-900 disabled:cursor-not-allowed transition-colors">
              {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
              Submit feedback
            </button>
            {!token && (
              <p className="mt-3 text-center text-[11px] text-amber-300/80">
                This page needs a token from a survey email — open it from your link.
              </p>
            )}
          </form>
        )}
      </div>
    </div>
  );
}
