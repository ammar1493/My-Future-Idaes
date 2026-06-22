import { Suspense, lazy, useEffect, useState } from "react";
import { api } from "../api/client";

// Lazy-loaded so the heavy LiveKit libraries are only fetched when a user
// actually enters a room — keeps the dashboard/login bundle small.
const RoomLiveKit = lazy(() => import("./RoomLiveKit.jsx"));
const RoomMesh = lazy(() => import("./RoomMesh.jsx"));

// Picks the video backend at runtime: LiveKit when the server has it
// configured, otherwise the built-in WebRTC mesh. Either way the URL is the
// same shareable /room/:roomId join link.
export default function Room() {
  const [cfg, setCfg] = useState(null);

  useEffect(() => {
    api
      .config()
      .then(setCfg)
      .catch(() => setCfg({ livekit_enabled: false }));
  }, []);

  if (!cfg) return <div className="center muted">Loading room…</div>;
  return (
    <Suspense fallback={<div className="center muted">Loading room…</div>}>
      {cfg.livekit_enabled ? <RoomLiveKit /> : <RoomMesh />}
    </Suspense>
  );
}
