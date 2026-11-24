// A time picker that always shows 12-hour time with AM / PM, whatever the computer's region setting
// (the browser's own <input type="time"> shows 24-hour time on many systems).
// The value stays "HH:MM" in 24-hour time, exactly what the API stores: "9:30 PM" <-> "21:30".

interface TimeSelectProps {
  value: string; // "HH:MM" (24-hour); "" shows 12:00 PM
  onChange: (value: string) => void;
  ariaLabel: string;
  className?: string;
}

const HOURS = [12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
const MINUTES = Array.from({ length: 12 }, (_, i) => i * 5);
const pad = (n: number) => String(n).padStart(2, "0");

function split(value: string): { hour12: number; minute: number; pm: boolean } {
  const m = /^(\d{1,2}):(\d{2})$/.exec(value);
  const h24 = m ? Math.min(23, Number(m[1])) : 12;
  const minute = m ? Math.min(59, Number(m[2])) : 0;
  return { hour12: h24 % 12 || 12, minute, pm: h24 >= 12 };
}

function join(hour12: number, minute: number, pm: boolean): string {
  const h24 = (hour12 % 12) + (pm ? 12 : 0);
  return `${pad(h24)}:${pad(minute)}`;
}

export default function TimeSelect({ value, onChange, ariaLabel, className }: TimeSelectProps) {
  const { hour12, minute, pm } = split(value);
  // Keep an odd minute (e.g. 9:07 from a prescription) selectable instead of silently rounding it.
  const minutes = MINUTES.includes(minute) ? MINUTES : [...MINUTES, minute].sort((a, b) => a - b);
  return (
    <span className={`time-select${className ? ` ${className}` : ""}`} role="group" aria-label={ariaLabel}>
      <select
        aria-label={`${ariaLabel}: hour`}
        value={hour12}
        onChange={(e) => onChange(join(Number(e.target.value), minute, pm))}
      >
        {HOURS.map((h) => (
          <option key={h} value={h}>
            {h}
          </option>
        ))}
      </select>
      <span className="time-select-colon" aria-hidden="true">
        :
      </span>
      <select
        aria-label={`${ariaLabel}: minutes`}
        value={minute}
        onChange={(e) => onChange(join(hour12, Number(e.target.value), pm))}
      >
        {minutes.map((m) => (
          <option key={m} value={m}>
            {pad(m)}
          </option>
        ))}
      </select>
      <select
        aria-label={`${ariaLabel}: AM or PM`}
        value={pm ? "PM" : "AM"}
        onChange={(e) => onChange(join(hour12, minute, e.target.value === "PM"))}
      >
        <option value="AM">AM</option>
        <option value="PM">PM</option>
      </select>
    </span>
  );
}
