import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getToken, wsUrl } from "../api/client";

// Peer-to-peer (mesh) WebRTC room. Each browser connects to our signaling
// websocket, which also records join/leave/heartbeat events — that event log is
// what the attendance engine turns into a register. Media is exchanged directly
// between peers; for large classes, swap the mesh for an SFU without touching
// the attendance layer.
const RTC_CONFIG = {
  iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
};

export default function Room() {
  const { roomId } = useParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState("connecting");
  const [peerIds, setPeerIds] = useState([]);
  const wsRef = useRef(null);
  const peersRef = useRef(new Map()); // peerId -> RTCPeerConnection
  const localStreamRef = useRef(null);
  const localVideoRef = useRef(null);
  const remoteVideosRef = useRef(new Map()); // peerId -> HTMLVideoElement

  useEffect(() => {
    let mounted = true;

    async function start() {
      // Try to grab camera/mic; monitors without a device still join (present).
      try {
        localStreamRef.current = await navigator.mediaDevices.getUserMedia({
          video: true,
          audio: true,
        });
      } catch {
        localStreamRef.current = new MediaStream();
      }
      if (localVideoRef.current && mounted) {
        localVideoRef.current.srcObject = localStreamRef.current;
      }

      const ws = new WebSocket(wsUrl(`/ws/rooms/${roomId}?token=${getToken()}`));
      wsRef.current = ws;

      ws.onopen = () => setStatus("connected");
      ws.onclose = (e) => setStatus(e.code === 4403 ? "room not live" : "disconnected");
      ws.onerror = () => setStatus("error");

      ws.onmessage = async (evt) => {
        const msg = JSON.parse(evt.data);
        switch (msg.type) {
          case "peers":
            // We are the newcomer → initiate an offer to everyone already here.
            for (const pid of msg.peers) await createOffer(pid);
            setPeerIds((p) => [...new Set([...p, ...msg.peers])]);
            break;
          case "peer-joined":
            setPeerIds((p) => [...new Set([...p, msg.peer_id])]);
            break;
          case "peer-left":
            closePeer(msg.peer_id);
            break;
          case "offer":
            await handleOffer(msg.from, msg.sdp);
            break;
          case "answer":
            await peersRef.current.get(msg.from)?.setRemoteDescription(msg.sdp);
            break;
          case "ice-candidate":
            try {
              await peersRef.current.get(msg.from)?.addIceCandidate(msg.candidate);
            } catch {
              /* ignore */
            }
            break;
          default:
            break;
        }
      };

      // Heartbeat keeps attendance accurate even if the tab is closed uncleanly.
      const hb = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "heartbeat" }));
      }, 20000);
      ws._hb = hb;
    }

    function newPeer(peerId) {
      const pc = new RTCPeerConnection(RTC_CONFIG);
      localStreamRef.current
        ?.getTracks()
        .forEach((track) => pc.addTrack(track, localStreamRef.current));
      pc.onicecandidate = (e) => {
        if (e.candidate)
          send({ type: "ice-candidate", target: peerId, candidate: e.candidate });
      };
      pc.ontrack = (e) => {
        const v = remoteVideosRef.current.get(peerId);
        if (v) v.srcObject = e.streams[0];
      };
      peersRef.current.set(peerId, pc);
      return pc;
    }

    async function createOffer(peerId) {
      const pc = newPeer(peerId);
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      send({ type: "offer", target: peerId, sdp: offer });
    }

    async function handleOffer(peerId, sdp) {
      const pc = peersRef.current.get(peerId) || newPeer(peerId);
      await pc.setRemoteDescription(sdp);
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      send({ type: "answer", target: peerId, sdp: answer });
      setPeerIds((p) => [...new Set([...p, peerId])]);
    }

    function closePeer(peerId) {
      peersRef.current.get(peerId)?.close();
      peersRef.current.delete(peerId);
      setPeerIds((p) => p.filter((id) => id !== peerId));
    }

    function send(obj) {
      if (wsRef.current?.readyState === WebSocket.OPEN)
        wsRef.current.send(JSON.stringify(obj));
    }

    start();

    return () => {
      mounted = false;
      if (wsRef.current?._hb) clearInterval(wsRef.current._hb);
      wsRef.current?.close();
      peersRef.current.forEach((pc) => pc.close());
      peersRef.current.clear();
      localStreamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, [roomId]);

  return (
    <div className="room">
      <header className="room-bar">
        <button className="btn ghost" onClick={() => navigate(-1)}>
          ← Leave
        </button>
        <span className="room-title">Room {roomId}</span>
        <span className={`pill ${status === "connected" ? "ok" : "warn"}`}>{status}</span>
        <span className="muted">{peerIds.length + 1} in room</span>
      </header>

      <div className="video-grid">
        <div className="video-cell">
          <video ref={localVideoRef} autoPlay playsInline muted />
          <span className="name-tag">You</span>
        </div>
        {peerIds.map((pid) => (
          <div className="video-cell" key={pid}>
            <video
              autoPlay
              playsInline
              ref={(el) => {
                if (el) remoteVideosRef.current.set(pid, el);
                else remoteVideosRef.current.delete(pid);
              }}
            />
            <span className="name-tag">Participant #{pid}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
