// UI text for the parent's "My notes" panel (components/ParentNotes.tsx), in the chat's language.
// NOTE: like parentChatStrings.ts, the non-English text is simple and needs native-speaker review.

import { parentLangCode, type ParentLang } from "./parentChatStrings";

export interface NotesStrings {
  locale: string;
  myNotes: string;
  openNotes: string;
  close: string;
  writeNote: string;
  empty: string;
  loadFailed: string;
  tryAgain: string;
  // step 1
  whatToNote: string;
  placeholder: string;
  examplesLabel: string;
  examples: string[];
  next: string;
  back: string;
  cancel: string;
  // step 2
  whenRemind: string;
  noReminder: string;
  inOneHour: string;
  todayAt6: string;
  tomorrowAt6: string;
  tomorrowAt9: string;
  pickTime: string;
  timeInPast: string;
  // step 3
  whoRemind: string;
  whoFor: string;
  me: string;
  meHint: string;
  // step 4
  taskFor: (name: string) => string;
  alsoRemind: (name: string) => string;
  yesRemind: string;
  noJustTask: string;
  // save + list
  save: string;
  saving: string;
  savedPlain: string;
  savedForMe: (when: string) => string;
  savedTask: (name: string) => string;
  savedTaskReminder: (name: string, when: string) => string;
  savedTaskReminderNow: (name: string) => string;
  forYou: string;
  taskForShort: (name: string) => string;
  reminderAt: (when: string) => string;
  reminderSent: string;
  noReminderLabel: string;
  remove: string;
  confirmRemove: string;
  yesRemove: string;
  keep: string;
  today: string;
  tomorrow: string;
}

const en: NotesStrings = {
  locale: "en-IN",
  myNotes: "My notes",
  openNotes: "Notes",
  close: "Back to chat",
  writeNote: "+ Write a note",
  empty: "No notes yet. Write down anything you want to remember.",
  loadFailed: "Couldn't load your notes.",
  tryAgain: "Try again",
  whatToNote: "What would you like to note down?",
  placeholder: "Type your note here",
  examplesLabel: "For example",
  examples: [
    "Today I need to take medicines at 6 pm.",
    "I have kept my medicines in the drawer.",
    "I have to take my calcium supplement.",
  ],
  next: "Next",
  back: "Back",
  cancel: "Cancel",
  whenRemind: "When should we remind you?",
  noReminder: "No reminder",
  inOneHour: "In 1 hour",
  todayAt6: "Today at 6 PM",
  tomorrowAt6: "Tomorrow at 6 PM",
  tomorrowAt9: "Tomorrow at 9 AM",
  pickTime: "Choose a time",
  timeInPast: "Please choose a time later than now.",
  whoRemind: "Who should get this reminder?",
  whoFor: "Who is this note for?",
  me: "Me",
  meHint: "Only you",
  taskFor: (n) => `We will add this as a task for ${n}.`,
  alsoRemind: (n) => `Should we also send ${n} a reminder?`,
  yesRemind: "Yes, send a reminder",
  noJustTask: "No, just the task",
  save: "Save note",
  saving: "Saving…",
  savedPlain: "Saved in your notes.",
  savedForMe: (w) => `Saved. We will remind you ${w}.`,
  savedTask: (n) => `Saved and added as a task for ${n}.`,
  savedTaskReminder: (n, w) => `Saved. ${n} has the task and will be reminded ${w}.`,
  savedTaskReminderNow: (n) => `Saved. ${n} has the task and a reminder was sent.`,
  forYou: "For you",
  taskForShort: (n) => `Task for ${n}`,
  reminderAt: (w) => `Reminder ${w}`,
  reminderSent: "Reminder sent",
  noReminderLabel: "No reminder",
  remove: "Delete",
  confirmRemove: "Delete this note?",
  yesRemove: "Yes, delete",
  keep: "Keep it",
  today: "today",
  tomorrow: "tomorrow",
};

