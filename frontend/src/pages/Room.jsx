import { Suspense, lazy } from "react";

// Live video room (LiveKit). Lazy-loaded so the LiveKit libraries are only
// fetched when a user actually enters a room.
const RoomLiveKit = lazy(() => import("./RoomLiveKit.jsx"));

export default function Room() {
  return (
    <Suspense fallback={<div className="center muted">Loading room…</div>}>
      <RoomLiveKit />
    </Suspense>
  );
}
