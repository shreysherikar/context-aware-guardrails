import { useState } from 'react';
import { requestRephrase, requestHumanReview, reportDecision } from '../api';

const RESOLUTION_ICONS = {
  REPHRASE: '🔧',
  HUMAN_REVIEW: '🟠',
  CANNOT_SELF_RESOLVE: '🛑',
  REPORT: '📋',
};

export default function ResolutionActions({
  explanation,
  conversationId,
  token,
  originalPrompt = '',
  onApplyRephrase,
  onActionComplete,
}) {
  const [loading, setLoading] = useState(null);
  const [message, setMessage] = useState(null);
  const [suggested, setSuggested] = useState(null);

  if (!explanation) return null;

  const resolutions = explanation.available_resolutions || [];
  const hasRephrase = resolutions.some((r) => r.type === 'REPHRASE');
  const hasHumanReview = resolutions.some((r) => r.type === 'HUMAN_REVIEW');
  const hasReport = resolutions.some((r) => r.type === 'REPORT');

  async function handleRephrase() {
    setLoading('rephrase');
    setMessage(null);
    try {
      const data = await requestRephrase({
        token,
        requestId: explanation.request_id,
        conversationId,
        prompt: '',
      });
      setSuggested(data.suggested_prompt);
      setMessage('Suggested safer phrasing is ready. Review it before applying.');
    } catch (err) {
      setMessage(err.message || 'Rephrase request failed.');
    } finally {
      setLoading(null);
    }
  }

  async function handleRephraseWithPrompt(prompt) {
    setLoading('rephrase');
    setMessage(null);
    try {
      const data = await requestRephrase({
        token,
        requestId: explanation.request_id,
        conversationId,
        prompt,
      });
      setSuggested(data.suggested_prompt);
      setMessage('Suggested safer phrasing is ready.');
    } catch (err) {
      setMessage(err.message || 'Rephrase request failed.');
    } finally {
      setLoading(null);
    }
  }

  async function handleHumanReview() {
    setLoading('review');
    setMessage(null);
    try {
      const data = await requestHumanReview({
        token,
        requestId: explanation.request_id,
        conversationId,
      });
      setMessage(`Human review submitted (${data.status}). The prompt was not sent to the LLM.`);
      onActionComplete?.('review', data);
    } catch (err) {
      setMessage(err.message || 'Review request failed.');
    } finally {
      setLoading(null);
    }
  }

  async function handleReport() {
    setLoading('report');
    setMessage(null);
    try {
      const data = await reportDecision({
        token,
        requestId: explanation.request_id,
        conversationId,
      });
      setMessage(`Report submitted (${data.status}). The original prompt was not forwarded.`);
      onActionComplete?.('report', data);
    } catch (err) {
      setMessage(err.message || 'Report failed.');
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="resolution-actions">
      {resolutions.map((r) => (
        <div key={r.type} className={`resolution-card resolution-${r.type.toLowerCase()}`}>
          <p className="resolution-card-title">
            {RESOLUTION_ICONS[r.type] || '•'} {r.title}
          </p>
          <p className="resolution-card-msg">{r.message}</p>
        </div>
      ))}

      <div className="resolution-buttons">
        {hasRephrase && (
          <button
            type="button"
            className="btn secondary"
            disabled={!!loading}
            onClick={() => handleRephraseWithPrompt(
              originalPrompt || explanation.sanitized_prompt || ''
            )}
          >
            {loading === 'rephrase' ? 'Working…' : 'Help Me Rephrase'}
          </button>
        )}
        {hasHumanReview && (
          <button
            type="button"
            className="btn secondary"
            disabled={!!loading}
            onClick={handleHumanReview}
          >
            {loading === 'review' ? 'Submitting…' : 'Request Human Review'}
          </button>
        )}
        {hasReport && (
          <button
            type="button"
            className="btn ghost"
            disabled={!!loading}
            onClick={handleReport}
          >
            {loading === 'report' ? 'Submitting…' : 'Report for Review'}
          </button>
        )}
      </div>

      {suggested && (
        <div className="rephrase-suggestion box">
          <p className="rephrase-label">Suggested safer phrasing</p>
          <pre className="response-text">{suggested}</pre>
          {onApplyRephrase && (
            <button
              type="button"
              className="btn primary btn-sm"
              onClick={() => onApplyRephrase(suggested)}
            >
              Use This Prompt
            </button>
          )}
        </div>
      )}

      {message && <p className="resolution-feedback">{message}</p>}
    </div>
  );
}