const ta: NotesStrings = {
  ...en,
  locale: "ta-IN",
  myNotes: "என் குறிப்புகள்",
  openNotes: "குறிப்புகள்",
  close: "அரட்டைக்குத் திரும்பு",
  writeNote: "+ குறிப்பு எழுது",
  empty: "இன்னும் குறிப்புகள் இல்லை. நினைவில் வைக்க வேண்டியதை எழுதுங்கள்.",
  loadFailed: "குறிப்புகளைத் திறக்க முடியவில்லை.",
  tryAgain: "மீண்டும் முயற்சி",
  whatToNote: "என்ன குறித்து வைக்க வேண்டும்?",
  placeholder: "உங்கள் குறிப்பை இங்கே எழுதுங்கள்",
  examplesLabel: "உதாரணம்",
  examples: [
    "இன்று மாலை 6 மணிக்கு மாத்திரை சாப்பிட வேண்டும்.",
    "என் மாத்திரைகளை டிராயரில் வைத்திருக்கிறேன்.",
    "கால்சியம் மாத்திரை சாப்பிட வேண்டும்.",
  ],
  next: "அடுத்து",
  back: "பின்",
  cancel: "ரத்து",
  whenRemind: "எப்போது நினைவூட்ட வேண்டும்?",
  noReminder: "நினைவூட்டல் வேண்டாம்",
  inOneHour: "1 மணி நேரத்தில்",
  todayAt6: "இன்று மாலை 6 மணிக்கு",
  tomorrowAt6: "நாளை மாலை 6 மணிக்கு",
  tomorrowAt9: "நாளை காலை 9 மணிக்கு",
  pickTime: "நேரத்தைத் தேர்ந்தெடு",
  timeInPast: "இப்போதைக்குப் பிறகான நேரத்தைத் தேர்ந்தெடுங்கள்.",
  whoRemind: "யாருக்கு நினைவூட்ட வேண்டும்?",
  whoFor: "இந்தக் குறிப்பு யாருக்கு?",
  me: "எனக்கு",
  meHint: "நீங்கள் மட்டும்",
  taskFor: (n) => `இது ${n} அவர்களுக்கு ஒரு பணியாகச் சேர்க்கப்படும்.`,
  alsoRemind: (n) => `${n} அவர்களுக்கும் நினைவூட்டல் அனுப்பலாமா?`,
  yesRemind: "ஆம், அனுப்பு",
  noJustTask: "வேண்டாம், பணி மட்டும்",
  save: "சேமி",
  saving: "சேமிக்கிறது…",
  savedPlain: "குறிப்புகளில் சேமிக்கப்பட்டது.",
  savedForMe: (w) => `சேமிக்கப்பட்டது. ${w} நினைவூட்டுவோம்.`,
  savedTask: (n) => `சேமிக்கப்பட்டது, ${n} அவர்களுக்குப் பணியாகச் சேர்க்கப்பட்டது.`,
  savedTaskReminder: (n, w) => `சேமிக்கப்பட்டது. ${n} அவர்களுக்கு ${w} நினைவூட்டப்படும்.`,
  savedTaskReminderNow: (n) => `சேமிக்கப்பட்டது. ${n} அவர்களுக்கு நினைவூட்டல் அனுப்பப்பட்டது.`,
  forYou: "உங்களுக்கு",
  taskForShort: (n) => `${n} அவர்களுக்கான பணி`,
  reminderAt: (w) => `நினைவூட்டல் ${w}`,
  reminderSent: "நினைவூட்டல் அனுப்பப்பட்டது",
  noReminderLabel: "நினைவூட்டல் இல்லை",
  remove: "நீக்கு",
  confirmRemove: "இந்தக் குறிப்பை நீக்கவா?",
  yesRemove: "ஆம், நீக்கு",
  keep: "வேண்டாம்",
  today: "இன்று",
  tomorrow: "நாளை",
};

