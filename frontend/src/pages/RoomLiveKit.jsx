import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  LiveKitRoom,
  GridLayout,
  ParticipantTile,
  RoomAudioRenderer,
  ControlBar,
  useTracks,
} from "@livekit/components-react";
import { Track } from "livekit-client";
import "@livekit/components-styles";
import { api } from "../api/client";

// LiveKit-backed room. We fetch a signed join token from our backend (identity =
// user id, room = session.room_id) and connect straight to the LiveKit SFU for
// media. Attendance is captured server-side from LiveKit's join/leave webhooks —
// the browser does nothing special for it.
export default function RoomLiveKit() {
  const { roomId } = useParams();
  const navigate = useNavigate();
  const [conn, setConn] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .joinToken(roomId)
      .then(setConn)
      .catch((e) => setError(e.message));
  }, [roomId]);

  if (error) {
    return (
      <div className="room">
        <header className="room-bar">
          <button className="btn ghost" onClick={() => navigate(-1)}>
            ← Leave
          </button>
          <span className="room-title">Room {roomId}</span>
        </header>
        <div className="error" style={{ padding: 24 }}>
          Could not join: {error}
        </div>
      </div>
    );
  }

  if (!conn) return <div className="center muted">Connecting to room…</div>;

  return (
    <div className="room">
      <header className="room-bar">
        <button className="btn ghost" onClick={() => navigate(-1)}>
          ← Leave
        </button>
        <span className="room-title">Room {roomId}</span>
        <span className="pill ok">livekit</span>
      </header>
      <LiveKitRoom
        token={conn.token}
        serverUrl={conn.url}
        connect
        video
        audio
        onDisconnected={() => navigate(-1)}
        style={{ flex: 1, display: "flex", flexDirection: "column" }}
      >
        <Stage />
        <RoomAudioRenderer />
        <ControlBar />
      </LiveKitRoom>
    </div>
  );
}

function Stage() {
  const tracks = useTracks(
    [
      { source: Track.Source.Camera, withPlaceholder: true },
      { source: Track.Source.ScreenShare, withPlaceholder: false },
    ],
    { onlySubscribed: false }
  );
  return (
    <GridLayout tracks={tracks} style={{ flex: 1 }}>
      <ParticipantTile />
    </GridLayout>
  );
}
