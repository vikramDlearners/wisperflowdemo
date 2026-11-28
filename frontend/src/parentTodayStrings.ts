// UI text for the parent's "I'm fine" button and today panel, in the chat's language.
// NOTE: like parentChatStrings.ts, the non-English text is simple and needs native-speaker review.

import type { ParentLang } from "./parentChatStrings";

export interface TodayStrings {
  imFine: string;
  fineHint: string;
  askedHint: string;
  fineDone: string;
  sending: string;
  failed: string;
  planTitle: string;
  tablets: string;
  taken: string;
  notYet: string;
  visits: string;
  todo: string;
  nothing: string;
  refillAsk: string;
  refillAskDate: string;
  refillYes: string;
  refillAsked: string;
  tellDoctor: string;
  pBp: string;
  pSugar: string;
  pMissed: string;
  pSaid: string;
  pAllergy: string;
  pAfter: string;
}

const EN: TodayStrings = {
  imFine: "I'm fine",
  fineHint: "One tap tells your family all is well today.",
  askedHint: "Are you OK? Tap \"I'm fine\" so your family knows.",
  fineDone: "Your family knows you're fine today.",
  sending: "Telling your family…",
  failed: "That didn't go through. Please try again.",  planTitle: "Today",
  tablets: "Tablets",
  taken: "taken",
  notYet: "not yet",
  visits: "Doctor visits",
  todo: "To do",
  nothing: "Nothing else planned for today.",
  refillAsk: "You have about {n} {name} tablets left. Shall I ask {who} to order them?",
  refillAskDate: "{name} is due for a refill. Shall I ask {who} to order it?",
  refillYes: "Yes, ask {who}",
  refillAsked: "{who} has been asked to order {name}.",
  tellDoctor: "Tell the doctor",
  pBp: "BP was high on {n} day(s), last {v}.",
  pSugar: "Sugar was high on {n} day(s), last {v}.",
  pMissed: "Missed {name} {n} time(s).",
  pSaid: "You said: \"{v}\"",
  pAllergy: "Allergies: {v}.",
  pAfter: "After the visit, your family can scan the prescription and your medicines update themselves.",
};