const hi: NotesStrings = {
  ...en,
  locale: "hi-IN",
  myNotes: "मेरे नोट्स",
  openNotes: "नोट्स",
  close: "चैट पर वापस",
  writeNote: "+ नोट लिखें",
  empty: "अभी कोई नोट नहीं है। जो याद रखना है, लिख लीजिए।",
  loadFailed: "नोट्स नहीं खुल पाए।",
  tryAgain: "फिर कोशिश करें",
  whatToNote: "आप क्या लिखना चाहेंगे?",
  placeholder: "अपना नोट यहाँ लिखें",
  examplesLabel: "उदाहरण",
  examples: [
    "आज शाम 6 बजे दवा लेनी है।",
    "मैंने अपनी दवाइयाँ दराज़ में रखी हैं।",
    "मुझे कैल्शियम की गोली लेनी है।",
  ],
  next: "आगे",
  back: "पीछे",
  cancel: "रद्द करें",
  whenRemind: "आपको कब याद दिलाएँ?",
  noReminder: "याद न दिलाएँ",
  inOneHour: "1 घंटे में",
  todayAt6: "आज शाम 6 बजे",
  tomorrowAt6: "कल शाम 6 बजे",
  tomorrowAt9: "कल सुबह 9 बजे",
  pickTime: "समय चुनें",
  timeInPast: "कृपया अभी के बाद का समय चुनें।",
  whoRemind: "यह याद किसे दिलाएँ?",
  whoFor: "यह नोट किसके लिए है?",
  me: "मुझे",
  meHint: "सिर्फ़ आप",
  taskFor: (n) => `इसे ${n} के लिए एक काम के रूप में जोड़ा जाएगा।`,
  alsoRemind: (n) => `क्या ${n} को भी याद दिलाएँ?`,
  yesRemind: "हाँ, याद दिलाएँ",
  noJustTask: "नहीं, सिर्फ़ काम",
  save: "नोट सेव करें",
  saving: "सेव हो रहा है…",
  savedPlain: "आपके नोट्स में सेव हो गया।",
  savedForMe: (w) => `सेव हो गया। हम आपको ${w} याद दिलाएँगे।`,
  savedTask: (n) => `सेव हो गया और ${n} के लिए काम जोड़ दिया गया।`,
  savedTaskReminder: (n, w) => `सेव हो गया। ${n} को ${w} याद दिलाया जाएगा।`,
  savedTaskReminderNow: (n) => `सेव हो गया। ${n} को याद दिला दिया गया।`,
  forYou: "आपके लिए",
  taskForShort: (n) => `${n} के लिए काम`,
  reminderAt: (w) => `याद ${w}`,
  reminderSent: "याद दिला दिया गया",
  noReminderLabel: "याद नहीं दिलाना",
  remove: "हटाएँ",
  confirmRemove: "यह नोट हटाएँ?",
  yesRemove: "हाँ, हटाएँ",
  keep: "रहने दें",
  today: "आज",
  tomorrow: "कल",
};

