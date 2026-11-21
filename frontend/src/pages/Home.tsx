import { useState } from "react";
import "../landing.css";
import { Link } from "react-router-dom";

// Public product landing page. Sign-up / log-in lives at /start.

const PROBLEMS = [
  { icon: "📞", text: "Calling every day just to ask “Did you take your tablets?”" },
  { icon: "🧾", text: "Prescriptions, reports and doctor numbers scattered across chats and paper." },
  { icon: "🤷", text: "Siblings and caretakers unsure who is handling what." },
  { icon: "📱", text: "Apps that are too small, too fiddly and English-only for elderly parents." },
];

const STEPS = [
  {
    n: "1",
    title: "Set up the circle",
    body: "Sign up with your email, choose your role, and fill in your parent's care profile in a short guided wizard. Invite siblings, caretakers or hospital staff.",
  },
  {
    n: "2",
    title: "Parent checks in by voice",
    body: "At medicine time your parent opens a big, simple screen and just speaks, in English, Tamil or Hindi. The reply is read back aloud.",
  },
  {
    n: "3",
    title: "CareCircle understands",
    body: "Speech is turned into text and matched to what your parent meant: taken, not yet, remind me later, medicine finished, or I need help.",
  },
  {
    n: "4",
    title: "Family acts together",
    body: "The update lands on the shared dashboard and activity log. The right people are notified, and follow-ups become tasks with an owner.",
  },
];

const INTENTS = [
  { say: "“I took it” · “சாப்பிட்டேன்” · “ले लिया”", means: "Dose confirmed", icon: "✅" },
  { say: "“Remind me in 15 minutes”", means: "Reminder snoozed for 5–30 min", icon: "⏰" },
  { say: "“Not yet” · “இன்னும்” · “अभी नहीं”", means: "Marked as not taken yet", icon: "⏳" },
  { say: "“My tablets are finished”", means: "Medicine unavailable, family alerted", icon: "📦" },
  { say: "“Help” · “உதவி” · “मदद”", means: "Help request sent to family", icon: "🆘" },
  { say: "“Cancel” · “Never mind”", means: "Check-in cancelled, nothing recorded", icon: "↩️" },
];

const FAMILY_FEATURES = [
  { icon: "📊", title: "Family dashboard", body: "Today's medicines, open tasks, recent check-ins and alerts for your parent on one screen." },
  { icon: "🧓", title: "Care profile", body: "Name they like to be greeted by, preferred language and time zone, health conditions, allergies and care instructions." },
  { icon: "💊", title: "Medicine management", body: "Each medicine with instructions, tablets remaining, refill date and the family member responsible for it." },
  { icon: "✅", title: "Family tasks", body: "Create, assign and complete tasks with due dates and priority. Assignees are notified automatically." },
  { icon: "📅", title: "Appointments", soon: true, body: "Keep track of doctor visits and check-ups for your parent." },
  { icon: "📁", title: "Shared records", soon: true, body: "Prescriptions and medical reports in one place, viewable or uploadable by permission." },
  { icon: "🎙️", title: "Care & voice activity", body: "Every spoken check-in and every change, logged with who did it and when." },
  { icon: "🕒", title: "Family timeline", soon: true, body: "One running story of everything happening in your parent's care." },
  { icon: "🔔", title: "Notifications", body: "In-app alerts plus email and SMS. Each member chooses what they want to hear about." },
];

const PARENT_SCREENS = [
  { title: "Home", body: "A warm greeting by name and today's medicines in large, clear text." },
  { title: "Voice check-in", body: "One big microphone button. Tap, speak, done." },
  { title: "Confirmation", body: "A clear on-screen and spoken reply, so your parent knows it was recorded." },
  { title: "Help", body: "A dedicated help screen when something does not feel right." },
];

const PROFILE_FIELDS = [
  "Full name & preferred name",
  "Relationship to you",
  "Date of birth or approximate age",
  "Profile photo",
  "Preferred language & mobile number",
  "Known health conditions",
  "Allergies",
  "Primary doctor & contact number",
  "Preferred hospital",
  "Care instructions",
  "Caregiver name, relationship, phone & email",
];

const ROLES = [
  {
    name: "Family manager",
    who: "Usually the child who sets up the circle",
    can: "Everything: profile, medicines, reports, tasks, members, roles and notifications.",
  },
  {
    name: "Caregiver",
    who: "A sibling, nurse or home caretaker",
    can: "View the dashboard and profile, update medicine stock, upload reports, create and assign tasks, view activity.",
  },
  {
    name: "Viewer",
    who: "Extended family who want to stay informed",
    can: "Read-only access to the dashboard, profile, medicines, reports, tasks and activity.",
  },
  {
    name: "Parent",
    who: "Your mother or father",
    can: "A simple voice-first parent mode and their own profile, nothing to manage.",
  },
];

const SIGNUP_ROLES = ["Parent", "Caretaker", "Hospital staff", "Child of a parent", "Others"];

