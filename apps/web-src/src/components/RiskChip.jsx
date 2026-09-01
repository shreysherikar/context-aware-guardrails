/**
 * Risk-level severity pill: NONE → CRITICAL.
 */
const LEVEL_CLASS = {
  NONE:     'risk-none',
  LOW:      'risk-low',
  MEDIUM:   'risk-medium',
  HIGH:     'risk-high',
  CRITICAL: 'risk-critical',
};

export default function RiskChip({ level }) {
  const cls = `risk-chip ${LEVEL_CLASS[level] || 'risk-none'}`;
  return (
    <span className={cls} aria-label={`Risk level: ${level || 'unknown'}`}>
      {level || '—'}
    </span>
  );
}
