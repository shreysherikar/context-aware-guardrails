import DecisionBadge from './DecisionBadge';
import LLMStatusStrip from './LLMStatusStrip';
import ResolutionActions from './ResolutionActions';

const DECISION_HEADINGS = {
  ALLOW: { icon: '✓', title: 'Request Allowed' },
  REWRITE: { icon: '⚠️', title: 'Prompt Safely Rewritten' },
  BLOCK: { icon: '🛑', title: 'Prompt Not Forwarded' },
  REVIEW: { icon: '🔎', title: 'Human Review Required' },
};

export default function ExplainableDecisionPanel({
  explanation,
  data,
  conversationId,
  token,
  originalPrompt = '',
  onApplyRephrase,
  onActionComplete,
}) {
  if (!explanation) {
    return (
      <div className="explain-fallback">
        <p className="muted">No structured explanation available for this response.</p>
      </div>
    );
  }

  const decision = String(explanation.decision || 'UNKNOWN').toUpperCase();
  const heading = DECISION_HEADINGS[decision] || { icon: '•', title: decision };

  return (
    <div className={`explain-panel explain-${decision.toLowerCase()}`}>
      <div className="explain-hero">
        <h3 className="explain-title">
          {heading.icon} {heading.title}
        </h3>
        <DecisionBadge action={decision} size="small" />
      </div>

      {decision === 'ALLOW' && (
        <p className="explain-lead">{explanation.reason}</p>
      )}

      {decision === 'REWRITE' && (
        <>
          <p className="explain-lead">{explanation.reason}</p>
          {explanation.sanitized_prompt && (
            <div className="box">
              <p className="kv-label">Safe version forwarded to LLM</p>
              <pre className="response-text">{explanation.sanitized_prompt}</pre>
            </div>
          )}
          {explanation.original_prompt_protected && (
            <p className="muted explain-note">Original prompt is protected and was not forwarded.</p>
          )}
        </>
      )}

      {(decision === 'BLOCK' || decision === 'REVIEW') && (
        <>
          <div className="explain-section">
            <p className="explain-section-title">Why was it stopped?</p>
            <p>{explanation.reason}</p>
          </div>

          {explanation.detected_elements?.length > 0 && (
            <div className="explain-section">
              <p className="explain-section-title">Detected issue</p>
              <ul className="detected-list">
                {explanation.detected_elements.map((el, i) => (
                  <li key={i}>{el}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="explain-section">
            <p className="explain-section-title">Category</p>
            <p>{explanation.category}</p>
          </div>

          {decision === 'REVIEW' && (
            <p className="explain-note warn">
              The request has NOT been forwarded to the LLM.
            </p>
          )}

          {decision === 'BLOCK' && (
            <div className="explain-section">
              <p className="explain-section-title">How can this be resolved?</p>
              <p className="muted">{explanation.resolution_message}</p>
            </div>
          )}
        </>
      )}

      {explanation.safe_suggestions?.length > 0 && decision !== 'ALLOW' && (
        <div className="explain-section">
          <p className="explain-section-title">Suggestions</p>
          <ul className="detected-list">
            {explanation.safe_suggestions.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      )}

      {decision !== 'ALLOW' && (
        <ResolutionActions
          explanation={explanation}
          conversationId={conversationId}
          token={token}
          originalPrompt={originalPrompt}
          onApplyRephrase={onApplyRephrase}
          onActionComplete={onActionComplete}
        />
      )}

      <LLMStatusStrip steps={explanation.llm_status} />

      {typeof data?.response === 'string' && data.response.length > 0 && decision === 'ALLOW' && (
        <div className="box" style={{ marginTop: 16 }}>
          <p className="kv-label">LLM Response</p>
          <pre className="response-text">{data.response}</pre>
        </div>
      )}

      {typeof data?.response === 'string' && data.response.length > 0 && decision === 'REWRITE' && (
        <div className="box" style={{ marginTop: 16 }}>
          <p className="kv-label">LLM Response (from sanitized prompt)</p>
          <pre className="response-text">{data.response}</pre>
        </div>
      )}
    </div>
  );
}
