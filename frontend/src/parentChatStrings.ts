// UI text for the parent check-in chat, in the parent's language. Bot bubbles are already
// translated by the backend; this covers everything the page itself says.
// NOTE: these translations are simple and need native-speaker review before release.

export type ParentLang = "en" | "ta" | "hi" | "te" | "ml" | "kn";

export interface ParentStrings {
  tapToSpeak: string;
  tapAgainToSend: string;
  pleaseWait: string;
  stopAndSend: string;
  typeInstead: string;
  typeYourAnswer: string;
  send: string;
  help: string;
  callFamily: string;
  askFamilyAddPhone: string;
  listening: string;
  thinking: string;
  gettingReady: string;
  almostThere: string;
  notLinked: string;
  parentsOnly: string;
  goToStart: string;
  loadFailedTitle: string;
  tryAgain: string;
  voiceUnavailable: string;
  genericError: string;
  heardNothing: string;
  micBlocked: string;
  voiceNotOnPhone: string;
  conversation: string;
  botSays: string;
  youSaid: string;
  notLinkedHelp: string;
  logOut: string;
  photoOf: string;
  closePhoto: string;
  emergencyQuestion: string;
  emergencyYes: string;
  emergencyNo: string;
  emergencySending: string;
  emergencyNotified: string;
  emergencyCall: string;
  emergencyFailed: string;
  signingOut: string;
}

const en: ParentStrings = {
  logOut: "Log out",
  photoOf: "Photo",
  closePhoto: "Close",
  emergencyQuestion: "Is this an emergency?",
  emergencyYes: "Yes, it's an emergency",
  emergencyNo: "No, I just need help",
  emergencySending: "Telling your family…",
  emergencyNotified: "We have notified your children, caretakers and relatives on WhatsApp, Email and Text message.",
  emergencyCall: "Tap to call the emergency number",
  emergencyFailed: "We couldn't send the alerts. Please call now.",
  signingOut: "Signing out…",
  tapToSpeak: "Tap to speak",
  tapAgainToSend: "Tap again to send",
  pleaseWait: "Please wait",
  stopAndSend: "Stop and send",
  typeInstead: "Type instead",
  typeYourAnswer: "Type your answer",
  send: "Send",
  help: "Help",
  callFamily: "Call family",
  askFamilyAddPhone: "Ask your family to add a phone number",
  listening: "Listening…",
  thinking: "Thinking…",
  gettingReady: "Getting ready…",
  almostThere: "Almost there",
  notLinked: "Ask your family to link your profile",
  notLinkedHelp: "A family member needs to add you using the email or phone number you signed up with.",
  parentsOnly: "This page is for parents",
  goToStart: "Go to the start page",
  loadFailedTitle: "We couldn't load your chat",
  tryAgain: "Try again",
  voiceUnavailable: "Voice isn't available right now. Please type instead.",
  genericError: "Something went wrong. Please try again.",
  heardNothing: "I didn't hear anything. Please tap the microphone and try again.",
  micBlocked: "I can't use the microphone. Please allow it, or type your answer below.",
  voiceNotOnPhone: "Voice isn't available on this phone. Please type your answer below.",
  conversation: "Conversation",
  botSays: "CareCircle says:",
  youSaid: "You said:",
};

