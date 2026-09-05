import { useEffect, useRef, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { apiFetch } from '../api';
import { Sun, Moon } from 'lucide-react';
import LoginBrandPanel from '../components/login/LoginBrandPanel';
import LoginPanelDecor from '../components/login/LoginPanelDecor';
import './LoginPage.css';

const EXAMPLE_ROLES = ['clinician', 'marketing', 'admin', 'employee'];

// Google Identity Services client ID (from apps/web-src/.env.production).
// When unset, the Google button is hidden and only the dev-mode form shows.
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

/**
 * Standalone login page (Concord-inspired split layout).
 * Calls POST /auth/dev-token. Token is kept in memory only.
 */
export default function LoginPage() {
  const { auth, login } = useAuth();
  const { resolved, toggleTheme } = useTheme();
  const [role, setRole] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const googleButtonRef = useRef(null);

  async function handleSubmit(e) {
    e.preventDefault();
    const r = role.trim();
    if (!r) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch('/auth/dev-token', {
        method: 'POST',
        body: { role: r },
      });
      if (!data?.token) throw { status: 0, message: 'No token in response.', type: 'server' };
      login(data.token, r);
    } catch (err) {
      if (err.status === 404) {
        setError(
          'Dev token issuance is disabled on this server. ' +
          'Set AUTH_DEV_MODE=true in .env and restart the backend to enable it.'
        );
      } else {
        setError(err.message || 'Login failed — check the backend is running.');
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // No Google button when this build has no client ID configured.
    if (!GOOGLE_CLIENT_ID) return undefined;

    let cancelled = false;
    let retryTimer = null;

    // Google Identity Services resolves the chosen Google account to an ID
    // token that the backend exchanges for a normal session token.
    async function handleCredential(response) {
      const credential = response?.credential;
      if (!credential) {
        setError('Google sign-in returned no credential — please try again.');
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const data = await apiFetch('/auth/google', {
          method: 'POST',
          body: { id_token: credential },
        });
        if (!data?.token) throw { status: 0, message: 'No token in response.', type: 'server' };
        login(data.token, data.role);
      } catch (err) {
        setError(err.message || 'Login failed — check the backend is running.');
      } finally {
        setLoading(false);
      }
    }

    function mountButton() {
      if (cancelled || !googleButtonRef.current) return;
      // gsi/client is loaded with async defer — retry until it becomes ready.
      if (!window.google?.accounts?.id) {
        retryTimer = window.setTimeout(mountButton, 250);
        return;
      }
      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: handleCredential,
      });
      window.google.accounts.id.renderButton(googleButtonRef.current, {
        theme: 'outline',
        size: 'large',
        width: 280,
        shape: 'rectangular',
        text: 'continue_with',
        logo_alignment: 'left',
      });
    }

    mountButton();

    return () => {
      cancelled = true;
      if (retryTimer) window.clearTimeout(retryTimer);
      window.google?.accounts?.id?.cancel();
    };
  }, [GOOGLE_CLIENT_ID, login]);

  if (auth) {
    return (
      <div className="login-loading">
        <p className="login-loading-name">ContextGuard</p>
        <span className="login-loader-track" aria-hidden="true">
          <span className="login-loader-bar" />
        </span>
      </div>
    );
  }

  return (
    <div className="login-screen">
      <LoginBrandPanel />

      <main className="login-form-side">
        <LoginPanelDecor />

        <button
          type="button"
          className="login-theme-toggle"
          onClick={toggleTheme}
          aria-label={resolved === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {resolved === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
        </button>

        <div className="login-form-wrap">
          <p className="login-mobile-brand">ContextGuard</p>

          <h1 className="login-form-title">Sign in</h1>
          <span className="login-form-rule" aria-hidden="true" />

          <form className="login-form" onSubmit={handleSubmit}>
            <div className="login-field">
              <label htmlFor="login-role">Role</label>
              <input
                id="login-role"
                type="text"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                placeholder="e.g. clinician, marketing, admin…"
                autoComplete="off"
                spellCheck="false"
                autoFocus
              />
            </div>

            <div className="login-chip-row">
              {EXAMPLE_ROLES.map((r) => (
                <button
                  key={r}
                  type="button"
                  className="login-chip"
                  onClick={() => setRole(r)}
                  aria-label={`Set role to ${r}`}
                >
                  {r}
                </button>
              ))}
            </div>

            {error && <p className="login-error">{error}</p>}

            <button
              type="submit"
              className="login-submit"
              disabled={loading || !role.trim()}
              aria-busy={loading}
            >
              {loading ? 'Minting token…' : 'Continue'}
            </button>
          </form>

          {GOOGLE_CLIENT_ID ? (
            <>
              <div className="login-divider" role="separator">
                <span>or continue with Google</span>
              </div>
              <div className="login-google" ref={googleButtonRef} />
            </>
          ) : (
            <p className="login-google-note">
              Google sign-in is not configured for this deployment.
            </p>
          )}

          <p className="login-footnote">
            Dev-mode JWT via <code>POST /auth/dev-token</code>. Token stays in page memory only.
            Role is embedded in the JWT for policy enforcement.
          </p>
        </div>
      </main>
    </div>
  );
}
