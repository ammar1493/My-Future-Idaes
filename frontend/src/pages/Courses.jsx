import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";

export default function Courses() {
  const [courses, setCourses] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [title, setTitle] = useState("");
  const [error, setError] = useState("");
  const [attendance, setAttendance] = useState(null);
  const [copied, setCopied] = useState(null);

  async function refresh() {
    try {
      setCourses(await api.courses());
      setSessions(await api.sessions());
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function createCourse(e) {
    e.preventDefault();
    if (!title.trim()) return;
    await api.createCourse({ title });
    setTitle("");
    refresh();
  }

  async function scheduleNow(courseId) {
    const now = new Date();
    const end = new Date(now.getTime() + 60 * 60 * 1000);
    await api.createSession({
      course_id: courseId,
      scheduled_start: now.toISOString(),
      scheduled_end: end.toISOString(),
    });
    refresh();
  }

  async function startSession(id) {
    await api.startSession(id);
    refresh();
  }
  async function endSession(id) {
    await api.endSession(id);
    refresh();
  }
  async function viewAttendance(id) {
    const rows = await api.sessionAttendance(id, true);
    setAttendance({ id, rows });
  }

  async function copyInvite(roomId) {
    // The shareable join link — anyone enrolled can open it, sign in, and the
    // platform drops them straight into the live room.
    const url = `${window.location.origin}/room/${roomId}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(roomId);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      window.prompt("Copy this invite link:", url);
    }
  }

  return (
    <div>
      <h1>Courses & Sessions</h1>
      {error && <div className="error">{error}</div>}

      <form className="row gap" onSubmit={createCourse}>
        <input
          placeholder="New course title…"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <button className="btn primary">Add course</button>
      </form>

      <div className="course-list">
        {courses.map((c) => {
          const cSessions = sessions.filter((s) => s.course_id === c.id);
          return (
            <div key={c.id} className="panel">
              <div className="row between">
                <h3>{c.title}</h3>
                <button className="btn small" onClick={() => scheduleNow(c.id)}>
                  + Session now
                </button>
              </div>
              {cSessions.length === 0 && <p className="muted">No sessions.</p>}
              {cSessions.map((s) => (
                <div key={s.id} className="session-row">
                  <span className={`pill ${s.status === "live" ? "ok" : "muted-pill"}`}>
                    {s.status}
                  </span>
                  <span className="grow">{s.title}</span>
                  {s.status === "scheduled" && (
                    <button className="btn small" onClick={() => startSession(s.id)}>
                      Start
                    </button>
                  )}
                  {s.status === "live" && (
                    <>
                      <Link className="btn small" to={`/room/${s.room_id}`}>
                        Join
                      </Link>
                      <button className="btn small" onClick={() => copyInvite(s.room_id)}>
                        {copied === s.room_id ? "✓ Copied" : "Copy link"}
                      </button>
                      <button className="btn small danger" onClick={() => endSession(s.id)}>
                        End
                      </button>
                    </>
                  )}
                  <button className="btn small ghost" onClick={() => viewAttendance(s.id)}>
                    Attendance
                  </button>
                </div>
              ))}
            </div>
          );
        })}
      </div>

      {attendance && (
        <div className="modal" onClick={() => setAttendance(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <h3>Attendance — session #{attendance.id}</h3>
            {attendance.rows.length === 0 ? (
              <p className="muted">No attendance recorded yet.</p>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Minutes</th>
                    <th>Ratio</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {attendance.rows.map((r) => (
                    <tr key={r.id}>
                      <td>#{r.user_id}</td>
                      <td>{Math.round(r.seconds_present / 60)}</td>
                      <td>{Math.round(r.attendance_ratio * 100)}%</td>
                      <td>
                        <span className={`pill ${r.status === "present" ? "ok" : r.status === "partial" ? "warn" : "muted-pill"}`}>
                          {r.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <button className="btn" onClick={() => setAttendance(null)}>
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