const hi: ParentStrings = {
  logOut: "लॉग आउट",
  photoOf: "फ़ोटो",
  closePhoto: "बंद करें",
  emergencyQuestion: "क्या यह आपातकाल है?",
  emergencyYes: "हाँ, आपातकाल है",
  emergencyNo: "नहीं, बस मदद चाहिए",
  emergencySending: "परिवार को बता रहे हैं…",
  emergencyNotified: "हमने आपके बच्चों, देखभाल करने वालों और रिश्तेदारों को WhatsApp, ईमेल और टेक्स्ट मैसेज से सूचित कर दिया है।",
  emergencyCall: "आपातकालीन नंबर पर कॉल करने के लिए दबाएँ",
  emergencyFailed: "सूचना नहीं भेज पाए। कृपया अभी कॉल करें।",
  signingOut: "लॉग आउट हो रहा है…",
  tapToSpeak: "बोलने के लिए दबाएं",
  tapAgainToSend: "भेजने के लिए फिर दबाएं",
  pleaseWait: "कृपया रुकें",
  stopAndSend: "रोकें और भेजें",
  typeInstead: "लिखकर बताएं",
  typeYourAnswer: "अपना जवाब लिखें",
  send: "भेजें",
  help: "मदद",
  callFamily: "परिवार को फ़ोन करें",
  askFamilyAddPhone: "अपने परिवार से फ़ोन नंबर जोड़ने को कहें",
  listening: "सुन रहे हैं…",
  thinking: "सोच रहे हैं…",
  gettingReady: "तैयार हो रहे हैं…",
  almostThere: "बस थोड़ा और",
  notLinked: "अपने परिवार से अपनी प्रोफ़ाइल जोड़ने को कहें",
  notLinkedHelp: "परिवार के किसी सदस्य को आपके ईमेल या फ़ोन नंबर से आपको जोड़ना होगा।",
  parentsOnly: "यह पेज माता-पिता के लिए है",
  goToStart: "शुरुआती पेज पर जाएं",
  loadFailedTitle: "आपकी चैट नहीं खुल सकी",
  tryAgain: "फिर कोशिश करें",
  voiceUnavailable: "अभी आवाज़ उपलब्ध नहीं है। कृपया लिखकर बताएं।",
  genericError: "कुछ गड़बड़ हो गई। कृपया फिर कोशिश करें।",
  heardNothing: "कुछ सुनाई नहीं दिया। कृपया माइक्रोफ़ोन दबाकर फिर कोशिश करें।",
  micBlocked: "माइक्रोफ़ोन इस्तेमाल नहीं हो सका। कृपया उसे अनुमति दें, या नीचे अपना जवाब लिखें।",
  voiceNotOnPhone: "इस फ़ोन पर आवाज़ उपलब्ध नहीं है। कृपया नीचे अपना जवाब लिखें।",
  conversation: "बातचीत",
  botSays: "केयरसर्कल कहता है:",
  youSaid: "आपने कहा:",
};

