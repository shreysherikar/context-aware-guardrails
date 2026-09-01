import { useState, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import { apiFetch } from '../api';
import {
  ClipboardList, RefreshCw, FileText, Image as ImageIcon,
  CheckCircle2, XCircle, Flag, ChevronDown, ChevronUp, Info,
  ShieldAlert, Database,
} from 'lucide-react';
import DecisionBadge from '../components/DecisionBadge';
import RiskChip from '../components/RiskChip';
import KVGrid, { fmt } from '../components/KVGrid';

const LIMIT_OPTIONS = [10, 25, 50, 100, 200];

/**
 * Audit Log page.
 * GET /audit/events with optional conversation_id filter + limit.
 * Each row is expandable to show all populated sub-object panels.
 */
export default function AuditLogPage() {
  const { auth } = useAuth();
  const [events, setEvents]       = useState([]);
  const [convFilter, setConvFilter] = useState('');
  const [limit, setLimit]         = useState(50);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState(null);
  const [expanded, setExpanded]   = useState(null);
  const [hasLoaded, setHasLoaded] = useState(false);

  const fetchEvents = useCallback(async () => {
    if (!auth) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (convFilter.trim()) params.set('conversation_id', convFilter.trim());
      params.set('limit', String(limit));
      const data = await apiFetch(`/audit/events?${params}`, { token: auth.token });
      setEvents(Array.isArray(data) ? data : []);
      setHasLoaded(true);
      setExpanded(null);
    } catch (err) {
      setError(err.message || 'Failed to load audit events.');
      setEvents([]);
    } finally {
      setLoading(false);
    }
  }, [auth, convFilter, limit]);

  function toggleExpand(idx) {
    setExpanded((prev) => (prev === idx ? null : idx));
  }

  return (
    <div className="page-container">
      {/* ── Header card ── */}
      <div className="card glass">
        <div className="card-header">
          <div className="card-icon"><ClipboardList size={20} /></div>
          <div className="card-meta">
            <h2>Audit Log</h2>
            <p className="card-desc">
              Browse all evaluation events via <code>GET /audit/events</code>.
              Every decision — ALLOW through BLOCK — is logged here regardless of outcome.
            </p>
          </div>
        </div>

        {!auth ? (
          <div className="info-box">
            <Info size={14} style={{ flexShrink: 0, marginTop: 1 }} />
            <span>Sign in to view audit events.</span>
          </div>
        ) : (
          <>
            {/* Filters */}
            <div className="audit-filters">
              <div className="field">
                <label htmlFor="audit-conv">Filter by conversation ID (optional)</label>
                <input
                  id="audit-conv"
                  type="text"
                  value={convFilter}
                  onChange={(e) => setConvFilter(e.target.value)}
                  placeholder="e.g. convo-1234567890"
                  spellCheck="false"
                  onKeyDown={(e) => e.key === 'Enter' && fetchEvents()}
                />
              </div>
              <div className="field field-sm">
                <label htmlFor="audit-limit">Limit</label>
                <select
                  id="audit-limit"
                  value={limit}
                  onChange={(e) => setLimit(Number(e.target.value))}
                >
                  {LIMIT_OPTIONS.map((l) => (
                    <option key={l} value={l}>{l}</option>
                  ))}
                </select>
              </div>
              <div className="field field-btn">
                <label>&nbsp;</label>
                <button
                  className="btn primary"
                  onClick={fetchEvents}
                  disabled={loading}
                  aria-busy={loading}
                >
                  {loading ? (
                    <><span className="spinner-inline" /> Loading…</>
                  ) : (
                    <><RefreshCw size={14} /> Refresh</>
                  )}
                </button>
              </div>
            </div>

            {error && (
              <div className="error-box fade-in" style={{ marginTop: 12 }}>
                <span className="error-box-icon"><Info size={15} /></span>
                <div><strong>Error</strong> <span>{error}</span></div>
              </div>
            )}

            {/* Privacy notice */}
            <p className="hint muted" style={{ marginTop: 10, fontSize: '0.76rem' }}>
              <ShieldAlert size={11} style={{ display: 'inline', marginRight: 4 }} />
              Prompts for REWRITE evaluations are stored redacted (<code>"[text input; sanitized]"</code>), and
              image inputs appear as <code>"[image input]"</code> / <code>"[image input; sanitized]"</code>.
              This is backend privacy-preserving audit behavior — not a UI bug.
            </p>

            {/* Empty state */}
            {hasLoaded && events.length === 0 && (
              <div className="empty-state">
                <div className="empty-state-icon">
                  <Database size={24} />
                </div>
                <h3>No audit events found</h3>
                <p>
                  {convFilter
                    ? `No events match conversation ID "${convFilter}".`
                    : 'Run some evaluations first, then refresh.'}
                </p>
              </div>
            )}

            {!hasLoaded && (
              <p className="muted" style={{ marginTop: 16, fontSize: '0.82rem', textAlign: 'center' }}>
                Click Refresh to load audit events.
              </p>
            )}
          </>
        )}
      </div>

      {/* ── Audit table ── */}
      {events.length > 0 && (
        <div className="card glass" style={{ padding: 0, overflow: 'hidden' }}>
          <div className="audit-table" style={{ border: 'none', borderRadius: 0, marginTop: 0 }}>
            {/* Header row */}
            <div className="audit-header-row">
              <div className="audit-col-header cell-time">Timestamp</div>
              <div className="audit-col-header cell-conv">Conversation</div>
              <div className="audit-col-header cell-role">Role</div>
              <div className="audit-col-header cell-action">Decision</div>
              <div className="audit-col-header cell-risk">Risk</div>
              <div className="audit-col-header cell-type">Type</div>
              <div className="audit-col-header cell-flags">Flags</div>
            </div>

            {/* Data rows */}
            {events.map((ev, i) => (
              <AuditRow
                key={i}
                event={ev}
                isExpanded={expanded === i}
                onToggle={() => toggleExpand(i)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Row component ── */
function AuditRow({ event, isExpanded, onToggle }) {
  const action     = event.policy_decision?.action || '?';
  const riskLevel  = event.risk_assessment?.risk_level || '?';
  const isImage    = !!event.optical;
  const genAttempted = event.llm?.attempted;
  const genSucceeded = event.llm?.succeeded;
  const flagged      = event.output_guardrail?.flagged;

  const flags = [];
  if (genAttempted && genSucceeded)  flags.push({ icon: CheckCircle2, label: 'gen·ok',     cls: 'flag-success' });
  if (genAttempted && !genSucceeded) flags.push({ icon: XCircle,      label: 'gen·failed', cls: 'flag-error' });
  if (flagged)                       flags.push({ icon: Flag,          label: 'flagged',    cls: 'flag-warning' });

  const ts = event.timestamp
    ? new Date(event.timestamp).toLocaleString(undefined, {
        month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit', second: '2-digit',
      })
    : '—';

  const convShort = event.conversation_id
    ? (event.conversation_id.length > 18
        ? event.conversation_id.slice(0, 18) + '…'
        : event.conversation_id)
    : '—';

  return (
    <>
      <div
        className={`audit-row${isExpanded ? ' expanded' : ''}`}
        onClick={onToggle}
        role="button"
        tabIndex={0}
        aria-expanded={isExpanded}
        onKeyDown={(e) => e.key === 'Enter' && onToggle()}
      >
        <div className="audit-cell cell-time">{ts}</div>
        <div className="audit-cell cell-conv" title={event.conversation_id}>{convShort}</div>
        <div className="audit-cell cell-role">
          <code style={{ fontSize: '0.74rem' }}>{event.user_role || '—'}</code>
        </div>
        <div className="audit-cell cell-action">
          <DecisionBadge action={action} size="small" />
        </div>
        <div className="audit-cell cell-risk">
          <RiskChip level={riskLevel} />
        </div>
        <div className="audit-cell cell-type">
          {isImage
            ? <><ImageIcon size={12} /> image</>
            : <><FileText  size={12} /> text</>}
        </div>
        <div className="audit-cell cell-flags">
          {flags.length
            ? flags.map((f, i) => (
                <span key={i} className={`flag-badge ${f.cls}`}>
                  <f.icon size={10} /> {f.label}
                </span>
              ))
            : <span style={{ color: 'var(--muted)', fontSize: '0.74rem' }}>—</span>}
          <span style={{ marginLeft: 'auto', color: 'var(--muted)' }}>
            {isExpanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </span>
        </div>
      </div>

      {isExpanded && <AuditDetail event={event} />}
    </>
  );
}

/* ── Expanded detail ── */
function AuditDetail({ event }) {
  return (
    <div className="audit-detail fade-in">
      <div className="audit-detail-grid">
        {/* Prompt — full width */}
        <div className="detail-section detail-full-width">
          <h4><FileText size={11} /> Prompt (stored)</h4>
          <pre className="response-text" style={{ marginTop: 0 }}>{event.prompt || '—'}</pre>
        </div>

        {/* Risk Assessment */}
        {event.risk_assessment && (
          <DetailSection title="Risk Assessment" icon={<ShieldAlert size={11} />}>
            <KVGrid
              data={event.risk_assessment}
              order={['risk_level', 'categories', 'data_sensitivity', 'injection_detected', 'disguise_detected', 'confidence', 'reasoning']}
            />
          </DetailSection>
        )}

        {/* Policy Decision */}
        {event.policy_decision && (
          <DetailSection title="Policy Decision">
            <KVGrid
              data={event.policy_decision}
              order={['action', 'policy_id', 'policy_version', 'reasons', 'required_controls', 'timestamp']}
            />
          </DetailSection>
        )}

        {/* LLM */}
        {event.llm && (
          <DetailSection title="LLM Generation">
            <KVGrid data={event.llm} order={['attempted', 'succeeded', 'error_kind']} />
          </DetailSection>
        )}

        {/* Output Guardrail */}
        {event.output_guardrail && (
          <DetailSection title="Output Guardrail">
            <KVGrid data={event.output_guardrail} order={['attempted', 'flagged', 'error_kind']} />
          </DetailSection>
        )}

        {/* Optical */}
        {event.optical && (
          <DetailSection title="Optical (Image)">
            <KVGrid
              data={event.optical}
              order={['input_type', 'ocr_used', 'optical_analysis_used', 'document_type', 'finding_count', 'sanitization_applied', 'image_sha256']}
            />
          </DetailSection>
        )}

        {/* Sanitization */}
        {event.sanitization && (
          <DetailSection title="Sanitization">
            <KVGrid
              data={event.sanitization}
              order={['attempted', 'succeeded', 'applied', 'input_type', 'finding_count', 'sanitizer_version', 'sanitized_context_used', 'failure_kind']}
            />
          </DetailSection>
        )}

        {/* Claim Verification */}
        {event.claim_verification && (
          <DetailSection title="Claim Verification">
            <ClaimVerificationDetail meta={event.claim_verification} />
          </DetailSection>
        )}
      </div>
    </div>
  );
}

function DetailSection({ title, icon, children }) {
  return (
    <div className="detail-section">
      <h4>{icon} {title}</h4>
      {children}
    </div>
  );
}

function ClaimVerificationDetail({ meta }) {
  const { assessment, ...rest } = meta;
  return (
    <>
      <KVGrid
        data={rest}
        order={['attempted', 'succeeded', 'applied', 'corpus_version', 'retrieval_version', 'relationship_version', 'verifier_version', 'failure_kind']}
      />
      {assessment?.assessments?.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <p style={{ margin: '0 0 8px', fontSize: 11, color: 'var(--text-muted)', fontWeight: 500, letterSpacing: '0.02em' }}>
            Claim assessments ({assessment.assessments.length})
          </p>
          {assessment.assessments.map((a, i) => (
            <div key={i} className="claim-item">
              <KVGrid
                data={{
                  claim: a.claim?.text || '—',
                  status: a.status,
                  relationship: a.relationship || '—',
                  confidence: fmt(a.confidence),
                  reasoning: a.reasoning || '—',
                }}
              />
            </div>
          ))}
        </div>
      )}
    </>
  );
}