const STRINGS: Record<ParentLang, TodayStrings> = {
  en: EN,
  ta: {
    imFine: "நான் நலம்",
    fineHint: "ஒரு தட்டல் போதும், இன்று எல்லாம் நலம் என்று குடும்பத்துக்குத் தெரியும்.",
    askedHint: "நலமா? குடும்பத்துக்குத் தெரிய \"நான் நலம்\" தட்டுங்கள்.",
    fineDone: "இன்று நீங்கள் நலம் என்று குடும்பத்துக்குத் தெரியும்.",
    sending: "குடும்பத்துக்குச் சொல்கிறேன்…",
    failed: "அனுப்ப முடியவில்லை. மீண்டும் முயற்சிக்கவும்.",
    planTitle: "இன்று",
    tablets: "மாத்திரைகள்",
    taken: "எடுத்தாயிற்று",
    notYet: "இன்னும் இல்லை",
    visits: "டாக்டர் சந்திப்பு",
    todo: "செய்ய வேண்டியவை",
    nothing: "இன்று வேறு எதுவும் இல்லை.",
    refillAsk: "{name} மாத்திரை சுமார் {n} மட்டுமே உள்ளது. வாங்க {who}-இடம் சொல்லட்டுமா?",
    refillAskDate: "{name} மீண்டும் வாங்க வேண்டிய நேரம். வாங்க {who}-இடம் சொல்லட்டுமா?",
    refillYes: "சரி, {who}-இடம் சொல்லுங்கள்",
    refillAsked: "{name} வாங்க {who}-இடம் சொல்லியாயிற்று.",
    tellDoctor: "டாக்டரிடம் சொல்லுங்கள்",
    pBp: "{n} நாள் BP அதிகம், கடைசியாக {v}.",
    pSugar: "{n} நாள் சுகர் அதிகம், கடைசியாக {v}.",
    pMissed: "{name} {n} முறை தவறியது.",
    pSaid: "நீங்கள் சொன்னது: \"{v}\"",
    pAllergy: "ஒவ்வாமை: {v}.",
    pAfter: "சந்திப்புக்குப் பிறகு குடும்பம் மருந்துச்சீட்டை ஸ்கேன் செய்தால், மருந்துகள் தானாகப் புதுப்பிக்கப்படும்.",
  },
  hi: {
    imFine: "मैं ठीक हूँ",
    fineHint: "एक बार दबाएँ, परिवार को पता चलेगा कि आज सब ठीक है।",
    askedHint: "आप ठीक हैं? परिवार को बताने के लिए \"मैं ठीक हूँ\" दबाएँ।",
    fineDone: "परिवार को पता है कि आज आप ठीक हैं।",
    sending: "परिवार को बता रहे हैं…",
    failed: "भेजा नहीं जा सका। फिर से कोशिश करें।",
    planTitle: "आज",
    tablets: "दवाइयाँ",
    taken: "ले ली",
    notYet: "अभी नहीं",
    visits: "डॉक्टर से मिलना",
    todo: "करने के काम",
    nothing: "आज और कुछ तय नहीं है।",
    refillAsk: "{name} की लगभग {n} गोलियाँ बची हैं। क्या मैं {who} से मँगवाने को कहूँ?",
    refillAskDate: "{name} फिर से लेने का समय है। क्या मैं {who} से मँगवाने को कहूँ?",
    refillYes: "हाँ, {who} से कहें",
    refillAsked: "{who} से {name} मँगवाने को कह दिया है।",
    tellDoctor: "डॉक्टर को बताएँ",
    pBp: "{n} दिन BP ज़्यादा था, आख़िरी {v}।",
    pSugar: "{n} दिन शुगर ज़्यादा थी, आख़िरी {v}।",
    pMissed: "{name} {n} बार छूटी।",
    pSaid: "आपने कहा: \"{v}\"",
    pAllergy: "एलर्जी: {v}।",
    pAfter: "मिलने के बाद परिवार पर्ची स्कैन करे, तो आपकी दवाइयाँ अपने-आप बदल जाएँगी।",
  },
  te: {
    imFine: "నేను బాగున్నాను",
    fineHint: "ఒక్కసారి నొక్కితే, ఈరోజు అంతా బాగుందని కుటుంబానికి తెలుస్తుంది.",
    askedHint: "బాగున్నారా? కుటుంబానికి తెలియడానికి \"నేను బాగున్నాను\" నొక్కండి.",
    fineDone: "ఈరోజు మీరు బాగున్నారని కుటుంబానికి తెలుసు.",
    sending: "కుటుంబానికి చెబుతున్నాం…",
    failed: "పంపడం కాలేదు. మళ్ళీ ప్రయత్నించండి.",
    planTitle: "ఈరోజు",
    tablets: "మాత్రలు",
    taken: "వేసుకున్నారు",
    notYet: "ఇంకా లేదు",
    visits: "డాక్టర్ దగ్గరకు",
    todo: "చేయాల్సినవి",
    nothing: "ఈరోజు ఇంకేమీ లేదు.",
    refillAsk: "{name} మాత్రలు సుమారు {n} మాత్రమే ఉన్నాయి. తెప్పించమని {who}కి చెప్పనా?",
    refillAskDate: "{name} మళ్ళీ తెప్పించే సమయం. తెప్పించమని {who}కి చెప్పనా?",
    refillYes: "అవును, {who}కి చెప్పండి",
    refillAsked: "{name} తెప్పించమని {who}కి చెప్పాం.",
    tellDoctor: "డాక్టర్‌కి చెప్పండి",
    pBp: "{n} రోజులు BP ఎక్కువ, చివరిది {v}.",
    pSugar: "{n} రోజులు షుగర్ ఎక్కువ, చివరిది {v}.",
    pMissed: "{name} {n} సార్లు మిస్ అయింది.",
    pSaid: "మీరు చెప్పింది: \"{v}\"",
    pAllergy: "అలర్జీ: {v}.",
    pAfter: "వెళ్ళొచ్చాక కుటుంబం ప్రిస్క్రిప్షన్ స్కాన్ చేస్తే, మీ మందులు వాటంతట అవే మారతాయి.",
  },
  ml: {
    imFine: "ഞാൻ സുഖമാണ്",
    fineHint: "ഒരു തവണ തൊട്ടാൽ, ഇന്ന് എല്ലാം ശരിയാണെന്ന് കുടുംബം അറിയും.",
    askedHint: "സുഖമാണോ? കുടുംബം അറിയാൻ \"ഞാൻ സുഖമാണ്\" തൊടുക.",
    fineDone: "ഇന്ന് നിങ്ങൾ സുഖമാണെന്ന് കുടുംബത്തിന് അറിയാം.",
    sending: "കുടുംബത്തെ അറിയിക്കുന്നു…",
    failed: "അയയ്ക്കാനായില്ല. വീണ്ടും ശ്രമിക്കുക.",
    planTitle: "ഇന്ന്",
    tablets: "ഗുളികകൾ",
    taken: "കഴിച്ചു",
    notYet: "ഇനിയും ഇല്ല",
    visits: "ഡോക്ടറെ കാണൽ",
    todo: "ചെയ്യാനുള്ളത്",
    nothing: "ഇന്ന് വേറെ ഒന്നുമില്ല.",
    refillAsk: "{name} ഏകദേശം {n} എണ്ണം മാത്രമേ ഉള്ളൂ. വാങ്ങാൻ {who}-നോട് പറയട്ടേ?",
    refillAskDate: "{name} വീണ്ടും വാങ്ങേണ്ട സമയമായി. വാങ്ങാൻ {who}-നോട് പറയട്ടേ?",
    refillYes: "ശരി, {who}-നോട് പറയൂ",
    refillAsked: "{name} വാങ്ങാൻ {who}-നോട് പറഞ്ഞു.",
    tellDoctor: "ഡോക്ടറോട് പറയുക",
    pBp: "{n} ദിവസം BP കൂടുതൽ, അവസാനം {v}.",
    pSugar: "{n} ദിവസം ഷുഗർ കൂടുതൽ, അവസാനം {v}.",
    pMissed: "{name} {n} തവണ മുടങ്ങി.",
    pSaid: "നിങ്ങൾ പറഞ്ഞത്: \"{v}\"",
    pAllergy: "അലർജി: {v}.",
    pAfter: "കണ്ടതിനു ശേഷം കുടുംബം കുറിപ്പടി സ്കാൻ ചെയ്താൽ, മരുന്നുകൾ തനിയെ പുതുക്കും.",
  },
  kn: {
    imFine: "ನಾನು ಚೆನ್ನಾಗಿದ್ದೇನೆ",
    fineHint: "ಒಮ್ಮೆ ಒತ್ತಿದರೆ, ಇಂದು ಎಲ್ಲವೂ ಚೆನ್ನಾಗಿದೆ ಎಂದು ಕುಟುಂಬಕ್ಕೆ ತಿಳಿಯುತ್ತದೆ.",
    askedHint: "ಚೆನ್ನಾಗಿದ್ದೀರಾ? ಕುಟುಂಬಕ್ಕೆ ತಿಳಿಯಲು \"ನಾನು ಚೆನ್ನಾಗಿದ್ದೇನೆ\" ಒತ್ತಿ.",
    fineDone: "ಇಂದು ನೀವು ಚೆನ್ನಾಗಿದ್ದೀರಿ ಎಂದು ಕುಟುಂಬಕ್ಕೆ ತಿಳಿದಿದೆ.",
    sending: "ಕುಟುಂಬಕ್ಕೆ ತಿಳಿಸುತ್ತಿದ್ದೇವೆ…",
    failed: "ಕಳುಹಿಸಲಾಗಲಿಲ್ಲ. ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
    planTitle: "ಇಂದು",
    tablets: "ಮಾತ್ರೆಗಳು",
    taken: "ತೆಗೆದುಕೊಂಡಿದ್ದೀರಿ",
    notYet: "ಇನ್ನೂ ಇಲ್ಲ",
    visits: "ವೈದ್ಯರ ಭೇಟಿ",
    todo: "ಮಾಡಬೇಕಾದವು",
    nothing: "ಇಂದು ಬೇರೆ ಏನೂ ಇಲ್ಲ.",
    refillAsk: "{name} ಸುಮಾರು {n} ಮಾತ್ರೆ ಮಾತ್ರ ಉಳಿದಿವೆ. ತರಿಸಲು {who} ಅವರಿಗೆ ಹೇಳಲೇ?",
    refillAskDate: "{name} ಮತ್ತೆ ತರಿಸುವ ಸಮಯ. ತರಿಸಲು {who} ಅವರಿಗೆ ಹೇಳಲೇ?",
    refillYes: "ಹೌದು, {who} ಅವರಿಗೆ ಹೇಳಿ",
    refillAsked: "{name} ತರಿಸಲು {who} ಅವರಿಗೆ ಹೇಳಲಾಗಿದೆ.",
    tellDoctor: "ವೈದ್ಯರಿಗೆ ಹೇಳಿ",
    pBp: "{n} ದಿನ BP ಹೆಚ್ಚು, ಕೊನೆಯದು {v}.",
    pSugar: "{n} ದಿನ ಶುಗರ್ ಹೆಚ್ಚು, ಕೊನೆಯದು {v}.",
    pMissed: "{name} {n} ಬಾರಿ ತಪ್ಪಿದೆ.",
    pSaid: "ನೀವು ಹೇಳಿದ್ದು: \"{v}\"",
    pAllergy: "ಅಲರ್ಜಿ: {v}.",
    pAfter: "ಭೇಟಿಯ ನಂತರ ಕುಟುಂಬ ಚೀಟಿಯನ್ನು ಸ್ಕ್ಯಾನ್ ಮಾಡಿದರೆ, ನಿಮ್ಮ ಔಷಧಿಗಳು ತಾವಾಗಿಯೇ ಬದಲಾಗುತ್ತವೆ.",
  },
};

export function todayStrings(language: string): TodayStrings {
  return STRINGS[language as ParentLang] ?? EN;
}

export function fill(text: string, values: Record<string, string | number>): string {
  return text.replace(/\{(\w+)\}/g, (_, k: string) => String(values[k] ?? ""));
}
