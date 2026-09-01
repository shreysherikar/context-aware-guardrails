/**
 * Inline highlights for GxP compliance issues.
 * Each highlight shows severity color and GxP frameworks on hover.
 */
export default function GxpHighlightedText({ text, highlights = [] }) {
  if (!highlights.length) {
    return <span className="gxp-plain-text">{text}</span>;
  }

  const sorted = [...highlights].sort((a, b) => a.start - b.start);
  const parts = [];
  let cursor = 0;

  sorted.forEach((h, index) => {
    if (h.start > cursor) {
      parts.push(<span key={`pre-${index}`}>{text.slice(cursor, h.start)}</span>);
    }
    const frameworks = (h.gxp_frameworks || []).join(', ');
    const title = [
      frameworks && `GxP: ${frameworks}`,
      h.reason,
      h.suggested_replacement && `→ ${h.suggested_replacement}`,
    ].filter(Boolean).join('\n');

    parts.push(
      <mark
        key={`hl-${index}`}
        className={`gxp-highlight gxp-highlight--${h.severity || 'medium'}`}
        title={title}
        data-frameworks={frameworks}
      >
        {text.slice(h.start, h.end)}
      </mark>,
    );
    cursor = h.end;
  });

  if (cursor < text.length) {
    parts.push(<span key="tail">{text.slice(cursor)}</span>);
  }

  return <span className="gxp-highlighted-text">{parts}</span>;
}