const FAQ = [
  {
    q: "Does my parent need to type or remember a password?",
    a: "No. Sign-in is passwordless with a 6-digit code sent to email, and once in, your parent only needs to tap and speak.",
  },
  {
    q: "Which languages are supported?",
    a: "English, Tamil (தமிழ்) and Hindi (हिन्दी), for both understanding what your parent says and reading replies aloud.",
  },
  {
    q: "What happens if the internet is slow or down?",
    a: "Check-ins are understood with built-in offline rules that recognise common phrases in all three languages. An admin switch lets you choose between offline rules and the AI mode powered by Google Gemini.",
  },
  {
    q: "Who can see my parent's health information?",
    a: "Only members you invite to your family circle, and only what their role allows. You can use the built-in roles or create custom roles from 17 fine-grained permissions.",
  },
  {
    q: "How are family members notified?",
    a: "Through in-app notifications and email. SMS is built in behind an adapter and runs in demo mode in this release.",
  },
  {
    q: "Can I manage more than one parent?",
    a: "Yes. A family circle can hold more than one care profile, and every medicine and task is linked to the right profile.",
  },
];

const STACK = [
  { name: "React + TypeScript", role: "Web app for families and parents" },
  { name: "FastAPI", role: "Secure Python backend API" },
  { name: "PostgreSQL", role: "Reliable data storage with migrations" },
  { name: "ElevenLabs", role: "Speech-to-text and natural text-to-speech" },
  { name: "Google Gemini", role: "AI understanding of check-ins" },
  { name: "Offline rules", role: "Keyword engine for EN / TA / HI fallback" },
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
            <a href="#voice">Voice check-ins</a>
            <a href="#features">Features</a>
            <a href="#roles">Roles & privacy</a>
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
                CareCircle lets an elderly parent check in on their medicines just by speaking, in
                English, Tamil or Hindi, while the whole family shares one place for the care
                profile, medicines, tasks and alerts, with appointments and shared records on the way.
              </p>
              <div className="lp-cta-row">
                <Link to="/start" className="lp-btn">
                  Create your family circle
                </Link>
                <a href="#how" className="lp-btn lp-btn-ghost">
                  See how it works
                </a>
              </div>
              <ul className="lp-hero-ticks">
                <li>No passwords: sign in with an email code</li>
                <li>Works offline for check-ins</li>
                <li>Role-based family access</li>
              </ul>
            </div>

            <div className="lp-phone" aria-label="Example voice check-in">
              <div className="lp-phone-screen">
                <p className="lp-phone-greet">Good morning, Amma 🌼</p>
                <p className="lp-phone-due">8:30 AM · Amlodipine 5 mg</p>
                <span className="lp-mic" aria-hidden="true">
                  🎙️
                </span>
                <p className="lp-phone-hint">Tap and speak</p>
                <div className="lp-bubble lp-bubble-user">“நான் மாத்திரை சாப்பிட்டேன்.”</div>
                <div className="lp-bubble lp-bubble-app">
                  ✓ Amlodipine marked as taken. Your family has been updated. 🔊
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

        {/* Voice check-ins */}
        <section id="voice" className="lp-section">
          <div className="lp-wrap">
            <h2 className="lp-h2">Just say it. CareCircle understands.</h2>
            <p className="lp-sub">
              Your parent doesn't need to learn commands. CareCircle recognises six everyday responses
              at medicine time, in any of the three languages.
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

        {/* Two experiences */}
        <section className="lp-section lp-section-tint">
          <div className="lp-wrap">
            <h2 className="lp-h2">Two experiences, one circle</h2>
            <p className="lp-sub">
              A calm, phone-sized parent mode, and a full desktop dashboard for the family.
            </p>
            <div className="lp-two">
              <div className="lp-card lp-audience">
                <p className="lp-eyebrow">Parent mode</p>
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
                  <li><strong>Know without calling</strong>: see whether today's doses were taken.</li>
                  <li><strong>Never run out</strong>: track tablets remaining and refill dates.</li>
                  <li><strong>Share the load</strong>: assign tasks with due dates and priority.</li>
                  <li><strong>Stay informed</strong>: activity log, timeline and alerts.</li>
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
                needs to know, saved as you go.
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
                <strong>17 permissions</strong>
                <span>Fine-grained control for custom roles</span>
              </div>
              <div>
                <strong>Passwordless</strong>
                <span>Secure 6-digit email codes</span>
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
                like a conversation. Each parent's preferred language and time zone are saved in
                their profile.
              </p>
              <p className="lp-sub lp-left">
                Choose between <strong>AI mode</strong> (Google Gemini) and <strong>offline rules</strong>,
                which understand common phrases without the cloud, with one admin switch.
              </p>
            </div>
            <div className="lp-langs">
              <div className="lp-card lp-lang">
                <span className="lp-lang-name">English</span>“I took my sugar tablet.”
              </div>
              <div className="lp-card lp-lang">
                <span className="lp-lang-name">தமிழ்</span>“நான் சர்க்கரை மாத்திரை சாப்பிட்டேன்.”
              </div>
              <div className="lp-card lp-lang">
                <span className="lp-lang-name">हिन्दी</span>“मैंने शुगर की दवा ले ली।”
              </div>
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
          <span>Voice-first family care · English · தமிழ் · हिन्दी</span>
          <span>© {new Date().getFullYear()} CareCircle</span>
        </div>
      </footer>
    </div>
  );
}
