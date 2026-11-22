import { useState } from "react";
import "../landing.css";
import { Link } from "react-router-dom";

// Public product landing page. Sign-up / log-in lives at /start.

const LANGUAGES = "English, Tamil, Hindi, Telugu, Malayalam or Kannada";

const PROBLEMS = [
  { icon: "📞", text: "Calling every day just to ask “Did you take your tablets? What did you eat?”" },
  { icon: "🧾", text: "Prescriptions, reports and doctor numbers scattered across chats and paper." },
  { icon: "🤷", text: "Siblings and caretakers unsure who is handling what." },
  { icon: "📱", text: "Apps that are too small, too fiddly and English-only for elderly parents." },
];

const STEPS = [
  {
    n: "1",
    title: "Set up the circle",
    body: "Sign up with your email, fill in your parent's care profile, add their medicines (or scan the prescription) and invite siblings and caretakers.",
  },
  {
    n: "2",
    title: "Parent chats by voice",
    body: `Your parent opens a big, simple chat and just talks, in ${LANGUAGES}. CareCircle greets them, asks how they are, and reads every reply aloud.`,
  },
  {
    n: "3",
    title: "CareCircle keeps track",
    body: "Health notes, medicines taken (with the time), meals and upcoming appointments are saved as the conversation goes.",
  },
  {
    n: "4",
    title: "Family stays in the loop",
    body: "AI summarises each conversation, important points become tasks for caretakers and managers, and alerts reach the family when something needs attention.",
  },
];

const DAILY_CHAT = [
  {
    icon: "🌼",
    title: "A warm greeting",
    body: "Good morning, afternoon or evening, by the name your parent likes, then “How are you feeling today?” The answer is shared with the family.",
  },
  {
    icon: "💊",
    title: "Medicines, the right dose",
    body: "“You have 2 medicines now. Did you take them?” A plain “I took my medicine” gets “How many?” first, and only the current dose is marked, with the time.",
  },
  {
    icon: "🍛",
    title: "Meals",
    body: "Breakfast in the morning, lunch in the afternoon, dinner at night. Missed earlier? It asks about the whole day and saves the answer.",
  },
  {
    icon: "📅",
    title: "Appointment reminders",
    body: "Doctor visits today or tomorrow are mentioned once, with the time and the doctor's name.",
  },
  {
    icon: "💛",
    title: "Gentle care notes",
    body: "Before goodbye, a soft note from the family: drink enough water, go easy on sweets, stay away from a known allergy.",
  },
  {
    icon: "📷",
    title: "Ask anything about medicines",
    body: "“What do I take tonight?” gets today's schedule, with a photo of each medicine so it's easy to pick the right one.",
  },
];

const INTENTS = [
  { say: "“I took it” · “சாப்பிட்டேன்” · “ले लिया”", means: "Current dose marked as taken, with the time", icon: "✅" },
  { say: "“I took one” · “Only Metformin”", means: "Asks which one, records only that dose", icon: "🔢" },
  { say: "“Remind me in 15 minutes”", means: "Reminder snoozed for 5–30 min", icon: "⏰" },
  { say: "“Not yet” · “இன்னும் இல்லை” · “अभी नहीं”", means: "Marked as not taken yet, asked again later", icon: "⏳" },
  { say: "“My tablets have run out”", means: "Family alerted to arrange a refill", icon: "📦" },
  { say: "“What do I take tonight?”", means: "Today's schedule, with medicine photos", icon: "🗓️" },
  { say: "“I fell” · “உதவி” · “मदद”", means: "Family alerted at once, Call button shown", icon: "🆘" },
  { say: "“Idli and coffee”", means: "Saved as today's breakfast", icon: "🍛" },
  { say: "“Thank you, bye”", means: "A warm goodbye, nothing shared", icon: "👋" },
];

