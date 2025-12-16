import React, { useState } from "react";

const API_BASE = "/api";

export default function LoginView({ onSuccess }) {
  const [authInfo, setAuthInfo] = React.useState(null);
  const [error, setError] = useState(null);
  const [info, setInfo] = useState(null);
  const [loadingSend, setLoadingSend] = useState(false);
  const [loadingLogin, setLoadingLogin] = useState(false);
  const [ready, setReady] = useState(false);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const autoLogged = React.useRef(false);

  React.useEffect(() => {
    const loadConfig = async () => {
      try {
        const resp = await fetch(`${API_BASE}/auth/config`);
        if (resp.ok) {
          const data = await resp.json();
          setAuthInfo(data);
        }
      } catch (err) {
        console.error("auth config failed", err);
        setError("Could not load auth config. Check connection and retry.");
      }
      setReady(true);
    };
    loadConfig();
  }, []);

  React.useEffect(() => {
    // Auto-bypass login if backend auth is disabled (dev/local mode).
    if (ready && authInfo && authInfo.auth_enabled === false && !autoLogged.current) {
      autoLogged.current = true;
      onSuccess({ token: "", role: "admin", email: "insecure@local" });
    }
  }, [ready, authInfo, onSuccess]);

  const handleSendCode = async () => {
    setError(null);
    setInfo(null);
    if (!email.trim()) {
      setError("Enter a valid work email.");
      return;
    }
    setLoadingSend(true);
    try {
      const resp = await fetch(`${API_BASE}/auth/request-code`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      });
      if (!resp.ok) throw new Error("Service is unavailable. Try again.");
      setSent(true);
      const deliveryHint =
        authInfo?.email_delivery === "smtp"
          ? "Check inbox/spam. The code stays valid for a few minutes."
          : "DEV: code is also in backend logs and data/login_codes/*.txt.";
      setInfo(`If the email is verified, we sent a one-time code. ${deliveryHint}`);
    } catch (err) {
      setError(err.message || "Could not send the code.");
    } finally {
      setLoadingSend(false);
    }
  };

  const handleEmailLogin = async (e) => {
    e.preventDefault();
    setError(null);
    setInfo(null);
    if (!email.trim() || !code.trim()) {
      setError("Email and code are required.");
      return;
    }
    setLoadingLogin(true);
    try {
      const resp = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          code: code.trim(),
        }),
      });
      if (!resp.ok) {
        const msg = resp.status === 401 ? "Invalid email or code." : "Service is unavailable. Try later.";
        throw new Error(msg);
      }
      const data = await resp.json();
      onSuccess(data);
    } catch (err) {
      setError(err.message || "Login failed.");
    } finally {
      setLoadingLogin(false);
    }
  };

  return (
    <div className="login-wrapper">
      <div className="login-card">
        <div className="brand-mark-wrap">
          <img className="brand-mark" src="/media/brand/wordmark-tight.webp" alt="Jack OutReacher" />
        </div>
        <div className="login-form-panel">
          <h2>Secure Access</h2>
          <form onSubmit={handleEmailLogin}>
            <label>
              Work email
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.com"
                disabled={loadingSend || loadingLogin}
                required
              />
            </label>
            <button type="button" className="sso-btn" onClick={handleSendCode} disabled={loadingSend || !email.trim()}>
              {!ready ? "..." : loadingSend ? "Sending..." : sent ? "Send again" : "Get code"}
            </button>

            <label>
              Code from email
              <input
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="One-time code"
                disabled={loadingLogin}
                inputMode="numeric"
              />
            </label>
            <button type="submit" disabled={loadingLogin}>
              {loadingLogin ? "Verifying..." : "Sign in"}
            </button>
          </form>
          {info && <div className="sso-hint">{info}</div>}
          {error && <div className="error">{error}</div>}
        </div>
      </div>
    </div>
  );
}
