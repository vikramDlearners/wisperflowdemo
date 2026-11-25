// Turns a dictated email ("Meera dot Rao at gmail dot com.") into an address.
// Returns null when the result is not an email.
export function spokenEmail(heard: string): string | null {
  const words = heard.toLowerCase().replace(/[\s,]+/g, " ").trim().replace(/[.!?]+$/, "");
  let s = ` ${words} `.replace(/^ (?:my )?(?:email|e-mail|mail)(?: address| id)? is:? /, " ");
  if (!s.includes("@")) s = s.replace(/ at (?:the )?rate(?: of)? | at /, " @ ");
  s = s
    .replace(/ (?:dot|period|point)(?= )/g, ".")
    .replace(/ underscore(?= )/g, "_")
    .replace(/ (?:dash|hyphen|minus)(?= )/g, "-")
    .replace(/ plus(?= )/g, "+")
    .replace(/\s+/g, "");
  return /^[^\s@]+@[^\s@]+\.[^\s@.]+$/.test(s) ? s : null;
}