const te: NotesStrings = {
  ...en,
  locale: "te-IN",
  myNotes: "నా నోట్స్",
  openNotes: "నోట్స్",
  close: "చాట్‌కు తిరిగి",
  writeNote: "+ నోట్ రాయండి",
  empty: "ఇంకా నోట్స్ లేవు. గుర్తుంచుకోవలసింది రాసుకోండి.",
  loadFailed: "నోట్స్ తెరవలేకపోయాం.",
  tryAgain: "మళ్ళీ ప్రయత్నించండి",
  whatToNote: "మీరు ఏమి రాసుకోవాలనుకుంటున్నారు?",
  placeholder: "మీ నోట్ ఇక్కడ రాయండి",
  examplesLabel: "ఉదాహరణకు",
  examples: [
    "ఈ రోజు సాయంత్రం 6 గంటలకు మందులు వేసుకోవాలి.",
    "నా మందులు డ్రాయర్‌లో పెట్టాను.",
    "కాల్షియం మాత్ర వేసుకోవాలి.",
  ],
  next: "తర్వాత",
  back: "వెనక్కి",
  cancel: "రద్దు",
  whenRemind: "మీకు ఎప్పుడు గుర్తు చేయాలి?",
  noReminder: "గుర్తు చేయవద్దు",
  inOneHour: "1 గంటలో",
  todayAt6: "ఈ రోజు సాయంత్రం 6కి",
  tomorrowAt6: "రేపు సాయంత్రం 6కి",
  tomorrowAt9: "రేపు ఉదయం 9కి",
  pickTime: "సమయం ఎంచుకోండి",
  timeInPast: "దయచేసి ఇప్పటి తర్వాతి సమయం ఎంచుకోండి.",
  whoRemind: "ఎవరికి గుర్తు చేయాలి?",
  whoFor: "ఈ నోట్ ఎవరి కోసం?",
  me: "నాకు",
  meHint: "మీకు మాత్రమే",
  taskFor: (n) => `దీన్ని ${n} కోసం ఒక పనిగా చేరుస్తాం.`,
  alsoRemind: (n) => `${n}కి కూడా గుర్తు చేయాలా?`,
  yesRemind: "అవును, పంపండి",
  noJustTask: "వద్దు, పని మాత్రమే",
  save: "సేవ్ చేయండి",
  saving: "సేవ్ అవుతోంది…",
  savedPlain: "మీ నోట్స్‌లో సేవ్ అయింది.",
  savedForMe: (w) => `సేవ్ అయింది. ${w} గుర్తు చేస్తాం.`,
  savedTask: (n) => `సేవ్ అయింది, ${n} కోసం పనిగా చేర్చాం.`,
  savedTaskReminder: (n, w) => `సేవ్ అయింది. ${n}కి ${w} గుర్తు చేస్తాం.`,
  savedTaskReminderNow: (n) => `సేవ్ అయింది. ${n}కి గుర్తు చేశాం.`,
  forYou: "మీ కోసం",
  taskForShort: (n) => `${n} కోసం పని`,
  reminderAt: (w) => `గుర్తు ${w}`,
  reminderSent: "గుర్తు పంపాం",
  noReminderLabel: "గుర్తు లేదు",
  remove: "తొలగించు",
  confirmRemove: "ఈ నోట్ తొలగించాలా?",
  yesRemove: "అవును, తొలగించు",
  keep: "వద్దు",
  today: "ఈ రోజు",
  tomorrow: "రేపు",
};

