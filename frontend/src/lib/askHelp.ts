// Ask for help: turns what the user typed ("I want to add an appointment") into a page to open.
// Only regular expressions are used here. matchAsk returns null when it is not sure, and the caller then asks the
// backend (POST .../ask), which is the only place an LLM is used. Keys must match backend/app/services/ask_help.py.

export interface AskDestination {
  label: string;
  path: (familyId: string) => string;
}

const fam = (p: string) => (familyId: string) => `/family/${familyId}${p}`;

export const DESTINATIONS = {
  overview: { label: "Overview", path: fam("") },
  "appointments.view": { label: "Appointments", path: fam("/appointments") },
  "appointments.add": { label: "Add appointment", path: fam("/appointments?new=1") },
  "tasks.view": { label: "Tasks", path: fam("/tasks") },
  "tasks.add": { label: "Add task", path: fam("/tasks?new=1") },
  "medicines.view": { label: "Medicines", path: fam("/medicines") },
  "medicines.add": { label: "Add medicine", path: fam("/medicines/new") },
  "prescription.scan": { label: "Scan prescription", path: fam("/prescription-scan") },
  "activity.view": { label: "CareVoice activity", path: fam("/activity") },
  "records.view": { label: "Records", path: fam("/records") },
  "members.view": { label: "Family members", path: fam("/members") },
  "care_profile.view": { label: "Care profile", path: () => "/parent-profile" },
  "care_profile.add": { label: "Add profile", path: (id: string) => `/onboarding/parent?add=1&family=${id}` },
  "my_profile.view": { label: "Manage Profile", path: fam("/manage-profile") },
  "notifications.view": { label: "Notification settings", path: fam("/notifications") },
} satisfies Record<string, AskDestination>;

export type AskKey = keyof typeof DESTINATIONS;

export function isAskKey(k: string | null | undefined): k is AskKey {
  return !!k && Object.prototype.hasOwnProperty.call(DESTINATIONS, k);
}

/** What a page opened by Ask for help carries in the router's location state. */
export interface AskState {
  id: number;
  text: string;
  familyId: string;
  key: AskKey;
  /** Pages already opened for this question, so "Not what I wanted" never opens one of them again. */
  tried: AskKey[];
}

interface Topic {
  words: RegExp;
  view: AskKey;
  add?: AskKey; // pages without a separate add form open the page itself
}

// Forgiving about common misspellings ("appoitment", "medecine").
const TOPICS: Topic[] = [
  { words: /\b(?:app?oi?n?t?e?ments?|doctor'?s? visits?|check-?ups?|consultations?|calendar|doctors?)\b/g, view: "appointments.view", add: "appointments.add" },
  { words: /\b(?:tasks?|to-?dos?|to do list|chores?|errands?)\b/g, view: "tasks.view", add: "tasks.add" },
  { words: /\bprescriptions?\b/g, view: "prescription.scan", add: "prescription.scan" },
  { words: /\b(?:med[ie]?cines?|medications?|meds|tablets?|pills?|doses?|dosage)\b/g, view: "medicines.view", add: "medicines.add" },
  { words: /\b(?:activity|activities|check-?ins?|conversations?|chat history)\b/g, view: "activity.view" },
  { words: /\b(?:records|reports?|summary|summaries)\b/g, view: "records.view" },
  { words: /\b(?:(?:family |care ?team )?members?|care ?team|care ?givers?|care ?takers?|permissions?|roles?)\b/g, view: "members.view" },
  { words: /\b(?:notifications?(?: settings?)?|alerts? settings?)\b/g, view: "notifications.view" },
  { words: /\b(?:my (?:own )?(?:profile|account|password|photo|name)|manage profile|account)\b/g, view: "my_profile.view" },
  { words: /\b(?:care profiles?|parent'?s? profiles?|profiles?|parents?|care recipients?)\b/g, view: "care_profile.view", add: "care_profile.add" },
  { words: /\b(?:overview|dashboard|home ?page|home)\b/g, view: "overview" },
];

const VIEW =
  /\b(?:view|see|show|open|check|look|list|find|go to|goto|take me|move to|what|when|which|who|where|did|has|is|are|any|edit|change|update|cancel|delete|remove|complete|finish|mark|reschedule|manage|track)\b/;
const ADD =
  /\b(?:add|adding|create|creating|make|making|new|book|booking|fix up|set up|setup|set|start|register|invite|upload|scan|enter|need an?|schedule (?:an?|another|the|my|new)|assign)\b/;
// Words that make a simple reading unsafe: let the fallback decide.
const UNSURE = /\b(?:do not|don'?t|doesn'?t|not|never|without|instead of|except)\b/;
const JOIN = /\b(?:and|then|also|or)\b|[,;&]/;
const VISIT_DOCTOR = /\b(?:see|visit|meet|consult)(?:ing)? (?:an?|the|another) doctor\b/;
// Opening words that say nothing about the page.
const LEAD =
  /^(?:(?:hi|hello|hey|ok|okay|please|can you|could you|can i|could i|how (?:do|can|to)(?: i| we)?|where (?:do|can) i|help me(?: to)?|i(?: would|'d)? (?:want|like|wish)(?: to)?|i need to|i wanna|let me|let's|to)\b[\s,]*)+/;

interface Hit {
  topic: Topic;
  start: number;
  end: number;
}

export function matchAsk(raw: string): AskKey | null {
  const text = raw
    .toLowerCase()
    .replace(/[‘’]/g, "'")
    .replace(/\s+/g, " ")
    .trim()
    .replace(LEAD, "");
  if (!text || UNSURE.test(text)) return null;

  const hits: Hit[] = [];
  for (const topic of TOPICS) {
    for (const m of text.matchAll(topic.words)) {
      const start = m.index ?? 0;
      const end = start + m[0].length;
      // A topic higher in the list keeps words it already took ("my profile" over "profile").
      if (!hits.some((h) => start < h.end && end > h.start)) hits.push({ topic, start, end });
    }
  }
  if (hits.length === 0) return null;
  hits.sort((a, b) => a.start - b.start);

  // "add a task to refill medicine" is about the task, and so is "medicine task".
  let chosen = hits[0];
  for (const next of hits.slice(1)) {
    if (next.topic === chosen.topic) continue;
    const between = text.slice(chosen.end, next.start);
    if (JOIN.test(between)) return null; // two things asked at once
    if (between.trim() === "") chosen = next;
  }

  if (chosen.topic.add === "appointments.add" && VISIT_DOCTOR.test(text)) return "appointments.add";
  const add = text.search(ADD);
  const view = text.search(VIEW);
  const wantsAdd = add >= 0 && (view < 0 || add < view);
  return (wantsAdd && chosen.topic.add) || chosen.topic.view;
}
