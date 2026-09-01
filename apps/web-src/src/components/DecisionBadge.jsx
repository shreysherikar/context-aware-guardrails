/**
 * Colored decision badge.
 * size='large' → big hero badge  |  size='small' → compact inline badge
 */
const HUMAN_LABELS = {
  ALLOW: 'Allowed',
  REWRITE: 'Rewritten',
  BLOCK: 'Blocked',
  REVIEW: 'Review',
  CLARIFY: 'Clarify',
  UNKNOWN: 'Unknown',
};

export default function DecisionBadge({ action, size = 'large', showLabel = true }) {
  const act = action || 'UNKNOWN';
  const cls = `badge badge-${act}${size === 'small' ? ' badge-sm' : ''}`;
  const label = showLabel ? (HUMAN_LABELS[act] || act) : act;
  return (
    <span className={cls} aria-label={`Decision: ${act}`} title={act}>
      {label}
    </span>
  );
}
