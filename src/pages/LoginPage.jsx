import { useState, useEffect, useRef } from 'react';
import { API_BASE, login, loginWithGoogle } from '../utils/auth';

const GOOGLE_SCRIPT = 'https://accounts.google.com/gsi/client';

// Loads Google's sign in script once and resolves when window.google is ready.
function loadGoogleScript() {
  return new Promise((resolve, reject) => {
    if (window.google && window.google.accounts) {
      resolve();
      return;
    }
    let tag = document.querySelector(`script[src="${GOOGLE_SCRIPT}"]`);
    if (!tag) {
      tag = document.createElement('script');
      tag.src = GOOGLE_SCRIPT;
      tag.async = true;
      tag.defer = true;
      document.head.appendChild(tag);
    }
    tag.addEventListener('load', () => resolve());
    tag.addEventListener('error', () => reject(new Error('Could not load Google sign in')));
  });
}

function LoginPage({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [googleReady, setGoogleReady] = useState(false);
  const googleButtonRef = useRef(null);

  // Ask the backend whether Google sign in is switched on and which client ID to use.
  useEffect(() => {
    let cancelled = false;

    async function setUpGoogle() {
      try {
        const res = await fetch(`${API_BASE}/api/auth/google/config`);
        if (!res.ok) return;
        const config = await res.json();
        if (!config.enabled || !config.client_id) return;
        await loadGoogleScript();
        if (cancelled || !googleButtonRef.current) return;

        window.google.accounts.id.initialize({
          client_id: config.client_id,
          callback: async response => {
            setError('');
            setSubmitting(true);
            try {
              const name = await loginWithGoogle(response.credential);
              onLogin(name);
            } catch (err) {
              setError(err.message);
            } finally {
              setSubmitting(false);
            }
          },
        });
        window.google.accounts.id.renderButton(googleButtonRef.current, {
          type: 'standard',
          theme: 'outline',
          size: 'large',
          text: 'continue_with',
          shape: 'pill',
          width: 320,
        });
        setGoogleReady(true);
      } catch (err) {
        // Google is optional: password login keeps working if this fails.
      }
    }

    setUpGoogle();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');

    if (!username.trim() || !password) {
      setError('Enter a username and password.');
      return;
    }

    setSubmitting(true);
    try {
      const loggedInUsername = await login(username.trim(), password);
      onLogin(loggedInUsername);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-screen">
      <form className="login-card" onSubmit={handleSubmit}>
        <div className="brand">SEDAYU ONE</div>
        <h1>QA Dashboard</h1>

        <div className="control-group">
          <label>Username</label>
          <input
            type="text"
            value={username}
            onChange={e => setUsername(e.target.value)}
            autoFocus
          />
        </div>

        <div className="control-group">
          <label>Password</label>
          <input
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
          />
        </div>

        {error && <div className="login-error">{error}</div>}

        <button className="btn btn-primary" type="submit" disabled={submitting}>
          {submitting ? 'Signing in.' : 'Sign in'}
        </button>

        <div style={{ display: googleReady ? 'block' : 'none', marginTop: 16 }}>
          <div style={{ textAlign: 'center', fontSize: 12, opacity: 0.7, marginBottom: 10 }}>or</div>
          <div ref={googleButtonRef} style={{ display: 'flex', justifyContent: 'center' }} />
        </div>
      </form>

      <img
        className="login-page-logo"
        src="/logos/main-logo-white.png"
        alt=""
      />
    </div>
  );
}

export default LoginPage;