const ta: ParentStrings = {
  logOut: "வெளியேறு",
  photoOf: "படம்",
  closePhoto: "மூடு",
  emergencyQuestion: "இது அவசரமா?",
  emergencyYes: "ஆம், அவசரம்",
  emergencyNo: "இல்லை, உதவி மட்டும் வேண்டும்",
  emergencySending: "குடும்பத்தினருக்குத் தெரிவிக்கிறோம்…",
  emergencyNotified: "உங்கள் பிள்ளைகள், பராமரிப்பாளர்கள் மற்றும் உறவினர்களுக்கு WhatsApp, மின்னஞ்சல் மற்றும் குறுஞ்செய்தி மூலம் தெரிவித்துவிட்டோம்.",
  emergencyCall: "அவசர எண்ணை அழைக்க இங்கே தட்டவும்",
  emergencyFailed: "தகவல் அனுப்ப முடியவில்லை. உடனே அழையுங்கள்.",
  signingOut: "வெளியேறுகிறது…",
  tapToSpeak: "பேச தட்டவும்",
  tapAgainToSend: "அனுப்ப மீண்டும் தட்டவும்",
  pleaseWait: "காத்திருக்கவும்",
  stopAndSend: "நிறுத்தி அனுப்பு",
  typeInstead: "தட்டச்சு செய்யவும்",
  typeYourAnswer: "உங்கள் பதிலை தட்டச்சு செய்யவும்",
  send: "அனுப்பு",
  help: "உதவி",
  callFamily: "குடும்பத்தை அழைக்கவும்",
  askFamilyAddPhone: "தொலைபேசி எண்ணைச் சேர்க்க உங்கள் குடும்பத்திடம் கேளுங்கள்",
  listening: "கேட்கிறோம்…",
  thinking: "யோசிக்கிறோம்…",
  gettingReady: "தயாராகிறது…",
  almostThere: "கிட்டத்தட்ட முடிந்தது",
  notLinked: "உங்கள் சுயவிவரத்தை இணைக்க குடும்பத்திடம் கேளுங்கள்",
  notLinkedHelp: "நீங்கள் பதிவு செய்த மின்னஞ்சல் அல்லது தொலைபேசி எண்ணைக் கொண்டு குடும்ப உறுப்பினர் உங்களைச் சேர்க்க வேண்டும்.",
  parentsOnly: "இந்தப் பக்கம் பெற்றோருக்கானது",
  goToStart: "தொடக்கப் பக்கத்திற்குச் செல்லவும்",
  loadFailedTitle: "உங்கள் அரட்டையை ஏற்ற முடியவில்லை",
  tryAgain: "மீண்டும் முயற்சிக்கவும்",
  voiceUnavailable: "இப்போது குரல் வசதி இல்லை. தயவுசெய்து தட்டச்சு செய்யவும்.",
  genericError: "ஏதோ தவறு நடந்தது. மீண்டும் முயற்சிக்கவும்.",
  heardNothing: "எதுவும் கேட்கவில்லை. மைக்ரோஃபோனைத் தட்டி மீண்டும் முயற்சிக்கவும்.",
  micBlocked: "மைக்ரோஃபோனைப் பயன்படுத்த முடியவில்லை. அனுமதிக்கவும், அல்லது கீழே தட்டச்சு செய்யவும்.",
  voiceNotOnPhone: "இந்த தொலைபேசியில் குரல் வசதி இல்லை. கீழே தட்டச்சு செய்யவும்.",
  conversation: "உரையாடல்",
  botSays: "கேர்சர்கிள் சொல்கிறது:",
  youSaid: "நீங்கள் சொன்னது:",
};

const te: ParentStrings = {
  logOut: "లాగ్ అవుట్",
  photoOf: "ఫోటో",
  closePhoto: "మూసివేయి",
  emergencyQuestion: "ఇది అత్యవసరమా?",
  emergencyYes: "అవును, అత్యవసరం",
  emergencyNo: "లేదు, కొంచెం సహాయం కావాలి",
  emergencySending: "మీ కుటుంబానికి తెలియజేస్తున్నాం…",
  emergencyNotified: "మీ పిల్లలు, సంరక్షకులు మరియు బంధువులకు WhatsApp, ఈమెయిల్ మరియు టెక్స్ట్ మెసేజ్ ద్వారా తెలియజేశాం.",
  emergencyCall: "అత్యవసర నంబర్‌కు కాల్ చేయడానికి నొక్కండి",
  emergencyFailed: "సందేశాలు పంపలేకపోయాం. దయచేసి ఇప్పుడే కాల్ చేయండి.",
  signingOut: "లాగ్ అవుట్ అవుతోంది…",
  tapToSpeak: "మాట్లాడటానికి నొక్కండి",
  tapAgainToSend: "పంపడానికి మళ్ళీ నొక్కండి",
  pleaseWait: "దయచేసి వేచి ఉండండి",
  stopAndSend: "ఆపి పంపండి",
  typeInstead: "టైప్ చేయండి",
  typeYourAnswer: "మీ సమాధానం టైప్ చేయండి",
  send: "పంపండి",
  help: "సహాయం",
  callFamily: "కుటుంబానికి కాల్ చేయండి",
  askFamilyAddPhone: "ఫోన్ నంబర్ జోడించమని మీ కుటుంబాన్ని అడగండి",
  listening: "వింటున్నాము…",
  thinking: "ఆలోచిస్తున్నాము…",
  gettingReady: "సిద్ధమవుతోంది…",
  almostThere: "దాదాపు అయిపోయింది",
  notLinked: "మీ ప్రొఫైల్‌ను లింక్ చేయమని మీ కుటుంబాన్ని అడగండి",
  notLinkedHelp: "మీరు సైన్ అప్ చేసిన ఈమెయిల్ లేదా ఫోన్ నంబర్‌తో కుటుంబ సభ్యులు మిమ్మల్ని జోడించాలి.",
  parentsOnly: "ఈ పేజీ తల్లిదండ్రుల కోసం",
  goToStart: "ప్రారంభ పేజీకి వెళ్ళండి",
  loadFailedTitle: "మీ చాట్ తెరవలేకపోయాము",
  tryAgain: "మళ్ళీ ప్రయత్నించండి",
  voiceUnavailable: "ఇప్పుడు వాయిస్ అందుబాటులో లేదు. దయచేసి టైప్ చేయండి.",
  genericError: "ఏదో తప్పు జరిగింది. మళ్ళీ ప్రయత్నించండి.",
  heardNothing: "ఏమీ వినిపించలేదు. మైక్రోఫోన్ నొక్కి మళ్ళీ ప్రయత్నించండి.",
  micBlocked: "మైక్రోఫోన్ వాడలేకపోయాము. దయచేసి అనుమతించండి, లేదా కింద టైప్ చేయండి.",
  voiceNotOnPhone: "ఈ ఫోన్‌లో వాయిస్ అందుబాటులో లేదు. కింద టైప్ చేయండి.",
  conversation: "సంభాషణ",
  botSays: "కేర్‌సర్కిల్ చెబుతోంది:",
  youSaid: "మీరు చెప్పింది:",
};

