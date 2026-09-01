import { useState, useEffect, useRef } from 'react';

/**
 * Live health indicator. Polls GET /health every 15 s.
 * Green = ok, red = unreachable, grey = pending.
 * Color is always paired with a text label when withLabel is true.
 */
export default function HealthDot({ withLabel = false }) {
  const [ok, setOk] = useState(null);
  const timer = useRef(null);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const res = await fetch('/health', { cache: 'no-store' });
        if (!cancelled) setOk(res.ok);
      } catch {
        if (!cancelled) setOk(false);
      }
    }

    check();
    timer.current = setInterval(check, 15_000);
    return () => { cancelled = true; clearInterval(timer.current); };
  }, []);

  const cls = ok === null ? 'health-dot unknown' : ok ? 'health-dot up' : 'health-dot down';
  const label = ok === null ? 'Checking API…' : ok ? 'API healthy' : 'API unreachable';

  if (!withLabel) {
    return <span className={cls} title={label} aria-label={label} />;
  }

  return (
    <div className="sidebar-health">
      <span className={cls} aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