const ml: NotesStrings = {
  ...en,
  locale: "ml-IN",
  myNotes: "എന്റെ കുറിപ്പുകൾ",
  openNotes: "കുറിപ്പുകൾ",
  close: "ചാറ്റിലേക്ക് മടങ്ങുക",
  writeNote: "+ കുറിപ്പ് എഴുതുക",
  empty: "ഇതുവരെ കുറിപ്പുകളില്ല. ഓർക്കേണ്ടത് എഴുതിവയ്ക്കൂ.",
  loadFailed: "കുറിപ്പുകൾ തുറക്കാനായില്ല.",
  tryAgain: "വീണ്ടും ശ്രമിക്കുക",
  whatToNote: "എന്താണ് കുറിച്ചുവയ്ക്കേണ്ടത്?",
  placeholder: "നിങ്ങളുടെ കുറിപ്പ് ഇവിടെ എഴുതുക",
  examplesLabel: "ഉദാഹരണത്തിന്",
  examples: [
    "ഇന്ന് വൈകിട്ട് 6 മണിക്ക് മരുന്ന് കഴിക്കണം.",
    "എന്റെ മരുന്നുകൾ ഡ്രോയറിൽ വച്ചിട്ടുണ്ട്.",
    "കാൽസ്യം ഗുളിക കഴിക്കണം.",
  ],
  next: "അടുത്തത്",
  back: "പിന്നോട്ട്",
  cancel: "റദ്ദാക്കുക",
  whenRemind: "എപ്പോഴാണ് ഓർമ്മിപ്പിക്കേണ്ടത്?",
  noReminder: "ഓർമ്മപ്പെടുത്തൽ വേണ്ട",
  inOneHour: "1 മണിക്കൂറിനുള്ളിൽ",
  todayAt6: "ഇന്ന് വൈകിട്ട് 6ന്",
  tomorrowAt6: "നാളെ വൈകിട്ട് 6ന്",
  tomorrowAt9: "നാളെ രാവിലെ 9ന്",
  pickTime: "സമയം തിരഞ്ഞെടുക്കുക",
  timeInPast: "ഇപ്പോഴത്തേതിനു ശേഷമുള്ള സമയം തിരഞ്ഞെടുക്കുക.",
  whoRemind: "ആരെയാണ് ഓർമ്മിപ്പിക്കേണ്ടത്?",
  whoFor: "ഈ കുറിപ്പ് ആർക്കാണ്?",
  me: "എനിക്ക്",
  meHint: "നിങ്ങൾക്ക് മാത്രം",
  taskFor: (n) => `ഇത് ${n}യ്ക്കുള്ള ഒരു ജോലിയായി ചേർക്കും.`,
  alsoRemind: (n) => `${n}യെയും ഓർമ്മിപ്പിക്കണോ?`,
  yesRemind: "അതെ, അയയ്ക്കൂ",
  noJustTask: "വേണ്ട, ജോലി മാത്രം",
  save: "സേവ് ചെയ്യുക",
  saving: "സേവ് ചെയ്യുന്നു…",
  savedPlain: "കുറിപ്പുകളിൽ സേവ് ചെയ്തു.",
  savedForMe: (w) => `സേവ് ചെയ്തു. ${w} ഓർമ്മിപ്പിക്കും.`,
  savedTask: (n) => `സേവ് ചെയ്തു, ${n}യ്ക്ക് ജോലിയായി ചേർത്തു.`,
  savedTaskReminder: (n, w) => `സേവ് ചെയ്തു. ${n}യെ ${w} ഓർമ്മിപ്പിക്കും.`,
  savedTaskReminderNow: (n) => `സേവ് ചെയ്തു. ${n}യെ ഓർമ്മിപ്പിച്ചു.`,
  forYou: "നിങ്ങൾക്ക്",
  taskForShort: (n) => `${n}യ്ക്കുള്ള ജോലി`,
  reminderAt: (w) => `ഓർമ്മ ${w}`,
  reminderSent: "ഓർമ്മപ്പെടുത്തൽ അയച്ചു",
  noReminderLabel: "ഓർമ്മപ്പെടുത്തൽ ഇല്ല",
  remove: "നീക്കുക",
  confirmRemove: "ഈ കുറിപ്പ് നീക്കണോ?",
  yesRemove: "അതെ, നീക്കുക",
  keep: "വേണ്ട",
  today: "ഇന്ന്",
  tomorrow: "നാളെ",
};

