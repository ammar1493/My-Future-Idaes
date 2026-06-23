import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext.jsx";
import Logo from "../components/Logo.jsx";

// Public student signup. After creating the account we log in and return to
// wherever the user was headed (e.g. a class invite link).
export default function Register() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const dest = location.state?.from?.pathname || "/";

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.register({ full_name: fullName, email, password });
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
        <p className="tagline muted">Create your student account</p>
        <label>Full name</label>
        <input value={fullName} onChange={(e) => setFullName(e.target.value)} required />
        <label>Email</label>
        <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />
        <label>Password</label>
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          type="password"
          required
        />
        {error && <div className="error">{error}</div>}
        <button className="btn primary" disabled={busy}>
          {busy ? "Creating…" : "Create account"}
        </button>
        <p className="hint muted">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