const EMERGENCY_STEPS = [
  { n: "1", title: "Tap Help", body: "One big button, always at the top of your parent's chat." },
  { n: "2", title: "“Is this an emergency?”", body: "Two clear choices: yes, or I just need help." },
  { n: "3", title: "Family alerted", body: "Every family member gets an urgent in-app alert and an email straight away." },
  { n: "4", title: "Tap to call", body: "A large call button with the emergency number, ready to dial." },
];

const FAMILY_FEATURES = [
  { icon: "📊", title: "Family dashboard", body: "Today's medicines, open tasks, the next appointment and alerts for each parent on one screen." },
  { icon: "🧠", title: "AI conversation summaries", body: "Google Gemini summarises every finished chat into a few plain sentences, saved for the family." },
  { icon: "✅", title: "Tasks from conversations", body: "Anything important your parent says becomes a task for the caretakers and managers, who are notified." },
  { icon: "💊", title: "Medicine management", body: "Instructions, photos, tablets left, refill dates, reminder times and today's status: ✓ Taken at 8:32 AM, Missed, Not taken." },
  { icon: "🧾", title: "Prescription scan", body: "Snap a prescription and the medicines, doses and timings are read and added for you." },
  { icon: "📅", title: "Appointments", body: "Doctor visits with time, doctor and place; your parent is reminded the day before and on the day." },
  { icon: "⏰", title: "Missed-dose alerts", body: "If a timed dose isn't confirmed an hour after it's due, the family is told." },
  { icon: "📬", title: "Daily summary email", body: "Every evening: how your parent felt, medicines taken or missed, meals and appointments." },
  { icon: "🔔", title: "Notifications", body: "In-app alerts and email for check-ins, urgent messages, medicines and tasks." },
  { icon: "🕒", title: "Family timeline", soon: true, body: "One running story of everything happening in your parent's care." },
];

const PARENT_SCREENS = [
  { title: "Fresh chat every time", body: "Each time it opens: a new greeting and only what's still open today." },
  { title: "Voice or typing", body: "One big microphone button, or type if that's easier. Replies are read aloud." },
  { title: "Medicine photos", body: "A picture appears whenever a medicine is mentioned. Tap to see it large." },
  { title: "Help", body: "Asks if it's an emergency, alerts the family and shows a number to call." },
];

const PROFILE_FIELDS = [
  "Full name & the name they like to be greeted by",
  "Relationship to you",
  "Date of birth or approximate age",
  "Profile photo",
  "Preferred language & mobile number",
  "Known health conditions & allergies",
  "Health deficiencies (sugar, BP, calcium…)",
  "Notes such as daily water or foods to avoid",
  "Primary doctor & contact number",
  "Preferred hospital & care instructions",
  "Caregiver name, relationship, phone & email",
];

const ROLES = [
  {
    name: "Family manager",
    who: "Usually the child who sets up the circle",
    can: "Everything: profiles, medicines, appointments, tasks, members, roles and notifications. Gets tasks from conversations.",
  },
  {
    name: "Caregiver",
    who: "A sibling, nurse or home caretaker",
    can: "View the dashboard and profile, update medicines, manage members and tasks, view activity. Gets tasks from conversations.",
  },
  {
    name: "Viewer",
    who: "Extended family who want to stay informed",
    can: "Read-only access to the dashboard, profile, medicines, tasks and activity.",
  },
  {
    name: "Parent",
    who: "Your mother or father",
    can: "A simple voice-first chat in their own language, a Help button, and their own profile.",
  },
];

const SIGNUP_ROLES = ["Parent", "Caretaker", "Hospital staff", "Manager", "Others"];

const LANGUAGE_EXAMPLES = [
  { name: "English", text: "“I took my sugar tablet.”" },
  { name: "தமிழ்", text: "“நான் சர்க்கரை மாத்திரை சாப்பிட்டேன்.”" },
  { name: "हिन्दी", text: "“मैंने शुगर की दवा ले ली।”" },
  { name: "తెలుగు", text: "“నేను షుగర్ మాత్ర వేసుకున్నాను.”" },
  { name: "മലയാളം", text: "“ഞാൻ ഷുഗറിന്റെ ഗുളിക കഴിച്ചു.”" },
  { name: "ಕನ್ನಡ", text: "“ನಾನು ಶುಗರ್ ಮಾತ್ರೆ ತೆಗೆದುಕೊಂಡೆ.”" },
];

