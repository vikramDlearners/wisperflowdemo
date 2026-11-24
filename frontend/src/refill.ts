// Suggested refill date for a medicine: today + the days the tablets left will last, minus a small buffer
// so the family can buy more before they run out.
//
// Tablets a day = doses a day × tablets per dose.
//   Doses a day: the reminder times if any are set, else read from the schedule text ("twice daily",
//   "after breakfast and dinner", "9:00 AM and 8:00 PM", "BD"…), else 1.
//   Tablets per dose: "2 tablets", "half a tablet", "1½"… in the schedule text, else 1.

export const REFILL_BUFFER_DAYS = 2;

const FREQUENCY: [RegExp, number][] = [
  [/\b(four times|4 times|qid|qds)\b/i, 4],
  [/\b(thrice|three times|3 times|tds|tid)\b/i, 3],
  [/\b(twice|two times|2 times|bd|bid)\b/i, 2],
  [/\b(once|one time|1 time|od|daily|every day|a day)\b/i, 1],
];
const MEAL_WORDS = [
  /\bbreakfast\b/i,
  /\blunch\b/i,
  /\b(dinner|supper)\b/i,
  /\bmorning\b/i,
  /\bafternoon\b/i,
  /\b(evening)\b/i,
  /\b(night|bedtime|bed time)\b/i,
];

function dosesFromText(text: string): number | null {
  const t = text.toLowerCase();
  // "1-0-1" / "1-1-1" style (morning-afternoon-night).
  const pattern = t.match(/\b([0-2](?:\.5)?)\s*-\s*([0-2](?:\.5)?)\s*-\s*([0-2](?:\.5)?)\b/);
  if (pattern) {
    const n = [pattern[1], pattern[2], pattern[3]].filter((x) => Number(x) > 0).length;
    if (n > 0) return n;
  }
  for (const [re, n] of FREQUENCY.slice(0, 3)) if (re.test(t)) return n;
  const clockTimes = t.match(/\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b/g);
  if (clockTimes && clockTimes.length > 1) return clockTimes.length;
  // "after breakfast and dinner" counts each mealtime once ("morning" and "breakfast" are the same dose).
  const meals = MEAL_WORDS.filter((re) => re.test(t)).length;
  const morningTwice = /\bbreakfast\b/i.test(t) && /\bmorning\b/i.test(t) ? 1 : 0;
  const nightTwice = /\b(dinner|supper)\b/i.test(t) && /\b(night|bedtime|bed time)\b/i.test(t) ? 1 : 0;
  const distinct = meals - morningTwice - nightTwice;
  if (distinct > 1) return distinct;
  if (FREQUENCY[3][0].test(t) || distinct === 1) return 1;
  return null;
}

function tabletsPerDose(text: string): number {
  const t = text.toLowerCase();
  if (/\b(half|½)\b/.test(t) || /\b0?\.5\s*(tablet|tab|pill|capsule)/.test(t)) return 0.5;
  const m = t.match(/\b(\d+(?:\.\d+)?)\s*(tablets?|tabs?|pills?|capsules?)\b/);
  if (m) return Number(m[1]);
  const words: Record<string, number> = { one: 1, two: 2, three: 3 };
  const w = t.match(/\b(one|two|three)\s*(tablets?|tabs?|pills?|capsules?)\b/);
  if (w) return words[w[1]];
  return 1;
}

export interface RefillEstimate {
  perDay: number;
  days: number; // whole days the tablets last, counting today
  runsOut: Date;
  refillBy: Date;
  dosesFrom: "times" | "schedule" | "default";
}

/** null when the quantity is missing or not a positive number. */
export function estimateRefill(
  quantity: string,
  schedule: string,
  reminderTimes: string[],
  today: Date = new Date(),
): RefillEstimate | null {
  const qty = Number(quantity);
  if (quantity.trim() === "" || !Number.isFinite(qty) || qty <= 0) return null;
  const textDoses = dosesFromText(schedule);
  const timeDoses = new Set(reminderTimes.filter(Boolean)).size;
  const doses = timeDoses > 0 ? timeDoses : textDoses ?? 1;
  const perDay = doses * tabletsPerDose(schedule);
  const days = Math.max(1, Math.floor(qty / perDay));
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const runsOut = new Date(start);
  runsOut.setDate(start.getDate() + days);
  const refillBy = new Date(runsOut);
  refillBy.setDate(runsOut.getDate() - REFILL_BUFFER_DAYS);
  if (refillBy < start) refillBy.setTime(start.getTime());
  return {
    perDay,
    days,
    runsOut,
    refillBy,
    dosesFrom: timeDoses > 0 ? "times" : textDoses != null ? "schedule" : "default",
  };
}

/** YYYY-MM-DD in local time, for <input type="date">. */
export function toDateInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
