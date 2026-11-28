import { useRef, useState } from "react";
import VideoCall from "./VideoCall";
import { videoCalls } from "../api";
import { gatheredSdp, pause } from "../lib/videoCall";

const LABELS = {
  connecting: "Ringing… the parent's app must be open to hear it.",
  live: "Connected",
  ended: "The call has ended.",
  end: "End call",
  noCamera: "Allow the camera and microphone to make a video call.",
};

// Rings the parent's app. It answers by itself when the parent turned that on, or shows a big green button.
export default function FamilyCallButton({ familyId, profileId, name }: { familyId: string; profileId: string; name: string }) {
  const [open, setOpen] = useState(false);
  const callId = useRef<string | null>(null);

  async function connect(pc: RTCPeerConnection, stopped: () => boolean) {
    await pc.setLocalDescription(await pc.createOffer());
    const call = await videoCalls.start(familyId, profileId, await gatheredSdp(pc));
    callId.current = call.id;
    while (!stopped()) {
      await pause(2000);
      const now = await videoCalls.get(familyId, call.id);
      if (now.status === "ended") throw new Error(`${name} did not answer.`);
      if (now.status === "live" && now.answer) {
        await pc.setRemoteDescription({ type: "answer", sdp: now.answer });
        return;
      }
    }
  }

  return (
    <>
      <button type="button" className="pp-btn" onClick={() => setOpen(true)}>
        📹 Video call {name}
      </button>
      {open && (
        <VideoCall
          title={`Video call with ${name}`}
          labels={LABELS}
          connect={connect}
          poll={() => (callId.current ? videoCalls.get(familyId, callId.current) : Promise.resolve(null))}
          hangUp={() => (callId.current ? videoCalls.end(familyId, callId.current) : Promise.resolve())}
          onClose={() => {
            callId.current = null;
            setOpen(false);
          }}
        />
      )}
    </>
  );
}
