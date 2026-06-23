import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import Logo from "../components/Logo.jsx";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  // After login, return to the page the invite link pointed at (default: dashboard).
  const dest = location.state?.from?.pathname || "/";
  const [email, setEmail] = useState("coordinator@neftenergies.com");
  const [password, setPassword] = useState("password");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email, password);
      navigate(dest, { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <form className="auth-card" onSubmit={submit}>
        <Logo size={64} variant="stack" />
        <p className="tagline muted">Live Training Platform · Coordinator console</p>
        <label>Email</label>
        <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" />
        <label>Password</label>
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          type="password"
        />
        {error && <div className="error">{error}</div>}
        <button className="btn primary" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="hint muted">Demo: coordinator@neftenergies.com / password</p>
      </form>
    </div>
  );
}
