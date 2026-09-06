import { useEffect, useRef, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { apiFetch } from '../api';
import { Sun, Moon } from 'lucide-react';
import LoginBrandPanel from '../components/login/LoginBrandPanel';
import LoginPanelDecor from '../components/login/LoginPanelDecor';
import './LoginPage.css';

// Google Identity Services client ID (from apps/web-src/.env.production).
// When unset, the Google button is hidden and only the email/password form shows.
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;
const DEMO_EMAIL = 'demo@contextguard.local';
const DEMO_PASSWORD = 'demo';

/**
 * Standalone login page (Concord-inspired split layout).
 * Calls POST /auth/login. Token is kept in memory only.
 */
export default function LoginPage() {
  const { auth, login } = useAuth();
  const { resolved, toggleTheme } = useTheme();
  const [email, setEmail] = useState(DEMO_EMAIL);
  const [password, setPassword] = useState(DEMO_PASSWORD);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const googleButtonRef = useRef(null);

  async function signInWith(nextEmail, nextPassword) {
    const trimmedEmail = (nextEmail || '').trim();
    if (!trimmedEmail || !nextPassword) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch('/auth/login', {
        method: 'POST',
        body: { email: trimmedEmail, password: nextPassword },
      });
      if (!data?.token) throw { status: 0, message: 'No token in response.', type: 'server' };
      login(data.token, data.role);
    } catch (err) {
      if (err.status === 401) {
        setError('Email or password is incorrect.');
      } else {
        setError(err.message || 'Login failed — check the backend is running.');
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    await signInWith(email, password);
  }

  async function handleDemo() {
    setEmail(DEMO_EMAIL);
    setPassword(DEMO_PASSWORD);
    await signInWith(DEMO_EMAIL, DEMO_PASSWORD);
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

          <h1 className="login-form-title">Welcome back</h1>
          <span className="login-form-rule" aria-hidden="true" />

          <form className="login-form" onSubmit={handleSubmit}>
            <div className="login-field">
              <label htmlFor="login-email">Email</label>
              <input
                id="login-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                autoComplete="username"
                spellCheck="false"
                autoFocus
              />
            </div>

            <div className="login-field">
              <label htmlFor="login-password">Password</label>
              <input
                id="login-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                autoComplete="current-password"
              />
            </div>

            {error && <p className="login-error">{error}</p>}

            <button
              type="submit"
              className="login-submit"
              disabled={loading || !email.trim() || !password}
              aria-busy={loading}
            >
              {loading ? 'Signing in…' : 'Continue'}
            </button>
            <button
              type="button"
              className="login-demo"
              onClick={handleDemo}
              disabled={loading}
            >
              Sign in as demo
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
            Dummy account: <code>{DEMO_EMAIL}</code> / <code>{DEMO_PASSWORD}</code>
            (clinician). Token stays in page memory only.
          </p>
        </div>
      </main>
    </div>
  );
}
