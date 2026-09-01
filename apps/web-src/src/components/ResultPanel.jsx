import { Code2, ChevronRight } from 'lucide-react';
import ExplainableDecisionPanel from './ExplainableDecisionPanel';
import KVGrid from './KVGrid';

/**
 * Shared result renderer for text + image evaluation responses.
 * Primary view: user-facing explainable decision. Debug details in collapsible section.
 */
export default function ResultPanel({
  data,
  conversationId,
  token,
  originalPrompt,
  onApplyRephrase,
  onActionComplete,
}) {
  if (!data) return null;

  const explanation = data.explanation || null;

  return (
    <div className="result-panel fade-in">
      <ExplainableDecisionPanel
        explanation={explanation}
        data={data}
        conversationId={conversationId || data.conversation_id || ''}
        token={token}
        originalPrompt={originalPrompt || ''}
        onApplyRephrase={onApplyRephrase}
        onActionComplete={onActionComplete}
      />

      <details className="raw-details debug-details">
        <summary>
          <Code2 size={13} />
          <span>Debug details (policy, risk, raw JSON)</span>
          <ChevronRight size={13} style={{ marginLeft: 'auto', transition: 'transform 0.2s' }} />
        </summary>
        <div className="debug-panels">
          {data.risk_assessment && (
            <div className="sub-block">
              <span className="sub-block-title">Risk Assessment (internal)</span>
              <KVGrid data={data.risk_assessment} />
            </div>
          )}
          {data.decision && (
            <div className="sub-block">
              <span className="sub-block-title">Policy Decision (internal)</span>
              <KVGrid data={data.decision} />
            </div>
          )}
          {data.optical_assessment && (
            <div className="sub-block">
              <span className="sub-block-title">Optical Assessment</span>
              <KVGrid data={data.optical_assessment} />
            </div>
          )}
          <pre className="raw-json">{JSON.stringify(data, null, 2)}</pre>
        </div>
      </details>
    </div>
  );
}