const ml: ParentStrings = {
  logOut: "ലോഗ് ഔട്ട്",
  photoOf: "ഫോട്ടോ",
  closePhoto: "അടയ്ക്കുക",
  emergencyQuestion: "ഇത് അടിയന്തരമാണോ?",
  emergencyYes: "അതെ, അടിയന്തരമാണ്",
  emergencyNo: "ഇല്ല, ഒരു സഹായം മതി",
  emergencySending: "കുടുംബത്തെ അറിയിക്കുന്നു…",
  emergencyNotified: "നിങ്ങളുടെ മക്കളെയും പരിചാരകരെയും ബന്ധുക്കളെയും WhatsApp, ഇമെയിൽ, ടെക്സ്റ്റ് മെസേജ് വഴി അറിയിച്ചു.",
  emergencyCall: "അടിയന്തര നമ്പറിലേക്ക് വിളിക്കാൻ ഇവിടെ തൊടുക",
  emergencyFailed: "അറിയിപ്പുകൾ അയയ്ക്കാനായില്ല. ദയവായി ഇപ്പോൾ വിളിക്കൂ.",
  signingOut: "ലോഗ് ഔട്ട് ചെയ്യുന്നു…",
  tapToSpeak: "സംസാരിക്കാൻ തൊടുക",
  tapAgainToSend: "അയയ്ക്കാൻ വീണ്ടും തൊടുക",
  pleaseWait: "ദയവായി കാത്തിരിക്കൂ",
  stopAndSend: "നിർത്തി അയയ്ക്കുക",
  typeInstead: "ടൈപ്പ് ചെയ്യുക",
  typeYourAnswer: "നിങ്ങളുടെ മറുപടി ടൈപ്പ് ചെയ്യുക",
  send: "അയയ്ക്കുക",
  help: "സഹായം",
  callFamily: "കുടുംബത്തെ വിളിക്കുക",
  askFamilyAddPhone: "ഫോൺ നമ്പർ ചേർക്കാൻ കുടുംബത്തോട് പറയുക",
  listening: "കേൾക്കുന്നു…",
  thinking: "ആലോചിക്കുന്നു…",
  gettingReady: "തയ്യാറാകുന്നു…",
  almostThere: "ഏതാണ്ട് കഴിഞ്ഞു",
  notLinked: "നിങ്ങളുടെ പ്രൊഫൈൽ ബന്ധിപ്പിക്കാൻ കുടുംബത്തോട് പറയുക",
  notLinkedHelp: "നിങ്ങൾ സൈൻ അപ്പ് ചെയ്ത ഇമെയിലോ ഫോൺ നമ്പറോ ഉപയോഗിച്ച് ഒരു കുടുംബാംഗം നിങ്ങളെ ചേർക്കണം.",
  parentsOnly: "ഈ പേജ് മാതാപിതാക്കൾക്കുള്ളതാണ്",
  goToStart: "തുടക്ക പേജിലേക്ക് പോകുക",
  loadFailedTitle: "നിങ്ങളുടെ ചാറ്റ് തുറക്കാനായില്ല",
  tryAgain: "വീണ്ടും ശ്രമിക്കുക",
  voiceUnavailable: "ഇപ്പോൾ ശബ്ദം ലഭ്യമല്ല. ദയവായി ടൈപ്പ് ചെയ്യുക.",
  genericError: "എന്തോ പിശക് പറ്റി. വീണ്ടും ശ്രമിക്കുക.",
  heardNothing: "ഒന്നും കേട്ടില്ല. മൈക്രോഫോൺ തൊട്ട് വീണ്ടും ശ്രമിക്കുക.",
  micBlocked: "മൈക്രോഫോൺ ഉപയോഗിക്കാനായില്ല. അനുവദിക്കുക, അല്ലെങ്കിൽ താഴെ ടൈപ്പ് ചെയ്യുക.",
  voiceNotOnPhone: "ഈ ഫോണിൽ ശബ്ദം ലഭ്യമല്ല. താഴെ ടൈപ്പ് ചെയ്യുക.",
  conversation: "സംഭാഷണം",
  botSays: "കെയർസർക്കിൾ പറയുന്നു:",
  youSaid: "നിങ്ങൾ പറഞ്ഞത്:",
};