const FAQ = [
  {
    q: "Does my parent need to type or remember a password?",
    a: "No. Sign-in is passwordless with a 6-digit code, and once in, your parent only needs to tap and speak.",
  },
  {
    q: "Which languages are supported?",
    a: `${LANGUAGES}, for understanding what your parent says, for every reply and for the buttons on screen. Change the language on the parent's profile and the very next reply switches.`,
  },
  {
    q: "What happens in an emergency?",
    a: "Your parent taps Help and confirms it's an emergency. Every family member gets an urgent in-app alert and an email at once, and your parent sees a large button to call the emergency number. Words like “I fell” or “help” in the chat alert the family too.",
  },
  {
    q: "What does the family see after a conversation?",
    a: "A short AI summary of the chat, tasks for the caretakers and managers for anything important, today's medicine status with times, and an evening summary email with health, medicines, meals and appointments.",
  },
  {
    q: "What if a medicine has no fixed time?",
    a: "It's counted by part of the day: morning, afternoon and night. Saying “I took it” in the evening marks only the night dose.",
  },
  {
    q: "What happens if the internet is slow or down?",
    a: "Answers are understood with built-in offline rules in all six languages, and a simple summary is saved if the AI isn't available. An admin switch chooses between offline rules and the AI mode powered by Google Gemini.",
  },
  {
    q: "Who can see my parent's health information?",
    a: "Only members you invite to your family circle, and only what their role allows. Use the built-in roles or create custom roles from fine-grained permissions.",
  },
  {
    q: "How are family members notified?",
    a: "Through in-app notifications and email today. WhatsApp and SMS alerts are on the way.",
  },
  {
    q: "Can I manage more than one parent?",
    a: "Yes. A family circle can hold several parents, each with their own profile, language, medicines and chat.",
  },
];

const STACK = [
  { name: "React + TypeScript", role: "Web app for families and parents" },
  { name: "FastAPI", role: "Secure Python backend API" },
  { name: "PostgreSQL", role: "Reliable data storage with migrations" },
  { name: "ElevenLabs", role: "Speech-to-text and natural text-to-speech" },
  { name: "Google Gemini", role: "Understanding answers, prescriptions and chat summaries" },
  { name: "Offline rules", role: "Keyword engine in six Indian languages" },
];

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`lp-faq-item${open ? " is-open" : ""}`}>
      <button type="button" className="lp-faq-q" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span>{q}</span>
        <span className="lp-faq-sign" aria-hidden="true">
          {open ? "−" : "+"}
        </span>
      </button>
      {open && <p className="lp-faq-a">{a}</p>}
    </div>
  );
}

