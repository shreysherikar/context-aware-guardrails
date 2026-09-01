/**
 * Renders user prompt text with inline highlights for guardrail-detected spans.
 */
export default function HighlightedPrompt({ text, highlights = [] }) {
  if (!highlights.length) {
    return <span>{text}</span>;
  }

  const sorted = [...highlights].sort((a, b) => a.start - b.start);
  const parts = [];
  let cursor = 0;

  sorted.forEach((h, index) => {
    if (h.start > cursor) {
      parts.push(<span key={`t-${index}-pre`}>{text.slice(cursor, h.start)}</span>);
    }
    parts.push(
      <mark
        key={`h-${index}`}
        className={`prompt-highlight prompt-highlight--${h.severity || 'medium'}`}
        title={h.reason}
      >
        {text.slice(h.start, h.end)}
      </mark>,
    );
    cursor = h.end;
  });

  if (cursor < text.length) {
    parts.push(<span key="tail">{text.slice(cursor)}</span>);
  }

  return <span className="highlighted-prompt">{parts}</span>;
}
