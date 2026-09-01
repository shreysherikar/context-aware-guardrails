import { useEffect, useState } from 'react';
import { apiFetch } from '../api';
import {
  Shield, Bot, CheckCircle2, XCircle, Clock, AlertTriangle,
  Activity, FileText, Lock, Monitor, RefreshCw, Octagon,
} from 'lucide-react';
import './GovernanceDashboard.css';

const DECISION_CLASS = {
  ALLOW: 'decision-allow',
  BLOCK: 'decision-block',
  HUMAN_APPROVAL_REQUIRED: 'decision-approval',
  REVIEW_REQUIRED: 'decision-review',
  RESTRICT: 'decision-restrict',
};

const STATUS_DOT_CLASS = {
  complete: 'status-dot-complete',
  running: 'status-dot-running',
  pending: 'status-dot-pending',
  idle: 'status-dot-idle',
  error: 'status-dot-error',
};

export default function GovernanceDashboard() {
  const [status, setStatus] = useState(null);
  const [agents, setAgents] = useState([]);
  const [approvals, setApprovals] = useState([]);
  const [events, setEvents] = useState([]);
  const [audit, setAudit] = useState([]);
  const [rewrites, setRewrites] = useState([]);
  const [computerSessions, setComputerSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, []);

  async function load() {
    try {
      const [st, ag, ap, ev, au, rw, cs] = await Promise.all([
        apiFetch('/system/status'),
        apiFetch('/agents'),
        apiFetch('/approval'),
        apiFetch('/security/events?limit=20'),
        apiFetch('/audit?limit=15'),
        apiFetch('/rewrite/recent?limit=10').catch(() => []),
        apiFetch('/computer/sessions').catch(() => []),
      ]);
      setStatus(st);
      setAgents(ag);
      setApprovals(ap);
      setEvents(ev);
      setAudit(au);
      setRewrites(rw);
      setComputerSessions(cs);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to load governance data');
    } finally {
      setLoading(false);
    }
  }

  const categories = agents.reduce((acc, a) => {
    acc[a.category] = (acc[a.category] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="gov-dashboard">
      <header className="gov-header">
        <div>
          <p className="gov-eyebrow">Always-active governance</p>
          <h1 className="gov-title">Pharma AI Agent Control Plane</h1>
        </div>
        <div className="gov-runtime-badge">
          {status?.emergency_stop_active && (
            <span className="gov-emergency"><Octagon size={14} /> EMERGENCY STOP</span>
          )}
          <span className={`gov-dot${status?.active ? ' live' : ''}`} />
          {status?.active ? 'Runtime active' : 'Runtime offline'}
        </div>
      </header>

      {error && <p className="gov-error">{error}</p>}

      <div className="gov-stats">
        <StatCard icon={Bot} label="Registered agents" value={status?.agents_registered ?? '—'} />
        <StatCard icon={CheckCircle2} label="Allowed" value={status?.requests_allowed ?? 0} tone="green" />
        <StatCard icon={XCircle} label="Blocked" value={status?.requests_blocked ?? 0} tone="red" />
        <StatCard icon={Clock} label="Pending approvals" value={status?.pending_approvals ?? 0} tone="amber" />
        <StatCard icon={AlertTriangle} label="Security events" value={status?.security_events ?? 0} tone="red" />
        <StatCard icon={FileText} label="Audit entries" value={status?.audit_entries ?? 0} />
        <StatCard icon={RefreshCw} label="Rewrites applied" value={status?.rewrites_applied ?? 0} tone="amber" />
        <StatCard icon={Monitor} label="Computer sessions" value={status?.active_computer_sessions ?? 0} />
      </div>

      <div className="gov-grid">
        <section className="gov-panel">
          <h2><Activity size={16} /> Agent categories</h2>
          <div className="gov-category-list">
            {Object.entries(categories).map(([cat, count]) => (
              <div key={cat} className="gov-category-row">
                <span>{cat.replace(/_/g, ' ')}</span>
                <span className="gov-count">{count}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="gov-panel">
          <h2><Clock size={16} /> Pending approvals</h2>
          {approvals.length === 0 ? (
            <p className="gov-empty">No pending approvals</p>
          ) : (
            <div className="gov-approval-list">
              {approvals.map((a) => (
                <div key={a.approval_request_id} className="gov-approval-item">
                  <strong>{a.requested_action}</strong>
                  <span className="gov-muted">{a.requesting_agent}</span>
                  <span className="gov-risk">{a.risk_level}</span>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="gov-panel">
          <h2><RefreshCw size={16} /> Safe rewriting</h2>
          {rewrites.length === 0 ? (
            <p className="gov-empty">No recent rewrites</p>
          ) : (
            <div className="gov-rewrite-list">
              {rewrites.map((r, i) => (
                <div key={i} className="gov-rewrite-item">
                  <span className="gov-risk">{r.status}</span>
                  <strong>{r.agent_id}</strong>
                  <span className="gov-muted">{r.request_id}</span>
                  {r.threats?.length > 0 && (
                    <span className="gov-muted">Threats: {r.threats.join(', ')}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="gov-panel">
          <h2><Monitor size={16} /> Computer use</h2>
          {computerSessions.length === 0 ? (
            <p className="gov-empty">No active sessions</p>
          ) : (
            <div className="gov-approval-list">
              {computerSessions.map((s) => (
                <div key={s.session_id} className="gov-approval-item">
                  <strong>{s.agent_id}</strong>
                  <span className="gov-muted">{s.current_application || '—'} / {s.current_domain || '—'}</span>
                  <span className="gov-risk">{s.actions_executed} executed · {s.actions_blocked} blocked</span>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="gov-panel wide">
          <h2><Shield size={16} /> Recent audit events</h2>
          {audit.length === 0 ? (
            <p className="gov-empty">{loading ? 'Loading…' : 'No audit events yet'}</p>
          ) : (
            <table className="gov-table">
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Action</th>
                  <th>Risk</th>
                  <th>Decision</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((row, i) => (
                  <tr key={i}>
                    <td>{row.agent_id}</td>
                    <td>{row.action}</td>
                    <td><span className="gov-risk">{row.risk_level}</span></td>
                    <td>
                      <span className={`gov-decision ${DECISION_CLASS[row.policy_decision] || 'decision-restrict'}`}>
                        {row.policy_decision}
                      </span>
                    </td>
                    <td>{row.result}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="gov-panel wide">
          <h2><Lock size={16} /> Security events</h2>
          {events.length === 0 ? (
            <p className="gov-empty">No security events</p>
          ) : (
            <div className="gov-event-list">
              {events.map((ev) => (
                <div key={ev.event_id} className="gov-event-item">
                  <span className={`gov-sev gov-sev--${ev.severity.toLowerCase()}`}>{ev.severity}</span>
                  <div>
                    <strong>{ev.category.replace(/_/g, ' ')}</strong>
                    <p className="gov-muted">{ev.description}</p>
                  </div>
                  <span className="gov-muted">{ev.agent_id}</span>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, tone }) {
  return (
    <div className={`gov-stat${tone ? ` gov-stat--${tone}` : ''}`}>
      <Icon size={18} />
      <div>
        <span className="gov-stat-value">{value}</span>
        <span className="gov-stat-label">{label}</span>
      </div>
    </div>
  );
}
