import { AlertTriangle, Shield } from 'lucide-react';

const SEVERITY_CLASS = {
  high: 'guardrail-notice--high',
  medium: 'guardrail-notice--medium',
  low: 'guardrail-notice--low',
};

/**
 * Shown only when guardrails detect a problem — explains what and why.
 */
export default function GuardrailNotice({ userText, issues = [], highlights = [], action }) {
  if (!issues.length && !highlights.length) return null;

  return (
    <div className={`guardrail-notice ${SEVERITY_CLASS.high}`}>
      <div className="guardrail-notice-header">
        <Shield size={15} />
        <strong>Policy concern detected</strong>
        {action && action !== 'ALLOW' && (
          <span className="guardrail-notice-action">{action}</span>
        )}
      </div>

      {issues.length > 0 && (
        <ul className="guardrail-notice-issues">
          {issues.map((issue) => (
            <li key={issue.code}>
              <AlertTriangle size={13} />
              <div>
                <strong>{issue.title}</strong>
                <p>{issue.why || issue.description}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
