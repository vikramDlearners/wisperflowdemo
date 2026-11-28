// UI text for the parent's circle panel (components/ParentCircle.tsx), in the chat's language.
// NOTE: like parentChatStrings.ts, the non-English text is simple and needs native-speaker review.

import type { ParentLang } from "./parentChatStrings";
import type { HelpKind, HelpOut } from "./parentApi";

export interface CircleStrings {
  title: string;
  fromFamily: string;
  helpTitle: string;
  kinds: Record<HelpKind, string>;
  status: Record<HelpOut["status"], string>;
  helpSent: string;
  callTitle: string;
  birthdayToday: string;
  birthdayTomorrow: string;
  nudgeCall: string;
  nudgeWalk: string;
  cardBtn: string;
  cardTitle: string;
  blood: string;
  allergies: string;
  medicines: string;
  doctor: string;
  hospital: string;
  contact: string;
  insurance: string;
  close: string;
  privacyTitle: string;
  shareWords: string;
  shareChats: string;
  autoAnswer: string;
  fallOn: string;
  fallAsk: string;
  fallOk: string;
  fallNoSensor: string;
  failed: string;
}

const EN: CircleStrings = {
  title: "My people",
  fromFamily: "From your family",
  helpTitle: "Ask the family for help",
  kinds: { bill: "Pay a bill", groceries: "Groceries", cab: "A cab", nurse: "A nurse", physio: "Physio", other: "Something else" },
  status: { asked: "waiting for family", approved: "family said yes", declined: "family said no", done: "done" },
  helpSent: "Your family has been asked.",
  callTitle: "Call",
  birthdayToday: "Today is {name}'s birthday. Call them?",
  birthdayTomorrow: "Tomorrow is {name}'s birthday.",
  nudgeCall: "You haven't heard from {name} for a few days. Call them?",
  nudgeWalk: "A short walk would be good today.",
  cardBtn: "My medical card",
  cardTitle: "Medical card",
  blood: "Blood group",
  allergies: "Allergies",
  medicines: "Medicines",
  doctor: "Doctor",
  hospital: "Hospital",
  contact: "Emergency contact",
  insurance: "Insurance",
  close: "Close",
  privacyTitle: "What my family sees",
  shareWords: "Share what I say in the chat",
  shareChats: "Share chat summaries",
  autoAnswer: "Answer family video calls by itself",
  fallOn: "Watch for falls on this phone",
  fallAsk: "Did you fall? Your family will be called in {n} seconds.",
  fallOk: "I'm OK",
  fallNoSensor: "This phone can't watch for falls.",
  failed: "That didn't go through. Please try again.",
};

