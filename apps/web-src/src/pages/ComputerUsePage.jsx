import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { apiFetch } from '../api';
import {
  Monitor, Play, Square, RefreshCw, Shield, AlertTriangle,
  CheckCircle2, Clock, Terminal,
} from 'lucide-react';
import DecisionBadge from '../components/DecisionBadge';
import './ComputerUsePage.css';

const ACTION_PRESETS = [
  { action: 'COMPUTER_VIEW_SCREEN', label: 'View screen', risk: 'LOW' },
  { action: 'COMPUTER_BROWSER_NAVIGATION', label: 'Navigate browser', risk: 'LOW', needsTarget: true, targetKey: 'domain', placeholder: 'intranet.pharma.local' },
  { action: 'COMPUTER_CLICK', label: 'Click element', risk: 'MEDIUM', needsTarget: true, placeholder: 'Submit button' },
  { action: 'COMPUTER_TYPE', label: 'Type text', risk: 'MEDIUM', needsArgs: true, argsKey: 'text', placeholder: 'Patient ID query' },
  { action: 'COMPUTER_READ_FILE', label: 'Read file', risk: 'MEDIUM', needsTarget: true, targetKey: 'path', placeholder: '/sandbox/clinical/report.pdf' },
  { action: 'COMPUTER_UPLOAD_FILE', label: 'Upload file', risk: 'HIGH', needsTarget: true, targetKey: 'path', placeholder: '/sandbox/clinical/upload.csv' },
];

function makeRequestId() {
  return `cu-req-${Date.now()}`;
}

function formatTime(ts) {
  if (!ts) return '—';
  return new Date(ts).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' });
}

