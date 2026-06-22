import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, getToken, wsUrl } from "../api/client";

// The coordinator's single pane of glass across every running course.
// One snapshot fetch + a live websocket that patches per-room headcounts as
// students join and leave — so 100 simultaneous sessions stay current with no
// polling and no manual register.
export default function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);

  useEffect(() => {
    api.dashboardSummary().then(setSummary).catch((e) => setError(e.message));

    const ws = new WebSocket(wsUrl(`/api/dashboard/live`));
    wsRef.current = ws;
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      if (msg.type === "snapshot") {
        setSummary(msg.data);
      } else if (msg.type === "presence") {
        // Patch a single room's live count in place.
        setSummary((prev) => {
          if (!prev) return prev;
          const tiles = prev.tiles.map((t) =>
            t.room_id === msg.room_id ? { ...t, live_now: msg.live_now } : t
          );
          const total = tiles.reduce((a, t) => a + t.live_now, 0);
          return { ...prev, tiles, total_participants_live: total };
        });
      }
    };
    // Keep-alive ping.
    const ping = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send("ping");
    }, 25000);

    return () => {
      clearInterval(ping);
      ws.close();
    };
  }, []);

  if (error) return <div className="error">⚠ {error}</div>;
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