const kn: ParentStrings = {
  logOut: "ಲಾಗ್ ಔಟ್",
  photoOf: "ಫೋಟೋ",
  closePhoto: "ಮುಚ್ಚಿ",
  emergencyQuestion: "ಇದು ತುರ್ತು ಪರಿಸ್ಥಿತಿಯೇ?",
  emergencyYes: "ಹೌದು, ತುರ್ತು",
  emergencyNo: "ಇಲ್ಲ, ಸ್ವಲ್ಪ ಸಹಾಯ ಬೇಕು",
  emergencySending: "ನಿಮ್ಮ ಕುಟುಂಬಕ್ಕೆ ತಿಳಿಸುತ್ತಿದ್ದೇವೆ…",
  emergencyNotified: "ನಿಮ್ಮ ಮಕ್ಕಳು, ಆರೈಕೆದಾರರು ಮತ್ತು ಸಂಬಂಧಿಕರಿಗೆ WhatsApp, ಇಮೇಲ್ ಮತ್ತು ಟೆಕ್ಸ್ಟ್ ಮೆಸೇಜ್ ಮೂಲಕ ತಿಳಿಸಿದ್ದೇವೆ.",
  emergencyCall: "ತುರ್ತು ಸಂಖ್ಯೆಗೆ ಕರೆ ಮಾಡಲು ಒತ್ತಿ",
  emergencyFailed: "ಸಂದೇಶ ಕಳುಹಿಸಲಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಈಗಲೇ ಕರೆ ಮಾಡಿ.",
  signingOut: "ಲಾಗ್ ಔಟ್ ಆಗುತ್ತಿದೆ…",
  tapToSpeak: "ಮಾತನಾಡಲು ಒತ್ತಿ",
  tapAgainToSend: "ಕಳುಹಿಸಲು ಮತ್ತೆ ಒತ್ತಿ",
  pleaseWait: "ದಯವಿಟ್ಟು ಕಾಯಿರಿ",
  stopAndSend: "ನಿಲ್ಲಿಸಿ ಕಳುಹಿಸಿ",
  typeInstead: "ಟೈಪ್ ಮಾಡಿ",
  typeYourAnswer: "ನಿಮ್ಮ ಉತ್ತರವನ್ನು ಟೈಪ್ ಮಾಡಿ",
  send: "ಕಳುಹಿಸಿ",
  help: "ಸಹಾಯ",
  callFamily: "ಕುಟುಂಬಕ್ಕೆ ಕರೆ ಮಾಡಿ",
  askFamilyAddPhone: "ಫೋನ್ ಸಂಖ್ಯೆ ಸೇರಿಸಲು ನಿಮ್ಮ ಕುಟುಂಬವನ್ನು ಕೇಳಿ",
  listening: "ಕೇಳುತ್ತಿದ್ದೇವೆ…",
  thinking: "ಯೋಚಿಸುತ್ತಿದ್ದೇವೆ…",
  gettingReady: "ಸಿದ್ಧವಾಗುತ್ತಿದೆ…",
  almostThere: "ಬಹುತೇಕ ಮುಗಿಯಿತು",
  notLinked: "ನಿಮ್ಮ ಪ್ರೊಫೈಲ್ ಅನ್ನು ಲಿಂಕ್ ಮಾಡಲು ಕುಟುಂಬವನ್ನು ಕೇಳಿ",
  notLinkedHelp: "ನೀವು ಸೈನ್ ಅಪ್ ಮಾಡಿದ ಇಮೇಲ್ ಅಥವಾ ಫೋನ್ ಸಂಖ್ಯೆಯಿಂದ ಕುಟುಂಬದ ಸದಸ್ಯರು ನಿಮ್ಮನ್ನು ಸೇರಿಸಬೇಕು.",
  parentsOnly: "ಈ ಪುಟ ಪೋಷಕರಿಗಾಗಿ",
  goToStart: "ಆರಂಭ ಪುಟಕ್ಕೆ ಹೋಗಿ",
  loadFailedTitle: "ನಿಮ್ಮ ಚಾಟ್ ಲೋಡ್ ಆಗಲಿಲ್ಲ",
  tryAgain: "ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ",
  voiceUnavailable: "ಈಗ ಧ್ವನಿ ಲಭ್ಯವಿಲ್ಲ. ದಯವಿಟ್ಟು ಟೈಪ್ ಮಾಡಿ.",
  genericError: "ಏನೋ ತಪ್ಪಾಯಿತು. ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
  heardNothing: "ಏನೂ ಕೇಳಿಸಲಿಲ್ಲ. ಮೈಕ್ರೋಫೋನ್ ಒತ್ತಿ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.",
  micBlocked: "ಮೈಕ್ರೋಫೋನ್ ಬಳಸಲಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಅನುಮತಿಸಿ, ಅಥವಾ ಕೆಳಗೆ ಟೈಪ್ ಮಾಡಿ.",
  voiceNotOnPhone: "ಈ ಫೋನ್‌ನಲ್ಲಿ ಧ್ವನಿ ಲಭ್ಯವಿಲ್ಲ. ಕೆಳಗೆ ಟೈಪ್ ಮಾಡಿ.",
  conversation: "ಸಂಭಾಷಣೆ",
  botSays: "ಕೇರ್‌ಸರ್ಕಲ್ ಹೇಳುತ್ತದೆ:",
  youSaid: "ನೀವು ಹೇಳಿದ್ದು:",
};

const TABLE: Record<ParentLang, ParentStrings> = { en, hi, ta, te, ml, kn };

function normalise(code: string | null | undefined): ParentLang | null {
  const prefix = (code || "").toLowerCase().split(/[-_]/)[0];
  return prefix in TABLE ? (prefix as ParentLang) : null;
}

/** The chat language: the server's, else the browser locale, else English. */
export function parentLangCode(serverLanguage: string | null | undefined): ParentLang {
  return (
    normalise(serverLanguage) ??
    normalise(typeof navigator !== "undefined" ? navigator.language : null) ??
    "en"
  );
}

export function parentStrings(serverLanguage: string | null | undefined): ParentStrings {
  return TABLE[parentLangCode(serverLanguage)];
}
