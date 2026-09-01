/**
 * Visual status strip: Prompt → ContextGuard → LLM
 */
export default function LLMStatusStrip({ steps }) {
  if (!Array.isArray(steps) || steps.length === 0) return null;

  const statusIcon = {
    forwarded: '✓',
    completed: '✓',
    not_forwarded: '✗',
    not_contacted: '⏸',
    pending: '⏸',
  };

  const statusClass = {
    forwarded: 'status-ok',
    completed: 'status-ok',
    not_forwarded: 'status-block',
    not_contacted: 'status-wait',
    pending: 'status-wait',
  };

  return (
    <div className="llm-status-strip">
      <p className="llm-status-title">LLM Status</p>
      <div className="llm-status-steps">
        {steps.map((step, i) => (
          <div key={i} className="llm-status-step">
            {i > 0 && <span className="llm-status-arrow">→</span>}
            <span className={`llm-status-node ${statusClass[step.status] || ''}`}>
              {statusIcon[step.status] || '•'} {step.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