const STRINGS: Record<ParentLang, CircleStrings> = {
  en: EN,
  ta: {
    title: "என் மக்கள்",
    fromFamily: "குடும்பத்திடமிருந்து",
    helpTitle: "குடும்பத்திடம் உதவி கேளுங்கள்",
    kinds: { bill: "பில் கட்ட", groceries: "மளிகை", cab: "டாக்சி", nurse: "நர்ஸ்", physio: "பிசியோ", other: "வேறு ஏதாவது" },
    status: { asked: "குடும்பத்தின் பதிலுக்குக் காத்திருக்கிறது", approved: "குடும்பம் சரி என்றது", declined: "குடும்பம் வேண்டாம் என்றது", done: "முடிந்தது" },
    helpSent: "குடும்பத்திடம் கேட்டாயிற்று.",
    callTitle: "அழையுங்கள்",
    birthdayToday: "இன்று {name} பிறந்தநாள். அழைக்கலாமா?",
    birthdayTomorrow: "நாளை {name} பிறந்தநாள்.",
    nudgeCall: "சில நாட்களாக {name}-இடம் பேசவில்லை. அழைக்கலாமா?",
    nudgeWalk: "இன்று கொஞ்சம் நடந்தால் நல்லது.",
    cardBtn: "என் மருத்துவ அட்டை",
    cardTitle: "மருத்துவ அட்டை",
    blood: "இரத்த வகை",
    allergies: "ஒவ்வாமை",
    medicines: "மருந்துகள்",
    doctor: "டாக்டர்",
    hospital: "மருத்துவமனை",
    contact: "அவசர தொடர்பு",
    insurance: "காப்பீடு",
    close: "மூடு",
    privacyTitle: "குடும்பம் எதைப் பார்க்கலாம்",
    shareWords: "நான் சொல்வதைப் பகிரவும்",
    shareChats: "உரையாடல் சுருக்கத்தைப் பகிரவும்",
    autoAnswer: "குடும்ப வீடியோ அழைப்பைத் தானாக எடுக்கவும்",
    fallOn: "இந்த போனில் விழுவதைக் கவனிக்கவும்",
    fallAsk: "விழுந்தீர்களா? {n} விநாடியில் குடும்பத்தை அழைப்பேன்.",
    fallOk: "நான் நலம்",
    fallNoSensor: "இந்த போனால் விழுவதைக் கவனிக்க முடியாது.",
    failed: "அனுப்ப முடியவில்லை. மீண்டும் முயற்சிக்கவும்.",
  },
  hi: {
    title: "मेरे अपने",
    fromFamily: "परिवार की ओर से",
    helpTitle: "परिवार से मदद माँगें",
    kinds: { bill: "बिल भरना", groceries: "राशन", cab: "टैक्सी", nurse: "नर्स", physio: "फिजियो", other: "कुछ और" },
    status: { asked: "परिवार के जवाब का इंतज़ार", approved: "परिवार ने हाँ कहा", declined: "परिवार ने ना कहा", done: "हो गया" },
    helpSent: "परिवार से कह दिया गया है।",
    callTitle: "फ़ोन करें",
    birthdayToday: "आज {name} का जन्मदिन है। फ़ोन करें?",
    birthdayTomorrow: "कल {name} का जन्मदिन है।",
    nudgeCall: "कुछ दिनों से {name} से बात नहीं हुई। फ़ोन करें?",
    nudgeWalk: "आज थोड़ा टहलना अच्छा रहेगा।",
    cardBtn: "मेरा मेडिकल कार्ड",
    cardTitle: "मेडिकल कार्ड",
    blood: "ब्लड ग्रुप",
    allergies: "एलर्जी",
    medicines: "दवाइयाँ",
    doctor: "डॉक्टर",
    hospital: "अस्पताल",
    contact: "आपातकालीन संपर्क",
    insurance: "बीमा",
    close: "बंद करें",
    privacyTitle: "परिवार क्या देख सकता है",
    shareWords: "मेरी कही बातें साझा करें",
    shareChats: "बातचीत का सार साझा करें",
    autoAnswer: "परिवार की वीडियो कॉल अपने आप उठाएँ",
    fallOn: "इस फ़ोन पर गिरने का ध्यान रखें",
    fallAsk: "क्या आप गिर गए? {n} सेकंड में परिवार को बुलाया जाएगा।",
    fallOk: "मैं ठीक हूँ",
    fallNoSensor: "यह फ़ोन गिरने का पता नहीं लगा सकता।",
    failed: "नहीं भेजा जा सका। फिर से कोशिश करें।",
  },
  te: {
    title: "నా వాళ్ళు",
    fromFamily: "కుటుంబం నుండి",
    helpTitle: "కుటుంబాన్ని సహాయం అడగండి",
    kinds: { bill: "బిల్లు కట్టడం", groceries: "సరుకులు", cab: "క్యాబ్", nurse: "నర్సు", physio: "ఫిజియో", other: "ఇంకేదైనా" },
    status: { asked: "కుటుంబం జవాబు కోసం", approved: "కుటుంబం సరే అంది", declined: "కుటుంబం వద్దు అంది", done: "అయిపోయింది" },
    helpSent: "కుటుంబాన్ని అడిగాము.",
    callTitle: "కాల్ చేయండి",
    birthdayToday: "ఈరోజు {name} పుట్టినరోజు. కాల్ చేద్దామా?",
    birthdayTomorrow: "రేపు {name} పుట్టినరోజు.",
    nudgeCall: "కొన్ని రోజులుగా {name} తో మాట్లాడలేదు. కాల్ చేద్దామా?",
    nudgeWalk: "ఈరోజు కొంచెం నడిస్తే మంచిది.",
    cardBtn: "నా మెడికల్ కార్డు",
    cardTitle: "మెడికల్ కార్డు",
    blood: "బ్లడ్ గ్రూప్",
    allergies: "అలర్జీలు",
    medicines: "మందులు",
    doctor: "డాక్టర్",
    hospital: "ఆసుపత్రి",
    contact: "అత్యవసర సంప్రదింపు",
    insurance: "బీమా",
    close: "మూసివేయి",
    privacyTitle: "కుటుంబం ఏమి చూడవచ్చు",
    shareWords: "నేను చెప్పేది పంచుకోండి",
    shareChats: "సంభాషణ సారాంశం పంచుకోండి",
    autoAnswer: "కుటుంబ వీడియో కాల్స్ తనంతట తానే ఎత్తాలి",
    fallOn: "ఈ ఫోన్‌లో పడిపోవడం గమనించండి",
    fallAsk: "మీరు పడిపోయారా? {n} సెకన్లలో కుటుంబాన్ని పిలుస్తాను.",
    fallOk: "నేను బాగున్నాను",
    fallNoSensor: "ఈ ఫోన్ పడిపోవడాన్ని గమనించలేదు.",
    failed: "పంపలేకపోయాం. మళ్ళీ ప్రయత్నించండి.",
  },
  ml: {
    title: "എന്റെ ആളുകൾ",
    fromFamily: "കുടുംബത്തിൽ നിന്ന്",
    helpTitle: "കുടുംബത്തോട് സഹായം ചോദിക്കുക",
    kinds: { bill: "ബിൽ അടയ്ക്കാൻ", groceries: "പലചരക്ക്", cab: "ടാക്സി", nurse: "നഴ്സ്", physio: "ഫിസിയോ", other: "മറ്റെന്തെങ്കിലും" },
    status: { asked: "കുടുംബത്തിന്റെ മറുപടിക്കായി", approved: "കുടുംബം ശരി പറഞ്ഞു", declined: "കുടുംബം വേണ്ട പറഞ്ഞു", done: "കഴിഞ്ഞു" },
    helpSent: "കുടുംബത്തോട് ചോദിച്ചു.",
    callTitle: "വിളിക്കുക",
    birthdayToday: "ഇന്ന് {name}-ന്റെ ജന്മദിനം. വിളിക്കട്ടെ?",
    birthdayTomorrow: "നാളെ {name}-ന്റെ ജന്മദിനം.",
    nudgeCall: "കുറച്ചു ദിവസമായി {name}-നോട് സംസാരിച്ചിട്ടില്ല. വിളിക്കട്ടെ?",
    nudgeWalk: "ഇന്ന് അൽപം നടക്കുന്നത് നല്ലതാണ്.",
    cardBtn: "എന്റെ മെഡിക്കൽ കാർഡ്",
    cardTitle: "മെഡിക്കൽ കാർഡ്",
    blood: "രക്തഗ്രൂപ്പ്",
    allergies: "അലർജി",
    medicines: "മരുന്നുകൾ",
    doctor: "ഡോക്ടർ",
    hospital: "ആശുപത്രി",
    contact: "അടിയന്തര ബന്ധം",
    insurance: "ഇൻഷുറൻസ്",
    close: "അടയ്ക്കുക",
    privacyTitle: "കുടുംബം എന്ത് കാണും",
    shareWords: "ഞാൻ പറയുന്നത് പങ്കിടുക",
    shareChats: "സംഭാഷണ സംഗ്രഹം പങ്കിടുക",
    autoAnswer: "കുടുംബ വീഡിയോ കോളുകൾ സ്വയം എടുക്കുക",
    fallOn: "ഈ ഫോണിൽ വീഴ്ച ശ്രദ്ധിക്കുക",
    fallAsk: "നിങ്ങൾ വീണോ? {n} സെക്കൻഡിൽ കുടുംബത്തെ വിളിക്കും.",
    fallOk: "എനിക്ക് കുഴപ്പമില്ല",
    fallNoSensor: "ഈ ഫോണിന് വീഴ്ച ശ്രദ്ധിക്കാൻ കഴിയില്ല.",
    failed: "അയയ്ക്കാനായില്ല. വീണ്ടും ശ്രമിക്കുക.",
  },
  kn: {
    title: "ನನ್ನವರು",
    fromFamily: "ಕುಟುಂಬದಿಂದ",
    helpTitle: "ಕುಟುಂಬದ ಸಹಾಯ ಕೇಳಿ",
    kinds: { bill: "ಬಿಲ್ ಕಟ್ಟಲು", groceries: "ದಿನಸಿ", cab: "ಟ್ಯಾಕ್ಸಿ", nurse: "ನರ್ಸ್", physio: "ಫಿಸಿಯೋ", other: "ಬೇರೆ ಏನಾದರೂ" },
    status: { asked: "ಕುಟುಂಬದ ಉತ್ತರಕ್ಕಾಗಿ", approved: "ಕುಟುಂಬ ಸರಿ ಎಂದಿದೆ", declined: "ಕುಟುಂಬ ಬೇಡ ಎಂದಿದೆ", done: "ಆಯಿತು" },
    helpSent: "ಕುಟುಂಬಕ್ಕೆ ಕೇಳಲಾಗಿದೆ.",
    callTitle: "ಕರೆ ಮಾಡಿ",
    birthdayToday: "ಇಂದು {name} ಅವರ ಹುಟ್ಟುಹಬ್ಬ. ಕರೆ ಮಾಡಲೇ?",
    birthdayTomorrow: "ನಾಳೆ {name} ಅವರ ಹುಟ್ಟುಹಬ್ಬ.",
    nudgeCall: "ಕೆಲವು ದಿನಗಳಿಂದ {name} ಜೊತೆ ಮಾತಾಡಿಲ್ಲ. ಕರೆ ಮಾಡಲೇ?",
    nudgeWalk: "ಇಂದು ಸ್ವಲ್ಪ ನಡೆದರೆ ಒಳ್ಳೆಯದು.",
    cardBtn: "ನನ್ನ ವೈದ್ಯಕೀಯ ಕಾರ್ಡ್",
    cardTitle: "ವೈದ್ಯಕೀಯ ಕಾರ್ಡ್",
    blood: "ರಕ್ತದ ಗುಂಪು",
    allergies: "ಅಲರ್ಜಿ",
    medicines: "ಔಷಧಿಗಳು",
    doctor: "ವೈದ್ಯರು",
    hospital: "ಆಸ್ಪತ್ರೆ",
    contact: "ತುರ್ತು ಸಂಪರ್ಕ",
    insurance: "ವಿಮೆ",
    close: "ಮುಚ್ಚಿ",
    privacyTitle: "ಕುಟುಂಬ ಏನು ನೋಡಬಹುದು",
    shareWords: "ನಾನು ಹೇಳುವುದನ್ನು ಹಂಚಿಕೊಳ್ಳಿ",
    shareChats: "ಸಂಭಾಷಣೆಯ ಸಾರಾಂಶ ಹಂಚಿಕೊಳ್ಳಿ",
    autoAnswer: "ಕುಟುಂಬದ ವೀಡಿಯೊ ಕರೆಗಳನ್ನು ತಾನಾಗಿಯೇ ಎತ್ತಿ",
    fallOn: "ಈ ಫೋನ್‌ನಲ್ಲಿ ಬೀಳುವುದನ್ನು ಗಮನಿಸಿ",
    fallAsk: "ನೀವು ಬಿದ್ದಿರಾ? {n} ಸೆಕೆಂಡುಗಳಲ್ಲಿ ಕುಟುಂಬವನ್ನು ಕರೆಯಲಾಗುತ್ತದೆ.",
    fallOk: "ನಾನು ಚೆನ್ನಾಗಿದ್ದೇನೆ",
    fallNoSensor: "ಈ ಫೋನ್ ಬೀಳುವುದನ್ನು ಗಮನಿಸಲಾರದು.",
    failed: "ಕಳುಹಿಸಲಾಗಲಿಲ್ಲ. ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
  },
};

export function circleStrings(language: string): CircleStrings {
  return STRINGS[language as ParentLang] ?? EN;
}