export default function Home() {
  return (
    <div className="lp">
      <header className="lp-nav">
        <div className="lp-wrap lp-nav-inner">
          <a href="#top" className="lp-logo">
            <span className="lp-logo-mark" aria-hidden="true">◎</span> CareCircle
          </a>
          <nav className="lp-nav-links" aria-label="Main">
            <a href="#how">How it works</a>
            <a href="#chat">Daily check-in</a>
            <a href="#safety">Emergency help</a>
            <a href="#features">Features</a>
            <a href="#faq">FAQ</a>
          </nav>
          <div className="lp-nav-cta">
            <Link to="/start" className="lp-link">
              Log in
            </Link>
            <Link to="/start" className="lp-btn lp-btn-sm">
              Get started
            </Link>
          </div>
        </div>
      </header>

      <main id="top">
        {/* Hero */}
        <section className="lp-hero">
          <div className="lp-wrap lp-hero-grid">
            <div>
              <p className="lp-eyebrow">Voice-first family care app</p>
              <h1 className="lp-h1">
                Care for your parents <span className="lp-accent">together</span>, even from afar.
              </h1>
              <p className="lp-lead">
                Every day CareCircle chats with your parent by voice, in {LANGUAGES}: how they feel,
                their medicines, their meals and their appointments. The whole family sees what matters,
                gets tasks for what needs doing, and is alerted the moment help is needed.
              </p>
              <div className="lp-cta-row">
                <Link to="/start" className="lp-btn">
                  Create your family circle
                </Link>
                <a href="#chat" className="lp-btn lp-btn-ghost">
                  See the daily check-in
                </a>
              </div>
              <ul className="lp-hero-ticks">
                <li>Six Indian languages</li>
                <li>One-tap emergency help</li>
                <li>AI summaries and tasks for the family</li>
              </ul>
            </div>

            <div className="lp-phone" aria-label="Example voice check-in">
              <div className="lp-phone-screen">
                <p className="lp-phone-greet">Good morning, Amma 🌼</p>
                <p className="lp-phone-due">You have 2 medicines now</p>
                <span className="lp-mic" aria-hidden="true">
                  🎙️
                </span>
                <p className="lp-phone-hint">Tap and speak</p>
                <div className="lp-bubble lp-bubble-user">“நான் மாத்திரை சாப்பிட்டேன்.”</div>
                <div className="lp-bubble lp-bubble-app">How many of your 2 medicines did you take? 🔊</div>
                <div className="lp-bubble lp-bubble-user">“இரண்டும்.”</div>
                <div className="lp-bubble lp-bubble-app">
                  ✓ Noted: you took both at 8:32 AM. What did you have for breakfast? 🔊
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Problem */}
        <section className="lp-section">
          <div className="lp-wrap">
            <h2 className="lp-h2">Caring from a distance is hard</h2>
            <p className="lp-sub">
              Many families live in different cities from their ageing parents. Keeping track of
              their health shouldn't depend on endless phone calls.
            </p>
            <div className="lp-problems">
              {PROBLEMS.map((p) => (
                <div key={p.text} className="lp-card lp-problem">
                  <span aria-hidden="true">{p.icon}</span>
                  <p>{p.text}</p>
                </div>
              ))}
            </div>
            <p className="lp-solution">
              <strong>CareCircle</strong> brings parents, children, caretakers and hospital staff into
              one circle, and lets the parent take part just by talking.
            </p>
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="lp-section lp-section-tint">
          <div className="lp-wrap">
            <h2 className="lp-h2">How it works</h2>
            <p className="lp-sub">From setup to a daily rhythm in four simple steps.</p>
            <ol className="lp-steps">
              {STEPS.map((s) => (
                <li key={s.n} className="lp-card lp-step">
                  <span className="lp-step-n">{s.n}</span>
                  <h3>{s.title}</h3>
                  <p>{s.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* Daily check-in chat */}
        <section id="chat" className="lp-section">
          <div className="lp-wrap">
            <h2 className="lp-h2">A daily check-in that feels like a chat</h2>
            <p className="lp-sub">
              A short, kind conversation that adapts to the time of day and remembers what's already
              been answered, so nothing is asked twice.
            </p>
            <div className="lp-features">
              {DAILY_CHAT.map((f) => (
                <div key={f.title} className="lp-card lp-feature">
                  <span className="lp-feature-icon" aria-hidden="true">
                    {f.icon}
                  </span>
                  <h3>{f.title}</h3>
                  <p>{f.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Voice understanding */}
        <section id="voice" className="lp-section lp-section-tint">
          <div className="lp-wrap">
            <h2 className="lp-h2">Just say it. CareCircle understands.</h2>
            <p className="lp-sub">
              Your parent doesn't need to learn commands. Everyday answers are understood in any of the
              six languages.
            </p>
            <div className="lp-intents">
              {INTENTS.map((i) => (
                <div key={i.means} className="lp-card lp-intent">
                  <span className="lp-intent-icon" aria-hidden="true">
                    {i.icon}
                  </span>
                  <div>
                    <p className="lp-intent-say">{i.say}</p>
                    <p className="lp-intent-means">{i.means}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Emergency help */}
        <section id="safety" className="lp-section">
          <div className="lp-wrap">
            <h2 className="lp-h2">Help, one tap away</h2>
            <p className="lp-sub">
              When something feels wrong, your parent doesn't have to find a number or explain anything.
            </p>
            <ol className="lp-steps">
              {EMERGENCY_STEPS.map((s) => (
                <li key={s.n} className="lp-card lp-step">
                  <span className="lp-step-n">{s.n}</span>
                  <h3>{s.title}</h3>
                  <p>{s.body}</p>
                </li>
              ))}
            </ol>
            <p className="lp-solution">
              Words like <strong>“I fell”</strong> or <strong>“help”</strong> anywhere in the chat alert the
              family too, and a red <strong>Call family</strong> button appears on screen.
            </p>
          </div>
        </section>

        {/* Two experiences */}
        <section className="lp-section lp-section-tint">
          <div className="lp-wrap">
            <h2 className="lp-h2">Two experiences, one circle</h2>
            <p className="lp-sub">
              A calm, phone-sized parent chat, and a full dashboard for the family.
            </p>
            <div className="lp-two">
              <div className="lp-card lp-audience">
                <p className="lp-eyebrow">Parent chat</p>
                <h3>Big, simple, spoken</h3>
                <p className="muted">Large text, large buttons, and nothing to configure.</p>
                <ul className="lp-screen-list">
                  {PARENT_SCREENS.map((s) => (
                    <li key={s.title}>
                      <strong>{s.title}</strong>: {s.body}
                    </li>
                  ))}
                </ul>
              </div>
              <div className="lp-card lp-audience">
                <p className="lp-eyebrow">Family dashboard</p>
                <h3>Everything at a glance</h3>
                <p className="muted">For children, caretakers and hospital staff.</p>
                <ul className="lp-screen-list">
                  <li><strong>Know without calling</strong>: each dose taken, with the time, and what they ate.</li>
                  <li><strong>Read the summary</strong>: a few AI-written sentences after every chat.</li>
                  <li><strong>Act on it</strong>: important points arrive as tasks for caretakers and managers.</li>
                  <li><strong>Never run out</strong>: tablets left, refill dates and “ran out” alerts.</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        {/* Features */}
        <section id="features" className="lp-section">
          <div className="lp-wrap">
            <h2 className="lp-h2">Everything the care circle needs</h2>
            <p className="lp-sub">
              One place instead of scattered messages, paper slips and phone calls.
            </p>
            <div className="lp-features">
              {FAMILY_FEATURES.map((f) => (
                <div key={f.title} className="lp-card lp-feature">
                  <span className="lp-feature-icon" aria-hidden="true">
                    {f.icon}
                  </span>
                  <h3>
                    {f.title}
                    {"soon" in f && f.soon && <span className="lp-soon">Coming soon</span>}
                  </h3>
                  <p>{f.body}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Onboarding / profile */}
        <section className="lp-section lp-section-tint">
          <div className="lp-wrap lp-two lp-center-y">
            <div>
              <p className="lp-eyebrow">Guided onboarding</p>
              <h2 className="lp-h2 lp-left">A complete care profile in minutes</h2>
              <p className="lp-sub lp-left">
                A step-by-step wizard captures everything a caregiver, doctor or new family member
                needs to know. The chat uses it too: the greeting name, the language, and gentle
                reminders from the deficiencies and notes you add.
              </p>
              <p className="lp-sub lp-left">At sign-up, everyone picks how they relate to the circle:</p>
              <div className="lp-chips">
                {SIGNUP_ROLES.map((r) => (
                  <span key={r} className="lp-chip">
                    {r}
                  </span>
                ))}
              </div>
            </div>
            <div className="lp-card">
              <h3>What the profile holds</h3>
              <ul className="lp-checklist">
                {PROFILE_FIELDS.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        {/* Roles & privacy */}
        <section id="roles" className="lp-section">
          <div className="lp-wrap">
            <h2 className="lp-h2">Right access for the right people</h2>
            <p className="lp-sub">
              Health information stays inside your circle. Every action is checked against the
              member's role: start with these built-in roles, or create your own.
            </p>
            <div className="lp-roles">
              {ROLES.map((r) => (
                <div key={r.name} className="lp-card lp-role">
                  <h3>{r.name}</h3>
                  <p className="lp-role-who">{r.who}</p>
                  <p>{r.can}</p>
                </div>
              ))}
            </div>
            <div className="lp-trust">
              <div>
                <strong>Custom roles</strong>
                <span>Fine-grained permissions for each member</span>
              </div>
              <div>
                <strong>Passwordless</strong>
                <span>Secure 6-digit sign-in codes</span>
              </div>
              <div>
                <strong>Full audit trail</strong>
                <span>Every change logged with who and when</span>
              </div>
              <div>
                <strong>Invite only</strong>
                <span>Only members you add can see your family</span>
              </div>
            </div>
          </div>
        </section>

        {/* Languages & offline */}
        <section id="languages" className="lp-section lp-section-tint">
          <div className="lp-wrap lp-two lp-center-y">
            <div>
              <p className="lp-eyebrow">Multilingual & resilient</p>
              <h2 className="lp-h2 lp-left">Speaks their language, even offline</h2>
              <p className="lp-sub lp-left">
                Natural speech recognition and lifelike voices from ElevenLabs make check-ins feel
                like a conversation. Each parent's language and time zone are saved in their profile,
                and changing the language switches the chat from the very next reply.
              </p>
              <p className="lp-sub lp-left">
                Choose between <strong>AI mode</strong> (Google Gemini) and <strong>offline rules</strong>,
                which understand common phrases without the cloud, with one admin switch.
              </p>
            </div>
            <div className="lp-langs">
              {LANGUAGE_EXAMPLES.map((l) => (
                <div key={l.name} className="lp-card lp-lang">
                  <span className="lp-lang-name">{l.name}</span>
                  {l.text}
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Tech */}
        <section className="lp-section">
          <div className="lp-wrap">
            <h2 className="lp-h2">Under the hood</h2>
            <p className="lp-sub">Built on a modern, dependable stack.</p>
            <div className="lp-stack">
              {STACK.map((s) => (
                <div key={s.name} className="lp-stack-item">
                  <strong>{s.name}</strong>
                  <span>{s.role}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section id="faq" className="lp-section lp-section-tint">
          <div className="lp-wrap lp-narrow">
            <h2 className="lp-h2">Frequently asked questions</h2>
            <div className="lp-faq">
              {FAQ.map((f) => (
                <FaqItem key={f.q} q={f.q} a={f.a} />
              ))}
            </div>
          </div>
        </section>

        {/* Final CTA */}
        <section className="lp-section">
          <div className="lp-wrap">
            <div className="lp-final">
              <h2>Start your family's care circle today</h2>
              <p>
                Sign up with your email, set up your parent's profile, and invite your family. It
                only takes a few minutes.
              </p>
              <Link to="/start" className="lp-btn lp-btn-light">
                Get started
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <div className="lp-wrap lp-footer-inner">
          <span className="lp-logo">
            <span className="lp-logo-mark" aria-hidden="true">◎</span> CareCircle
          </span>
          <span>Voice-first family care · English · தமிழ் · हिन्दी · తెలుగు · മലയാളം · ಕನ್ನಡ</span>
          <span>© {new Date().getFullYear()} CareCircle</span>
        </div>
      </footer>
    </div>
  );
}