export default function ComputerUsePage() {
  const { auth } = useAuth();
  const [agents, setAgents] = useState([]);
  const [environments, setEnvironments] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [approvals, setApprovals] = useState([]);
  const [actionLog, setActionLog] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [agentId, setAgentId] = useState('');
  const [environmentId, setEnvironmentId] = useState('sandbox-default');
  const [activeSessionId, setActiveSessionId] = useState(null);

  const [selectedAction, setSelectedAction] = useState(ACTION_PRESETS[0].action);
  const [target, setTarget] = useState('');
  const [argText, setArgText] = useState('');
  const [executing, setExecuting] = useState(false);
  const [lastResult, setLastResult] = useState(null);

  const computerAgents = useMemo(
    () => agents.filter((a) => (a.computer_use_permissions || []).length > 0),
    [agents],
  );

  const activeSession = useMemo(
    () => sessions.find((s) => s.session_id === activeSessionId) || null,
    [sessions, activeSessionId],
  );

  const selectedPreset = ACTION_PRESETS.find((p) => p.action === selectedAction) || ACTION_PRESETS[0];

  const load = useCallback(async () => {
    try {
      const [ag, env, sess, ap, log] = await Promise.all([
        apiFetch('/agents', { token: auth?.token }),
        apiFetch('/computer/environments', { token: auth?.token }),
        apiFetch('/computer/sessions', { token: auth?.token }),
        apiFetch('/approval', { token: auth?.token }),
        apiFetch('/computer/actions?limit=30', { token: auth?.token }),
      ]);
      setAgents(ag);
      setEnvironments(env);
      setSessions(sess);
      setApprovals(ap);
      setActionLog(log);
      setError(null);

      const withPerms = ag.filter((a) => (a.computer_use_permissions || []).length > 0);
      if (!agentId && withPerms.length > 0) {
        setAgentId(withPerms[0].agent_id);
      }
    } catch (err) {
      setError(err.message || 'Failed to load computer-use data');
    } finally {
      setLoading(false);
    }
  }, [auth?.token, agentId]);

  useEffect(() => {
    load();
    const id = setInterval(load, 12000);
    return () => clearInterval(id);
  }, [load]);

  async function startSession(e) {
    e.preventDefault();
    if (!agentId) return;
    setError(null);
    try {
      const session = await apiFetch('/computer/sessions', {
        method: 'POST',
        token: auth?.token,
        body: { agent_id: agentId, environment_id: environmentId },
      });
      setActiveSessionId(session.session_id);
      await load();
    } catch (err) {
      setError(err.message || 'Failed to start session');
    }
  }

  async function stopSession(sessionId) {
    setError(null);
    try {
      await apiFetch(`/computer/sessions/${sessionId}/stop`, {
        method: 'POST',
        token: auth?.token,
      });
      if (activeSessionId === sessionId) {
        setActiveSessionId(null);
        setLastResult(null);
      }
      await load();
    } catch (err) {
      setError(err.message || 'Failed to stop session');
    }
  }

  async function executeAction(approvalId = null) {
    if (!activeSessionId) return;
    setExecuting(true);
    setError(null);
    const requestId = makeRequestId();
    const arguments_ = {};
    if (selectedPreset.needsArgs && argText) {
      arguments_[selectedPreset.argsKey || 'text'] = argText;
    }
    if (selectedPreset.targetKey === 'domain' && target) {
      arguments_.domain = target;
    }
    if (selectedPreset.targetKey === 'path' && target) {
      arguments_.path = target;
    }
    try {
      const result = await apiFetch(`/computer/sessions/${activeSessionId}/actions`, {
        method: 'POST',
        token: auth?.token,
        body: {
          request_id: requestId,
          action: selectedAction,
          target: target || null,
          arguments: arguments_,
          approval_id: approvalId,
        },
      });
      setLastResult(result);
      await load();
      if (activeSessionId) {
        const sessionLog = await apiFetch(
          `/computer/sessions/${activeSessionId}/actions?limit=20`,
          { token: auth?.token },
        );
        setActionLog(sessionLog);
      }
    } catch (err) {
      setError(err.message || 'Action failed');
    } finally {
      setExecuting(false);
    }
  }

  async function approveAndRetry(approvalId) {
    setError(null);
    try {
      await apiFetch(`/approval/${approvalId}/approve`, {
        method: 'POST',
        token: auth?.token,
        body: { approver: auth?.role || 'reviewer' },
      });
      await executeAction(approvalId);
    } catch (err) {
      setError(err.message || 'Approval failed');
    }
  }

  if (loading && agents.length === 0) {
    return <div className="cu-page"><p className="cu-muted">Loading computer-use console…</p></div>;
  }

  return (
    <div className="cu-page">
      <header className="cu-header">
        <div>
          <p className="cu-eyebrow">Governed sandbox</p>
          <h1 className="cu-title"><Monitor size={22} /> Computer Use</h1>
          <p className="cu-subtitle">
            Every screen action passes policy, risk scoring, safe rewrite, and audit — simulated sandbox only.
          </p>
        </div>
        <button type="button" className="cu-refresh" onClick={load} aria-label="Refresh">
          <RefreshCw size={15} />
        </button>
      </header>

      {error && <p className="cu-error" role="alert">{error}</p>}

      <div className="cu-grid">
        <section className="cu-card">
          <h2 className="cu-card-title">Start session</h2>
          <form onSubmit={startSession} className="cu-form">
            <label className="cu-field">
              <span>Agent</span>
              <select value={agentId} onChange={(e) => setAgentId(e.target.value)} required>
                {computerAgents.length === 0 && <option value="">No agents with computer permissions</option>}
                {computerAgents.map((a) => (
                  <option key={a.agent_id} value={a.agent_id}>{a.name}</option>
                ))}
              </select>
            </label>
            <label className="cu-field">
              <span>Environment</span>
              <select value={environmentId} onChange={(e) => setEnvironmentId(e.target.value)}>
                {environments.map((env) => (
                  <option key={env.environment_id} value={env.environment_id}>{env.name}</option>
                ))}
              </select>
            </label>
            {environments.find((e) => e.environment_id === environmentId) && (
              <p className="cu-env-desc">
                {environments.find((e) => e.environment_id === environmentId).description}
              </p>
            )}
            <button type="submit" className="cu-btn cu-btn-primary" disabled={!agentId}>
              <Play size={14} /> Start sandbox session
            </button>
          </form>
        </section>

        <section className="cu-card">
          <h2 className="cu-card-title">Active sessions</h2>
          {sessions.length === 0 ? (
            <p className="cu-muted">No active sessions.</p>
          ) : (
            <ul className="cu-session-list">
              {sessions.map((s) => (
                <li key={s.session_id} className={s.session_id === activeSessionId ? 'active' : ''}>
                  <button
                    type="button"
                    className="cu-session-select"
                    onClick={() => setActiveSessionId(s.session_id)}
                  >
                    <span className="cu-session-agent">{s.agent_id}</span>
                    <span className="cu-session-meta">{s.environment_id} · {s.actions_executed} executed</span>
                  </button>
                  <button
                    type="button"
                    className="cu-btn-icon"
                    onClick={() => stopSession(s.session_id)}
                    title="Stop session"
                  >
                    <Square size={14} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {activeSession && (
        <section className="cu-card cu-console">
          <div className="cu-console-head">
            <h2 className="cu-card-title"><Terminal size={16} /> Action console</h2>
            <div className="cu-session-badges">
              <span className="cu-badge">{activeSession.environment_id}</span>
              <span className="cu-badge">risk ≤ {activeSession.risk_limit}</span>
              <span className="cu-badge">{activeSession.actions_executed} ok / {activeSession.actions_blocked} blocked</span>
            </div>
          </div>

          <div className="cu-action-row">
            <label className="cu-field cu-field-inline">
              <span>Action</span>
              <select value={selectedAction} onChange={(e) => setSelectedAction(e.target.value)}>
                {ACTION_PRESETS.map((p) => (
                  <option key={p.action} value={p.action}>{p.label} ({p.risk})</option>
                ))}
              </select>
            </label>
            {(selectedPreset.needsTarget || selectedPreset.targetKey) && (
              <label className="cu-field cu-field-inline cu-field-grow">
                <span>Target</span>
                <input
                  type="text"
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  placeholder={selectedPreset.placeholder || 'target'}
                />
              </label>
            )}
            {selectedPreset.needsArgs && (
              <label className="cu-field cu-field-inline cu-field-grow">
                <span>Input</span>
                <input
                  type="text"
                  value={argText}
                  onChange={(e) => setArgText(e.target.value)}
                  placeholder={selectedPreset.placeholder || 'value'}
                />
              </label>
            )}
            <button
              type="button"
              className="cu-btn cu-btn-primary"
              onClick={() => executeAction()}
              disabled={executing}
            >
              {executing ? 'Running…' : 'Execute'}
            </button>
          </div>

          {lastResult && (
            <div className={`cu-result cu-result-${lastResult.decision}`}>
              <div className="cu-result-head">
                <DecisionBadge action={lastResult.decision} size="small" />
                <span className="cu-risk">Risk: {lastResult.risk_level}</span>
              </div>
              <p className="cu-result-reason">{lastResult.reason}</p>
              {lastResult.approval_required && lastResult.approval_id && (
                <div className="cu-approval-banner">
                  <AlertTriangle size={14} />
                  <span>Human approval required for this action.</span>
                  <button
                    type="button"
                    className="cu-btn cu-btn-approve"
                    onClick={() => approveAndRetry(lastResult.approval_id)}
                  >
                    <CheckCircle2 size={14} /> Approve &amp; retry
                  </button>
                </div>
              )}
            </div>
          )}

          <div className="cu-boundaries">
            <p><Shield size={12} /> Allowed domains: {(activeSession.allowed_domains || []).join(', ') || '—'}</p>
            <p>Allowed apps: {(activeSession.allowed_apps || []).join(', ') || '—'}</p>
          </div>
        </section>
      )}

      <div className="cu-grid cu-grid-bottom">
        <section className="cu-card">
          <h2 className="cu-card-title"><Clock size={16} /> Action log</h2>
          {actionLog.length === 0 ? (
            <p className="cu-muted">No actions recorded yet.</p>
          ) : (
            <ul className="cu-log-list">
              {actionLog.map((entry) => (
                <li key={entry.log_id} className={`cu-log-item cu-log-${entry.decision}`}>
                  <span className="cu-log-time">{formatTime(entry.timestamp)}</span>
                  <span className="cu-log-action">{entry.action}</span>
                  <DecisionBadge action={entry.decision} size="small" />
                  <span className="cu-log-reason">{entry.reason}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="cu-card">
          <h2 className="cu-card-title">Pending approvals</h2>
          {approvals.length === 0 ? (
            <p className="cu-muted">No pending approvals.</p>
          ) : (
            <ul className="cu-approval-list">
              {approvals.map((ap) => (
                <li key={ap.approval_request_id}>
                  <div>
                    <strong>{ap.requested_action}</strong>
                    <p className="cu-muted">{ap.reason}</p>
                  </div>
                  <button
                    type="button"
                    className="cu-btn cu-btn-approve"
                    onClick={() => approveAndRetry(ap.approval_request_id)}
                  >
                    Approve
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