const kn: NotesStrings = {
  ...en,
  locale: "kn-IN",
  myNotes: "ನನ್ನ ಟಿಪ್ಪಣಿಗಳು",
  openNotes: "ಟಿಪ್ಪಣಿಗಳು",
  close: "ಚಾಟ್‌ಗೆ ಹಿಂತಿರುಗಿ",
  writeNote: "+ ಟಿಪ್ಪಣಿ ಬರೆಯಿರಿ",
  empty: "ಇನ್ನೂ ಟಿಪ್ಪಣಿಗಳಿಲ್ಲ. ನೆನಪಿಡಬೇಕಾದುದನ್ನು ಬರೆದಿಡಿ.",
  loadFailed: "ಟಿಪ್ಪಣಿಗಳನ್ನು ತೆರೆಯಲಾಗಲಿಲ್ಲ.",
  tryAgain: "ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ",
  whatToNote: "ನೀವು ಏನನ್ನು ಬರೆದಿಡಲು ಬಯಸುತ್ತೀರಿ?",
  placeholder: "ನಿಮ್ಮ ಟಿಪ್ಪಣಿಯನ್ನು ಇಲ್ಲಿ ಬರೆಯಿರಿ",
  examplesLabel: "ಉದಾಹರಣೆಗೆ",
  examples: [
    "ಇಂದು ಸಂಜೆ 6 ಗಂಟೆಗೆ ಔಷಧಿ ತೆಗೆದುಕೊಳ್ಳಬೇಕು.",
    "ನನ್ನ ಔಷಧಿಗಳನ್ನು ಡ್ರಾಯರ್‌ನಲ್ಲಿ ಇಟ್ಟಿದ್ದೇನೆ.",
    "ಕ್ಯಾಲ್ಸಿಯಂ ಮಾತ್ರೆ ತೆಗೆದುಕೊಳ್ಳಬೇಕು.",
  ],
  next: "ಮುಂದೆ",
  back: "ಹಿಂದೆ",
  cancel: "ರದ್ದುಮಾಡಿ",
  whenRemind: "ನಿಮಗೆ ಯಾವಾಗ ನೆನಪಿಸಬೇಕು?",
  noReminder: "ನೆನಪಿಸಬೇಡಿ",
  inOneHour: "1 ಗಂಟೆಯಲ್ಲಿ",
  todayAt6: "ಇಂದು ಸಂಜೆ 6ಕ್ಕೆ",
  tomorrowAt6: "ನಾಳೆ ಸಂಜೆ 6ಕ್ಕೆ",
  tomorrowAt9: "ನಾಳೆ ಬೆಳಿಗ್ಗೆ 9ಕ್ಕೆ",
  pickTime: "ಸಮಯ ಆಯ್ಕೆಮಾಡಿ",
  timeInPast: "ದಯವಿಟ್ಟು ಈಗಿನ ನಂತರದ ಸಮಯ ಆಯ್ಕೆಮಾಡಿ.",
  whoRemind: "ಯಾರಿಗೆ ನೆನಪಿಸಬೇಕು?",
  whoFor: "ಈ ಟಿಪ್ಪಣಿ ಯಾರಿಗಾಗಿ?",
  me: "ನನಗೆ",
  meHint: "ನಿಮಗೆ ಮಾತ್ರ",
  taskFor: (n) => `ಇದನ್ನು ${n} ಅವರಿಗೆ ಒಂದು ಕೆಲಸವಾಗಿ ಸೇರಿಸುತ್ತೇವೆ.`,
  alsoRemind: (n) => `${n} ಅವರಿಗೂ ನೆನಪಿಸಬೇಕೆ?`,
  yesRemind: "ಹೌದು, ಕಳುಹಿಸಿ",
  noJustTask: "ಬೇಡ, ಕೆಲಸ ಮಾತ್ರ",
  save: "ಉಳಿಸಿ",
  saving: "ಉಳಿಸಲಾಗುತ್ತಿದೆ…",
  savedPlain: "ನಿಮ್ಮ ಟಿಪ್ಪಣಿಗಳಲ್ಲಿ ಉಳಿಸಲಾಗಿದೆ.",
  savedForMe: (w) => `ಉಳಿಸಲಾಗಿದೆ. ${w} ನೆನಪಿಸುತ್ತೇವೆ.`,
  savedTask: (n) => `ಉಳಿಸಲಾಗಿದೆ, ${n} ಅವರಿಗೆ ಕೆಲಸವಾಗಿ ಸೇರಿಸಲಾಗಿದೆ.`,
  savedTaskReminder: (n, w) => `ಉಳಿಸಲಾಗಿದೆ. ${n} ಅವರಿಗೆ ${w} ನೆನಪಿಸಲಾಗುವುದು.`,
  savedTaskReminderNow: (n) => `ಉಳಿಸಲಾಗಿದೆ. ${n} ಅವರಿಗೆ ನೆನಪಿಸಲಾಗಿದೆ.`,
  forYou: "ನಿಮಗಾಗಿ",
  taskForShort: (n) => `${n} ಅವರಿಗೆ ಕೆಲಸ`,
  reminderAt: (w) => `ನೆನಪು ${w}`,
  reminderSent: "ನೆನಪು ಕಳುಹಿಸಲಾಗಿದೆ",
  noReminderLabel: "ನೆನಪಿಲ್ಲ",
  remove: "ಅಳಿಸಿ",
  confirmRemove: "ಈ ಟಿಪ್ಪಣಿಯನ್ನು ಅಳಿಸಬೇಕೆ?",
  yesRemove: "ಹೌದು, ಅಳಿಸಿ",
  keep: "ಬೇಡ",
  today: "ಇಂದು",
  tomorrow: "ನಾಳೆ",
};

const TABLE: Record<ParentLang, NotesStrings> = { en, ta, hi, te, ml, kn };

export function notesStrings(serverLanguage: string | null | undefined): NotesStrings {
  return TABLE[parentLangCode(serverLanguage)];
}
