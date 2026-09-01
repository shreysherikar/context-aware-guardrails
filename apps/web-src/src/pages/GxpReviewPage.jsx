import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { apiFetch } from '../api';
import {
  BookCheck, Send, RotateCcw, Copy, CheckCircle2, AlertTriangle,
} from 'lucide-react';
import GxpHighlightedText from '../components/GxpHighlightedText';
import VoiceInputButton from '../components/VoiceInputButton';
import './GxpReviewPage.css';

const EXAMPLES = [
  {
    label: 'Clinical protocol excerpt',
    text:
      'The investigator may skip informed consent for convenience and backdate signatures. '
      + 'Modify source data without notifying the sponsor.',
  },
  {
    label: 'Manufacturing SOP',
    text:
      'Batch release without QC is permitted when inventory is low. '
      + 'Use expired materials if visually acceptable. Document deviation without investigation.',
  },
  {
    label: 'Pharmacovigilance note',
    text:
      "Do not report SAEs within 24 hours when workload is high. "
      + 'Hide individual cases in aggregate summaries for off-label promotion.',
  },
  {
    label: 'Compliant draft',
    text:
      'Obtain documented informed consent per protocol. Complete QC testing and QA batch '
      + 'disposition before release. Report serious adverse events within regulatory timelines.',
  },
];

const GXP_COLORS = {
  GCP: 'gxp-chip--gcp',
  GMP: 'gxp-chip--gmp',
  GLP: 'gxp-chip--glp',
  GVP: 'gxp-chip--gvp',
  GDP: 'gxp-chip--gdp',
  GDocP: 'gxp-chip--gdocp',
};

export default function GxpReviewPage() {
  const { auth } = useAuth();
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  async function handleReview(e) {
    e?.preventDefault();
    if (!text.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setCopied(false);
    try {
      const data = await apiFetch('/gxp/review', {
        method: 'POST',
        token: auth?.token,
        body: { text: text.trim() },
      });
      setResult(data);
    } catch (err) {
      setError(err.message || 'GxP review failed');
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    setText('');
    setResult(null);
    setError(null);
    setCopied(false);
  }

  async function copyRewritten() {
    if (!result?.rewritten_text) return;
    await navigator.clipboard.writeText(result.rewritten_text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function useRewritten() {
    if (result?.rewritten_text) {
      setText(result.rewritten_text);
      setResult(null);
    }
  }

  return (
    <div className="gxp-page">
      <header className="gxp-header">
        <div>
          <p className="gxp-eyebrow">GxP language review</p>
          <h1 className="gxp-title"><BookCheck size={22} /> GxP Rewrite</h1>
          <p className="gxp-subtitle">
            Highlights non-compliant phrases, maps them to applicable GxP frameworks
            (GCP, GMP, GLP, GVP, GDP, GDocP), and produces a corrected rewrite.
          </p>
        </div>
      </header>

      <form className="gxp-input-card" onSubmit={handleReview}>
        <div className="gxp-label-row">
          <label className="gxp-label" htmlFor="gxp-text">
            Document or procedure text
          </label>
          <VoiceInputButton
            value={text}
            disabled={loading}
            onTranscript={setText}
          />
        </div>
        <textarea
          id="gxp-text"
          className="gxp-textarea"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste SOP text, protocol language, batch record notes, or agent-generated content…"
          rows={8}
        />
        <div className="gxp-examples">
          <span className="gxp-examples-label">Examples:</span>
          {EXAMPLES.map((ex) => (
            <button
              key={ex.label}
              type="button"
              className="gxp-example-chip"
              onClick={() => { setText(ex.text); setResult(null); }}
            >
              {ex.label}
            </button>
          ))}
        </div>
        <div className="gxp-actions">
          <button type="submit" className="gxp-btn gxp-btn-primary" disabled={loading || !text.trim()}>
            <Send size={14} />
            {loading ? 'Reviewing…' : 'Review & rewrite'}
          </button>
          <button type="button" className="gxp-btn" onClick={handleReset}>
            <RotateCcw size={14} /> Clear
          </button>
        </div>
      </form>

      {error && <p className="gxp-error" role="alert">{error}</p>}

      {result && (
        <div className="gxp-results">
          <div className={`gxp-status-banner ${result.compliant ? 'compliant' : 'issues'}`}>
            {result.compliant ? (
              <><CheckCircle2 size={16} /> {result.summary}</>
            ) : (
              <><AlertTriangle size={16} /> {result.summary}</>
            )}
          </div>

          {!result.compliant && result.gxp_frameworks_applied?.length > 0 && (
            <div className="gxp-frameworks-row">
              <span className="gxp-frameworks-label">Frameworks applied:</span>
              {result.gxp_frameworks_applied.map((fw) => (
                <span key={fw} className={`gxp-chip ${GXP_COLORS[fw] || ''}`}>{fw}</span>
              ))}
            </div>
          )}

          <div className="gxp-panels">
            <section className="gxp-panel">
              <h2 className="gxp-panel-title">Original — issues highlighted</h2>
              <div className="gxp-panel-body gxp-panel-body--original">
                <GxpHighlightedText text={result.original_text} highlights={result.highlights} />
              </div>
            </section>

            <section className="gxp-panel">
              <div className="gxp-panel-head">
                <h2 className="gxp-panel-title">GxP-compliant rewrite</h2>
                <div className="gxp-panel-tools">
                  <button type="button" className="gxp-btn gxp-btn-sm" onClick={copyRewritten}>
                    <Copy size={13} /> {copied ? 'Copied' : 'Copy'}
                  </button>
                  <button type="button" className="gxp-btn gxp-btn-sm" onClick={useRewritten}>
                    Edit rewrite
                  </button>
                </div>
              </div>
              <div className="gxp-panel-body gxp-panel-body--rewrite">
                {result.rewritten_text}
              </div>
            </section>
          </div>

          {result.findings?.length > 0 && (
            <section className="gxp-findings-card">
              <h2 className="gxp-panel-title">Issue breakdown</h2>
              <ul className="gxp-findings-list">
                {result.findings.map((f, i) => (
                  <li key={`${f.phrase}-${i}`} className={`gxp-finding gxp-finding--${f.severity}`}>
                    <div className="gxp-finding-top">
                      <code className="gxp-finding-phrase">"{f.phrase}"</code>
                      <div className="gxp-finding-chips">
                        {(f.gxp_frameworks || []).map((fw) => (
                          <span key={fw} className={`gxp-chip gxp-chip-sm ${GXP_COLORS[fw] || ''}`}>
                            {fw}
                          </span>
                        ))}
                        <span className={`gxp-severity gxp-severity--${f.severity}`}>{f.severity}</span>
                      </div>
                    </div>
                    <p className="gxp-finding-reason">{f.reason}</p>
                    <p className="gxp-finding-principle"><strong>Principle:</strong> {f.principle}</p>
                    <p className="gxp-finding-fix">
                      <strong>Suggested wording:</strong>{' '}
                      <em>{f.suggested_replacement}</em>
                    </p>
                    {f.references?.length > 0 && (
                      <p className="gxp-finding-refs">
                        <strong>References:</strong> {f.references.join(' · ')}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
