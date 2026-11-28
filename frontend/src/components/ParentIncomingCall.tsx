import { useEffect, useRef, useState } from "react";
import VideoCall from "./VideoCall";
import { answerCall, endParentCall, getIncomingCall, getParentCall, type IncomingCall } from "../parentApi";
import { gatheredSdp } from "../lib/videoCall";
import type { ParentLang } from "../parentChatStrings";

const STRINGS: Record<
  ParentLang,
  { ringing: string; answer: string; title: string; connecting: string; live: string; ended: string; end: string; noCamera: string }
> = {
  en: { ringing: "is calling you", answer: "Answer", title: "Video call with", connecting: "Connecting…", live: "Connected", ended: "The call has ended.", end: "End call", noCamera: "Allow the camera and microphone to answer." },
  ta: { ringing: "உங்களை அழைக்கிறார்", answer: "எடுக்கவும்", title: "வீடியோ அழைப்பு:", connecting: "இணைக்கிறது…", live: "இணைந்தது", ended: "அழைப்பு முடிந்தது.", end: "அழைப்பை முடிக்கவும்", noCamera: "எடுக்க கேமராவையும் மைக்கையும் அனுமதிக்கவும்." },
  hi: { ringing: "आपको कॉल कर रहे हैं", answer: "उठाएँ", title: "वीडियो कॉल:", connecting: "जुड़ रहा है…", live: "जुड़ गया", ended: "कॉल खत्म हो गई।", end: "कॉल खत्म करें", noCamera: "कॉल उठाने के लिए कैमरा और माइक की अनुमति दें।" },
  te: { ringing: "మీకు కాల్ చేస్తున్నారు", answer: "ఎత్తండి", title: "వీడియో కాల్:", connecting: "కలుపుతోంది…", live: "కలిసింది", ended: "కాల్ ముగిసింది.", end: "కాల్ ముగించండి", noCamera: "ఎత్తడానికి కెమెరా, మైక్‌ను అనుమతించండి." },
  ml: { ringing: "നിങ്ങളെ വിളിക്കുന്നു", answer: "എടുക്കുക", title: "വീഡിയോ കോൾ:", connecting: "ബന്ധിപ്പിക്കുന്നു…", live: "ബന്ധിപ്പിച്ചു", ended: "കോൾ അവസാനിച്ചു.", end: "കോൾ അവസാനിപ്പിക്കുക", noCamera: "എടുക്കാൻ ക്യാമറയും മൈക്കും അനുവദിക്കുക." },
  kn: { ringing: "ನಿಮಗೆ ಕರೆ ಮಾಡುತ್ತಿದ್ದಾರೆ", answer: "ಎತ್ತಿ", title: "ವೀಡಿಯೊ ಕರೆ:", connecting: "ಸಂಪರ್ಕಿಸುತ್ತಿದೆ…", live: "ಸಂಪರ್ಕವಾಯಿತು", ended: "ಕರೆ ಮುಗಿಯಿತು.", end: "ಕರೆ ಮುಗಿಸಿ", noCamera: "ಎತ್ತಲು ಕ್ಯಾಮೆರಾ ಮತ್ತು ಮೈಕ್ ಅನುಮತಿಸಿ." },
};

// Asks every 5 seconds whether a family member is ringing. Answers by itself when the parent turned that on,
// otherwise shows one big green button.
export default function ParentIncomingCall({ language, profileId }: { language: string; profileId: string }) {
  const t = STRINGS[language as ParentLang] ?? STRINGS.en;
  const [ring, setRing] = useState<IncomingCall | null>(null);
  const [inCall, setInCall] = useState<IncomingCall | null>(null);
  const busy = useRef(false);

  useEffect(() => {
    let alive = true;
    const check = async () => {
      if (busy.current) return;
      const now = await getIncomingCall().catch(() => null);
      if (!alive || busy.current) return;
      if (now?.auto_answer) {
        busy.current = true;
        setRing(null);
        setInCall(now);
      } else {
        setRing(now);
      }
    };
    void check();
    const timer = window.setInterval(() => void check(), 5000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [profileId]);

  async function connect(pc: RTCPeerConnection, call: IncomingCall) {
    await pc.setRemoteDescription({ type: "offer", sdp: call.offer });
    await pc.setLocalDescription(await pc.createAnswer());
    await answerCall(call.id, await gatheredSdp(pc));
  }

  if (inCall) {
    const call = inCall;
    return (
      <VideoCall
        title={`${t.title} ${call.caller}`}
        labels={t}
        connect={(pc) => connect(pc, call)}
        poll={() => getParentCall(call.id)}
        hangUp={() => endParentCall(call.id)}
        onClose={() => {
          busy.current = false;
          setInCall(null);
        }}
      />
    );
  }
  if (!ring) return null;
  return (
    <div className="vc-ring" role="alertdialog" aria-label={`${ring.caller} ${t.ringing}`}>
      <span aria-hidden="true">📹</span>
      <span>
        <strong>{ring.caller}</strong> {t.ringing}
      </span>
      <button
        type="button"
        className="pp-btn vc-answer"
        onClick={() => {
          busy.current = true;
          setInCall(ring);
          setRing(null);
        }}
      >
        {t.answer}
      </button>
      <button
        type="button"
        className="pp-btn vc-end"
        aria-label={t.end}
        onClick={() => {
          const id = ring.id;
          setRing(null);
          void endParentCall(id).catch(() => undefined);
        }}
      >
        ✕
      </button>
    </div>
  );
}
