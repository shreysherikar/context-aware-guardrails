import { useState, useMemo } from 'react';
import { useAuth } from '../context/AuthContext';
import { apiFetch } from '../api';
import AgentFlowCanvas from '../components/flow/AgentFlowCanvas';
import {
  AGENT_NODES,
  idleStates,
  runningStates,
  traceFromResponse,
  countByStatus,
} from '../data/agentFlow';
import {
  Pause, Trash2, MessageSquare,
  Send, Loader2, Plus,
} from 'lucide-react';
import VoiceInputButton from '../components/VoiceInputButton';
import './AgentFlowPage.css';

function makeConvoId() {
  return `convo-${Date.now()}`;
}

const STATUS_ROWS = [
  { key: 'complete', label: 'Complete', dotClass: 'status-dot-complete' },
  { key: 'running', label: 'Running', dotClass: 'status-dot-running' },
  { key: 'pending', label: 'Pending', dotClass: 'status-dot-pending' },
  { key: 'idle', label: 'Idle', dotClass: 'status-dot-idle' },
  { key: 'error', label: 'Errors', dotClass: 'status-dot-error' },
];

const SAMPLE_PROMPTS = [
  'Draft a compliant follow-up email for an HCP after our diabetes webinar.',
  'Search the web for the latest FDA guidance on GLP-1 labeling.',
  'Summarize aggregate CRM engagement metrics by region for Q3.',
  'Explain fair balance requirements for our promotional materials.',
];

function actionClass(action) {
  const key = String(action || '').toLowerCase();
  if (key === 'allow') return 'decision-allow';
  if (key === 'rewrite') return 'decision-rewrite';
  if (key === 'clarify') return 'decision-clarify';
  if (key === 'review') return 'decision-review';
  if (key === 'block') return 'decision-block';
  return '';
}

function shouldShowActionBadge(action) {
  return String(action || '').toUpperCase() === 'BLOCK';
}

