# Parent Voice Chatbot — Design

Date: 2026-11-22 · Project: CareCircle (wisperflowdemo / codebenders)

## Intent and why

When an elderly parent signs in, they land on a friendly voice companion instead of a menu. In their own
language it greets them, asks how they feel, checks today's medicines, and reminds them about appointments.
The family wants to know how their parent is doing and whether medicines were taken **without calling every
day**. Every check-in is noted and shared with the whole family circle.

Success: a parent can complete a daily check-in by voice alone, in their language, and every family member
receives an accurate note of how they are and which medicines were taken.

## Who uses it

- **Parent** (role `Parent` in the family, linked to a care profile via `care_profiles.linked_user_id`). Signs in
  through the parent invite link (`/parent/accept-invite`) or the email code.
- **Family members** (every active member of that family: Family manager, Caregivers, Viewers, Hospital staff,
  custom roles) receive the notes.

## The conversation (agreed behaviour)

Turn-based, tap-to-talk. One "check-in" = one conversation, run step by step by the backend:

1. **Greeting by time of day** using the parent's greeting name: "Good morning, Amma!"
   (morning before 12:00, afternoon 12:00–17:00, evening after 17:00, in the care profile's time zone).
2. **Health question:** "How are you feeling today?" The parent answers freely.
   - The answer is **noted** (stored as a health note) and **sent to every family member** (see Notifications).
   - **Worrying answers** (fell, chest pain, can't breathe, dizzy, "help", etc.) are flagged **urgent**
     *(decided by the user)*:
     - The bot must **never** claim that help or a call is on its way: nothing places calls in this version.
       It says it has alerted named family members right now, e.g. "I've alerted Meera and Rahul right now."
     - It shows a large **Call** button with the caregiver's phone number from the onboarding profile
       (`caregiver_phone`, falling back to the parent's `doctor_contact_number` if no caregiver phone exists).
     - The family gets an immediate urgent alert marked **"Needs attention now"** (in-app + email).
     - The check-in then **continues** to the medicine questions.
3. **Medicine check:** using the dose log and reminder times, the bot lists the medicines **due so far today and
   not yet taken**: "You have 2 medicines this morning: Amlodipine 5 mg and Metformin 500 mg. Did you take them?"
   - Understands answers like "yes", "I took the BP one but not the sugar one", "not yet", "remind me later",
     "tablets are finished".
   - Records each answer in the **dose log** (taken / not taken / skipped). "Finished" alerts the family
     immediately (out of stock).
   - **"Remind me later"** (5–30 min, matching existing `ALLOWED_DELAY_MINUTES`) *(decided by the user)*:
     the reminder is stored on the dose. If the chat page is still open when it is due, the bot asks again on its
     own; otherwise it asks the next time the parent opens the app. If the dose is **still not taken about an hour
     after it was due**, the family gets a "medicine not taken" note.
   - Medicines already logged as taken today are not asked about again.
4. **Appointments:** if there is an appointment **today or tomorrow** (status scheduled/rescheduled) it reminds
   them: "Tomorrow at 10:00 AM you have a doctor follow-up with Dr. Rao at City Clinic."
5. **Close:** a short warm goodbye. The full check-in summary is sent to the family.

**One check-in per day** *(decided by the user)*. The health question is asked once a day. If the parent opens
the app or taps to talk again later the same day, the bot continues the same day's check-in from the next
unfinished step (for example newly due medicines in the evening), or answers "anything else?" once everything is
done.

## Goals

- Voice in and out, in the parent's **preferred language** (voice and on-screen text both).
- Reliable, predictable steps: the medicine and appointment checks always happen.
- Every check-in produces a written note to every family member.
- A **dose log** that both the chatbot and the family pages use ("taken / missed today").
- **Reminder times for every medicine**, including ones added by hand.

## Non-goals (this version)

- No free-flowing "phone call" conversation, interruptions or always-on microphone.
- No medical advice, diagnosis or dose changes. The bot never recommends treatment (matches the app's existing
  "CareCircle does not recommend or change treatment" rule).
- No real SMS (still mocked); no push notifications to phones.
- No scheduled/automatic calls to the parent; the parent starts the check-in by opening the app.

## Anti-goals (failure even if it "works")

- The bot skips the medicine question, invents medicines, or logs a dose the parent didn't confirm.
- Health notes reach only some family members, or reach people outside the family.
- The ElevenLabs or Gemini API keys reach the browser.
- The parent is stuck: confusing screens, small text, or the bot not understanding and looping.

## Approaches considered

| | A. ElevenLabs Conversational AI agent | **B. Backend runs the conversation; ElevenLabs = ears + voice (chosen)** |
|---|---|---|
| How | Live call; ElevenLabs' AI decides what to say, calls our backend for facts | Parent taps & speaks → ElevenLabs speech-to-text → our backend decides the next step (Gemini to understand free answers, offline rules as fallback) → ElevenLabs text-to-speech |
| Strength | Most natural, fastest, interruptible | Always follows the script; dose log & notes exactly as designed; health data and logic stay in our backend; keys stay on the server; testable |
| Trade-off | Health talk passes through a third-party AI; may skip steps; per-minute cost; hard to test | Turn-based (tap → speak → short wait) |

Dropped: browser built-in speech recognition (weak for Tamil and older voices, Chrome-only).
**Chosen: B** (by the user). It can move to A later once the steps are proven.

## How it works (decided)

### Voice pipeline
- Browser records a short clip after the parent taps the big mic button (tap again or silence ends it) and
  uploads it to the backend.
- Backend: **ElevenLabs Speech-to-Text** (language hint = parent's language) → text.
- Backend conversation engine decides the reply text (see below).
- Backend: **ElevenLabs Text-to-Speech** in the parent's language and a chosen voice → audio returned to the browser,
  which plays it and shows the text as chat bubbles.
- API keys live only in backend settings (`ELEVENLABS_API_KEY`, `GEMINI_API_KEY`). The existing stub classes in
  `backend/app/services/adapters/speech.py` get real implementations.
- **Fallback:** if ElevenLabs is unavailable, the parent can type, and replies show as text (no audio).

### Conversation engine (backend)
- A step machine per check-in: `greet → health → medicines → appointments → done`.
- Understanding free answers: **Gemini** when `INTENT_MODE` is online, otherwise the existing **offline rules**
  (`adapters/intent.py`: CONFIRM_TAKEN, NOT_TAKEN_YET, REMIND_LATER, MEDICINE_UNAVAILABLE, NEED_HELP, CANCEL).
  For multi-medicine answers ("the BP one but not the sugar one") Gemini maps phrases to the due medicines; with
  offline rules, ambiguous answers lead the bot to ask about each medicine one by one.
- All facts (medicines due, appointments) come from the database, never from the AI.
- Replies are built from fixed, translated templates per language; Gemini only understands, it does not write
  medical content.

### Language
- The parent's preferred language drives speech recognition, the spoken voice and the on-screen text.
- *(Builder's call, approved with the design)* The **care profile** language is the one the chatbot uses. Its
  allowed values are widened from en/ta/hi to **en, ta, hi, te, ml, kn** (migration), and the mapping from the
  onboarding profile's language names (`careProfileSetup.ts` and the onboarding save) is fixed so Telugu,
  Malayalam and Kannada no longer fall back to English.
- Supported for voice: English, Tamil, Hindi, Telugu, Malayalam, Kannada (the onboarding list). Offline rules
  cover English/Tamil/Hindi only; the other three rely on Gemini for understanding.

### New data
- **Dose log** (`medicine_doses`): medicine, scheduled date + time slot, status (`taken`, `not_taken`, `skipped`,
  `missed`), when recorded, recorded by (parent via chatbot, or a family member), source (`chatbot`/`manual`).
  One row per medicine per scheduled time per day.
- **Reminder times for every medicine:** reuse the existing `medicine_reminders` table (`time_of_day` "HH:MM",
  `active`). The Add/Edit medicine form gets a "Reminder times" editor (like the scan review's time chips).
  Medicines with no times are treated as **once a day** (asked once per day, any time).
- **Health check-ins / notes** (`health_checkins`): parent, care profile, started/finished time, the parent's
  health answer (text), urgency flag, the step reached, and a short summary (medicines taken/not taken,
  appointment reminded).
- **Chat messages** for the check-in (who said what, language, timestamps) so the parent's screen can show the
  conversation and the family can read the transcript.

### Notifications to the family *(frequency decided by the user)*
- Recipients: **every active member of the family** (all roles), using the existing `notify()` service.
- **In-app notifications** for each check-in update.
- **One email summary per day** per member (the day's health answer, medicines taken / not taken, appointments
  reminded).
- **Immediate** in-app + email alerts for: urgent answers ("Needs attention now"), tablets finished, and a dose
  still not taken about an hour after it was due.
- SMS stays mocked.
- The note contains: time, the parent's health answer, medicines taken / not taken, appointment reminded, and an
  urgent banner when flagged.
- Each check-in also writes an activity log entry so it appears in the family timeline.

### Screens
- **Parent chat page** (new landing page for parents, e.g. `/parent/chat`): large text, one huge mic button,
  chat bubbles, the bot's reply read aloud automatically, a "type instead" option, and an always-visible
  **Help** button. Mobile-first (parents use phones).
- **Parent sign-in routing:** users with the Parent role go to the chat page after sign-in (invite link and email
  code). Today the email-code login sends everyone to the caregiver onboarding wizard; parents must be routed to
  the chat instead.
- **Family side:** medicine pages **show** today's dose status from the dose log ("Taken 8:10 AM", "Not taken");
  the check-in notes appear in notifications and the timeline. *(Builder's call)* Marking doses by hand from the
  family pages is **out of scope** for this version (display only).
- *(Builder's call)* The chat page **replaces** the existing parent pages: `/parent/home`, `/parent/checkin` and
  `/parent/confirmation` redirect to the chat, and Help becomes a button inside the chat (the Call button and
  recent alerts). `ParentAcceptInvite` sends parents to the chat.

## Constraints

- Builds on the existing stack: React + TypeScript frontend, FastAPI + SQLAlchemy backend, Alembic migrations,
  SQLite now / PostgreSQL later (no SQLite-only or Postgres-only features).
- Permissions use the existing role system: the parent role currently has `parent_profile.view` and
  `voice.use_parent_mode`; new endpoints check `voice.use_parent_mode` for the parent and existing permissions
  for family views.
- **Who builds what** *(decided by the user)*: the backend (tables, migrations, endpoints, ElevenLabs and Gemini
  integration, tests) **and** the frontend are built in **wisperflowdemo**. The team then copies the backend into
  codebenders, which stays read-only from this side. Migrations must work on SQLite now and PostgreSQL later.
- Elderly users: large tap targets, high contrast, short sentences, no time pressure.

## Left to the builder

- Exact endpoint paths, schemas and table/column names.
- Audio format and recording details (e.g. WebM/Opus), clip length limits, silence detection.
- ElevenLabs model and voice choice per language; caching of repeated phrases (greetings).
- Wording of the reply templates in each language (keep them short and warm).
- Exact urgent-keyword list and the Gemini prompt for understanding answers.
- How "missed" doses are marked (e.g. end-of-day job vs computed on read).
- Visual design of the chat page within the existing CareCircle style.
