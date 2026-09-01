/** Left brand panel on the login page — Concord-inspired layout. */
import brandLogo from '../../assets/brand-logo.png';

export default function LoginBrandPanel() {
  return (
    <aside className="login-brand-panel" aria-hidden="false">
      <div className="login-brand-art" aria-hidden="true">
        <div className="login-brand-gradient" />
        <div className="login-brand-glow" />

        <svg
          className="login-brand-contours"
          viewBox="0 0 560 760"
          preserveAspectRatio="xMidYMid slice"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path d="M-20 180 C80 120, 160 220, 280 180 S480 100, 600 160" stroke="currentColor" strokeWidth="1" />
          <path d="M-40 280 C100 220, 200 320, 320 270 S520 190, 640 250" stroke="currentColor" strokeWidth="1" />
          <path d="M-10 380 C120 330, 220 420, 340 370 S500 290, 620 340" stroke="currentColor" strokeWidth="1" />
          <path d="M0 480 C140 430, 240 520, 360 470 S520 390, 650 450" stroke="currentColor" strokeWidth="1" />
          <path d="M20 580 C160 530, 260 610, 380 560 S540 490, 660 550" stroke="currentColor" strokeWidth="1" />
          <path d="M40 680 C180 630, 280 700, 400 650 S560 580, 680 640" stroke="currentColor" strokeWidth="0.75" opacity="0.7" />
        </svg>

        <svg className="login-brand-arc" viewBox="0 0 200 200" fill="none">
          <circle cx="100" cy="100" r="78" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 9" />
          <circle cx="100" cy="100" r="54" stroke="currentColor" strokeWidth="1" />
          <path d="M100 22 V46 M100 154 V178 M22 100 H46 M154 100 H178" stroke="currentColor" strokeWidth="1" opacity="0.5" />
        </svg>

        <svg className="login-brand-curve" viewBox="0 0 200 200" fill="none">
          <path
            d="M20 160 C60 120, 80 60, 130 40 C160 28, 185 45, 190 75"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
          <path d="M30 170 C70 135, 95 85, 145 65" stroke="currentColor" strokeWidth="1" opacity="0.55" />
          <circle cx="190" cy="75" r="4" fill="currentColor" opacity="0.35" />
        </svg>

        <svg className="login-brand-nodes" viewBox="0 0 560 760" preserveAspectRatio="xMidYMid slice">
          {[
            [420, 120, 140, 200],
            [140, 200, 220, 280],
            [220, 280, 380, 240],
            [380, 240, 480, 360],
            [120, 420, 240, 500],
            [240, 500, 360, 440],
          ].map(([x1, y1, x2, y2], i) => (
            <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="currentColor" strokeWidth="0.75" opacity="0.6" />
          ))}
          {[
            [420, 120],
            [140, 200],
            [220, 280],
            [380, 240],
            [480, 360],
            [120, 420],
            [240, 500],
            [360, 440],
          ].map(([cx, cy], i) => (
            <circle key={i} cx={cx} cy={cy} r="2" fill="currentColor" opacity="0.5" />
          ))}
        </svg>

        <div className="login-brand-pool" />
      </div>

      <div className="login-brand-hero">
        <img src={brandLogo} alt="Novo Nordisk" className="login-brand-logo" />
        <h1 className="login-brand-name">ContextGuard</h1>
        <p className="login-brand-eyebrow">Policy layer</p>
      </div>

      <div className="login-brand-foot">
        <p className="login-brand-tagline">
          Risk classification, claim verification, and audit — in one pipeline.
        </p>
        <p className="login-brand-meta">JWT · RBAC · Audit trail</p>
      </div>
    </aside>
  );
}
