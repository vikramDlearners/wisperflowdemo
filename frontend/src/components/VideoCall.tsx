import { useEffect, useRef, useState } from "react";
import "../care-circle.css";
import { newPeer, pause } from "../lib/videoCall";

type Status = { status: "ringing" | "live" | "ended" };

// A full-screen video call. `connect` does the offer/answer exchange for its side; `poll` reports whether the other
// side hung up; `hangUp` tells the server the call is over.
export default function VideoCall({
  title,
  labels,
  connect,
  poll,
  hangUp,
  onClose,
}: {
  title: string;
  labels: { connecting: string; live: string; ended: string; end: string; noCamera: string };
  connect: (pc: RTCPeerConnection, stopped: () => boolean) => Promise<void>;
  poll: () => Promise<Status | null>;
  hangUp: () => Promise<unknown>;
  onClose: () => void;
}) {
  const local = useRef<HTMLVideoElement>(null);
  const remote = useRef<HTMLVideoElement>(null);
  const [state, setState] = useState<"connecting" | "live" | "ended">("connecting");
  const [error, setError] = useState<string | null>(null);
  const finish = useRef<() => void>(() => undefined);

  useEffect(() => {
    let stopped = false;
    let stream: MediaStream | null = null;
    const pc = newPeer();
    const end = () => {
      if (stopped) return;
      stopped = true;
      stream?.getTracks().forEach((t) => t.stop());
      pc.close();
      setState("ended");
    };
    finish.current = end;
    pc.ontrack = (e) => {
      if (remote.current) remote.current.srcObject = e.streams[0];
      setState("live");
    };
    pc.onconnectionstatechange = () => {
      if (pc.connectionState === "failed" || pc.connectionState === "closed") end();
    };
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      } catch {
        setError(labels.noCamera);
        end();
        return;
      }
      if (stopped) return;
      if (local.current) local.current.srcObject = stream;
      stream.getTracks().forEach((t) => pc.addTrack(t, stream!));
      try {
        await connect(pc, () => stopped);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        end();
        return;
      }
      while (!stopped) {
        await pause(3000);
        const now = await poll().catch(() => null);
        if (now?.status === "ended") end();
      }
    })();
    return () => {
      if (!stopped) void hangUp().catch(() => undefined);
      end();
    };
    // The call runs once per mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function close() {
    finish.current();
    await hangUp().catch(() => undefined);
    onClose();
  }

  return (
    <div className="vc-overlay" role="dialog" aria-label={title}>
      <div>
        <h2>{title}</h2>
        <p role="status">{error ?? labels[state]}</p>
      </div>
      <div className="vc-stage">
        <video ref={remote} className="vc-remote" autoPlay playsInline />
        <video ref={local} className="vc-local" autoPlay playsInline muted />
      </div>
      <div className="vc-bar">
        <button type="button" className="pp-btn vc-end" onClick={() => void close()}>
          {labels.end}
        </button>
      </div>
    </div>
  );
}
