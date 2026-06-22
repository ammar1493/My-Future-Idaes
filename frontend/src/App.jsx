import { Navigate, Route, Routes, Link, useNavigate } from "react-router-dom";
import { useAuth } from "./context/AuthContext.jsx";
import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Courses from "./pages/Courses.jsx";
import Room from "./pages/Room.jsx";

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="center muted">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function Shell({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <div>
      <header className="topbar">
        <div className="brand">● LiveTrain</div>
        <nav>
          <Link to="/">Dashboard</Link>
          <Link to="/courses">Courses</Link>
        </nav>
        <div className="spacer" />
        <span className="muted">
          {user?.full_name} · {user?.role}
        </span>
        <button
          className="btn ghost"
          onClick={() => {
            logout();
            navigate("/login");
          }}
        >
          Sign out
        </button>
      </header>
      <main className="content">{children}</main>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <Protected>
            <Shell>
              <Dashboard />
            </Shell>
          </Protected>
        }
      />
      <Route
        path="/courses"
        element={
          <Protected>
            <Shell>
              <Courses />
            </Shell>
          </Protected>
        }
      />
      <Route
        path="/room/:roomId"
        element={
          <Protected>
            <Room />
          </Protected>
        }
      />
    </Routes>
  );
}
