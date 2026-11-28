// Browser-to-browser video over WebRTC. The server only carries the two descriptions, so each side waits for its
// network candidates to be gathered before sending its description. The STUN server is Google's public one; it
// only tells each browser its public address, the video itself goes directly between the two.
export const ICE_SERVERS: RTCIceServer[] = [{ urls: "stun:stun.l.google.com:19302" }];

export function newPeer(): RTCPeerConnection {
  return new RTCPeerConnection({ iceServers: ICE_SERVERS });
}

export async function gatheredSdp(pc: RTCPeerConnection): Promise<string> {
  if (pc.iceGatheringState !== "complete") {
    await new Promise<void>((resolve) => {
      const timer = window.setTimeout(finish, 5000);
      function finish() {
        window.clearTimeout(timer);
        pc.removeEventListener("icegatheringstatechange", check);
        resolve();
      }
      function check() {
        if (pc.iceGatheringState === "complete") finish();
      }
      pc.addEventListener("icegatheringstatechange", check);
    });
  }
  return pc.localDescription?.sdp ?? "";
}

export const pause = (ms: number) => new Promise((r) => window.setTimeout(r, ms));
