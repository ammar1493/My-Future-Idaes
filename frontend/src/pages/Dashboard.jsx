import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";

// The coordinator's single pane of glass across every running course. Live
// headcounts are derived server-side from the presence-event log (fed by
// LiveKit webhooks), so a short poll keeps all 100 simultaneous sessions
// current — no manual register, and no persistent socket required (serverless
// friendly).
const POLL_MS = 4000;

export default function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let active = true;

    async function tick() {
      try {
        const data = await api.dashboardSummary();
        if (!active) return;
        setSummary(data);
        setConnected(true);
        setError("");
      } catch (e) {
        if (!active) return;
        setConnected(false);
        setError(e.message);
      }
    }

    tick();
    const timer = setInterval(tick, POLL_MS);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);

  if (error && !summary) return <div className="error">⚠ {error}</div>;
  if (!summary) return <div className="muted">Loading dashboard…</div>;

  return (
    <div>
      <div className="dash-header">
        <h1>Live Operations</h1>
        <span className={`pill ${connected ? "ok" : "warn"}`}>
          {connected ? "live" : "reconnecting…"}
        </span>
      </div>

      <div className="stats">
        <Stat label="Running sessions" value={summary.total_live_sessions} />
        <Stat label="Participants live now" value={summary.total_participants_live} />
        <Stat label="Total courses" value={summary.total_courses} />
      </div>

      {summary.tiles.length === 0 ? (
        <p className="muted">No sessions are live right now.</p>
      ) : (
        <div className="grid">
          {summary.tiles.map((t) => (
            <CourseTile key={t.session_id} tile={t} />
          ))}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="stat-card">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

function CourseTile({ tile }) {
  const ratio = tile.enrolled ? Math.round((tile.live_now / tile.enrolled) * 100) : 0;
  const heat = ratio >= 75 ? "good" : ratio >= 40 ? "mid" : "low";
  return (
    <div className="tile">
      <div className="tile-top">
        <span className="tile-title">{tile.course_title}</span>
        <span className="pill ok small">LIVE</span>
      </div>
      <div className="tile-sub">{tile.session_title}</div>
      <div className="attendance-bar">
        <div className={`fill ${heat}`} style={{ width: `${Math.min(100, ratio)}%` }} />
      </div>
      <div className="tile-foot">
        <span>
          <strong>{tile.live_now}</strong> / {tile.enrolled} present
        </span>
        <Link className="btn small" to={`/room/${tile.room_id}`}>
          Open room
        </Link>
      </div>
    </div>
  );
}