export default function AgentFlowPage() {
  const { auth } = useAuth();
  const [nodeStates, setNodeStates] = useState(idleStates());
  const [selectedId, setSelectedId] = useState('router');
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [convId] = useState(makeConvoId);
  /** compose = input visible · active = input collapsed into result row */
  const [dockMode, setDockMode] = useState('compose');
  const [activeRun, setActiveRun] = useState(null);
  const [resultExpanded, setResultExpanded] = useState(false);

  const counts = useMemo(() => countByStatus(nodeStates), [nodeStates]);
  const selectedNode = AGENT_NODES.find((n) => n.id === selectedId);
  const selectedState = nodeStates[selectedId];

  async function runFlow(message) {
    const text = (message ?? prompt).trim();
    if (!text || !auth || loading) return;

    setLoading(true);
    setDockMode('active');
    setResultExpanded(false);
    setActiveRun({ status: 'running', prompt: text });
    setPrompt('');
    setNodeStates(runningStates());

    try {
      const data = await apiFetch('/agent/chat', {
        method: 'POST',
        body: { message: text, conversation_id: convId, use_web_search: true },
        token: auth.token,
      });
      setNodeStates(traceFromResponse(data, text));
      if (data.primary_agent) setSelectedId(data.primary_agent);
      setActiveRun({
        status: 'complete',
        prompt: text,
        action: data.action,
        primaryAgent: data.primary_agent,
        summary: data.message || data.answer,
      });
    } catch (err) {
      const msg = err.message || 'Agent flow failed';
      setNodeStates(idleStates());
      setActiveRun({ status: 'error', prompt: text, summary: msg });
    } finally {
      setLoading(false);
    }
  }

  function openCompose() {
    setDockMode('compose');
    setActiveRun(null);
    setResultExpanded(false);
  }

  function resetFlow() {
    setNodeStates(idleStates());
    setPrompt('');
    setSelectedId('router');
    setActiveRun(null);
    setResultExpanded(false);
    setDockMode('compose');
  }

  return (
    <div className="agent-flow-page">
      <header className="flow-header">
        <div className="flow-header-left">
          <h1 className="flow-title">Pipeline canvas</h1>
          {selectedNode && (
            <p className="flow-task-preview">
              <strong>{selectedNode.name}</strong>
              {' · '}
              {selectedState?.task || selectedNode.description}
            </p>
          )}
        </div>

        <div className="flow-status-strip" aria-label="Agent status">
          {STATUS_ROWS.map(({ key, label, dotClass }) => (
            <div key={key} className="flow-status-chip">
              <span className={`flow-status-dot ${dotClass}`} />
              <span className="flow-status-chip-label">{label}</span>
              <span className="flow-status-count">{counts[key] || 0}</span>
            </div>
          ))}
        </div>

        <div className="flow-header-actions">
          <button type="button" className="flow-action-btn ghost" onClick={resetFlow}>
            <Trash2 size={14} /> Reset
          </button>
          <button type="button" className="flow-action-btn ghost" disabled={loading}>
            <Pause size={14} /> Pause
          </button>
          <a className="flow-action-btn primary" href="/agent">
            <MessageSquare size={14} /> Open Chat
          </a>
        </div>
      </header>

      <div className="flow-body">
        <AgentFlowCanvas
          nodeStates={nodeStates}
          selectedId={selectedId}
          onSelectNode={setSelectedId}
        />

        <div className="flow-toolbar">
          <button type="button" className="flow-toolbar-btn" title="Add node">+</button>
          <button type="button" className="flow-toolbar-btn" title="Fit view">⊡</button>
          <button type="button" className="flow-toolbar-btn" title="Settings">⚙</button>
        </div>

        <div className={`flow-dock flow-dock--${dockMode}`} aria-label="Pipeline prompt">
          {dockMode === 'compose' ? (
            <>
              <div className="flow-dock-samples">
                {SAMPLE_PROMPTS.map((sample) => (
                  <button
                    key={sample}
                    type="button"
                    className="flow-sample-chip"
                    onClick={() => runFlow(sample)}
                  >
                    {sample.length > 40 ? `${sample.slice(0, 40)}…` : sample}
                  </button>
                ))}
              </div>
              <div className="flow-prompt-bar">
                <input
                  type="text"
                  className="flow-prompt-input"
                  placeholder="Run a prompt through the agent pipeline…"
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && runFlow()}
                  aria-label="Pipeline prompt"
                  autoFocus
                />
                <VoiceInputButton
                  value={prompt}
                  disabled={loading}
                  onTranscript={setPrompt}
                />
                <button
                  type="button"
                  className="flow-prompt-send"
                  disabled={!prompt.trim()}
                  onClick={() => runFlow()}
                  aria-label="Run flow"
                >
                  <Send size={15} />
                </button>
              </div>
            </>
          ) : (
            activeRun && (
              <div
                className={`flow-dock-result flow-dock-result--${activeRun.status}${resultExpanded ? ' flow-dock-result--expanded' : ''}`}
                aria-live="polite"
              >
                <div className="flow-dock-result-row">
                  <button
                    type="button"
                    className="flow-dock-result-body"
                    onClick={() => {
                      if (!loading && activeRun.summary) setResultExpanded((v) => !v);
                    }}
                    disabled={loading || !activeRun.summary}
                    aria-expanded={resultExpanded}
                    title={activeRun.summary || activeRun.prompt}
                  >
                    {activeRun.status === 'running' && (
                      <Loader2 size={14} className="spin flow-dock-result-icon" />
                    )}
                    {activeRun.status === 'complete' && shouldShowActionBadge(activeRun.action) && (
                      <span className={`flow-dock-result-badge ${actionClass(activeRun.action)}`}>
                        {activeRun.action}
                      </span>
                    )}
                    {activeRun.status === 'error' && (
                      <span className="flow-dock-result-badge flow-dock-result-badge--error">Error</span>
                    )}
                    <span className="flow-dock-result-prompt">{activeRun.prompt}</span>
                  </button>
                  {!loading && (
                    <button
                      type="button"
                      className="flow-dock-new"
                      onClick={openCompose}
                      aria-label="New prompt"
                      title="New prompt"
                    >
                      <Plus size={16} />
                    </button>
                  )}
                </div>
                {resultExpanded && activeRun.summary && activeRun.status !== 'running' && (
                  <p className="flow-dock-result-summary">{activeRun.summary}</p>
                )}
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}
