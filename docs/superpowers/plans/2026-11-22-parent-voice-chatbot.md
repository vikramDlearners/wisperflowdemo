# Parent Voice Chatbot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A parent signs in and lands on a tap-to-talk voice chatbot that greets them, asks about their health,
checks today's medicines against a new dose log, reminds them of appointments today/tomorrow, and shares
everything with the whole family.

**Architecture:** The backend owns the conversation: a per-day check-in step machine
(`greet → health → medicines → appointments → done`) built from fixed, translated reply templates. ElevenLabs
does speech-to-text and text-to-speech only; Gemini (or the existing offline rules) only *understands* answers.
Facts (medicines due, appointments) always come from the database. New tables: medicine dose log, health
check-ins, chat messages. Reminder times reuse `medicine_reminders`.

**Tech Stack:** FastAPI 0.115, SQLAlchemy 2.0, Alembic, pytest (backend, Python 3.11 venv in `backend/.venv`);
React 18 + TypeScript + Vite (frontend). External HTTP via `urllib.request` like `services/prescription_scan.py`.

**Spec:** `docs/superpowers/specs/2026-11-22-parent-voice-chatbot-design.md`

## Global Constraints

- Work only in `D:\Hackathon\wisperflowdemo`. `D:\Hackathon\codebenders` is read-only.
- Migrations must run on SQLite now and PostgreSQL later: no dialect-specific SQL; use `op.batch_alter_table` for column changes (see `alembic/env.py` SQLite handling).
- API keys (`ELEVENLABS_API_KEY`, `GEMINI_API_KEY`) are read only by the backend; never returned to the browser.
- The bot never gives medical advice and never says help or a call is on its way.
- Languages: `en, ta, hi, te, ml, kn` everywhere the parent's language is used.
- Times use the care profile `timezone` (default `Asia/Kolkata`). Greeting: morning < 12:00, afternoon 12:00–17:00, evening ≥ 17:00.
- "Remind me later" delays must be in `ALLOWED_DELAY_MINUTES` = {5, 10, 15, 20, 25, 30} (`services/adapters/intent.py`).
- One health check-in per parent per local day.
- Family notifications go to **every active member** of the family (all roles).
- Commits are local to wisperflowdemo; push only when the user asks.
- Backend tests: `cd backend && .venv\Scripts\python -m pytest -q`. Frontend check: `cd frontend && npx tsc -p . --noEmit`.

## Review Focus

1. A parent with **no linked care profile** (invite accepted before this change) opens the chat → the backend links them to the family's only care profile, or returns a clear 409 "Ask your family to link your profile" when there are several; never a 500. *(Task 4 test.)*
2. A medicine with **no reminder times** → treated as one daily dose (slot `"any"`), asked once, and not asked again after it is logged. *(Task 3 test.)*
3. **Midnight / time zone**: a dose logged at 23:50 local time counts for that day, not the next UTC day. *(Task 3 test.)*
4. **ElevenLabs or Gemini down / not configured** → the turn still completes as text (offline rules), with `audio` null, never a 500. *(Task 8 test.)*
5. **Urgent words in Tamil/Hindi** ("விழுந்துட்டேன்", "मैं गिर गई") → urgent flag set and immediate family alert, check-in continues to medicines. *(Task 6 test.)*

---

### Task 1: Six parent languages on care profiles

**Files:**
- Modify: `backend/app/services/care.py:17` (`ALLOWED_LANGUAGES`)
- Create: `backend/app/services/languages.py`
- Modify: `frontend/src/careProfileSetup.ts` (language map)
- Test: `backend/tests/test_parent_languages.py`

**Interfaces:**
- Produces: `LANGUAGE_CODES: tuple[str, ...] = ("en", "ta", "hi", "te", "ml", "kn")`; `language_code(name_or_code: str | None) -> str` (maps "Tamil"/"tamil"/"ta" → "ta"; unknown/None → "en").

- [ ] **Step 1: Write failing tests**
```python
def test_care_profile_accepts_all_six_languages(db_session, manager_family):  # fixture builds family+manager
    for code in ("en", "ta", "hi", "te", "ml", "kn"):
        p = care.create_care_profile(db_session, mgr.id, fam.id, "P", "Amma", code)
        assert p.preferred_language == code

def test_language_code_maps_names():
    assert language_code("Telugu") == "te"
    assert language_code("malayalam") == "ml"
    assert language_code("kn") == "kn"
    assert language_code(None) == "en"
    assert language_code("French") == "en"
```
- [ ] **Step 2: Run** `pytest tests/test_parent_languages.py -v` → FAIL (`te` rejected; `language_code` missing).
- [ ] **Step 3: Implement** `languages.py`; set `ALLOWED_LANGUAGES = frozenset(LANGUAGE_CODES)`; update the `ValueError` text. In `careProfileSetup.ts` extend `LANGUAGE_CODES` with `telugu: "te", malayalam: "ml", kannada: "kn"`.
- [ ] **Step 4: Run** backend tests → PASS; `npx tsc -p . --noEmit` → exit 0.
- [ ] **Step 5: Commit** `feat: support six parent languages on care profiles`

### Task 2: Reminder times for every medicine

**Files:**
- Create: `backend/app/services/reminders.py`
- Modify: `backend/app/api/medicines.py` (two routes), `backend/app/schemas.py` (`ReminderTimesIn`, `ReminderTimesOut`)
- Modify: `frontend/src/api.ts` (`medicines.getReminders`, `medicines.setReminders`), `frontend/src/pages/MedicineForm.tsx` (times editor, reuse `ps-times` / `ps-time` styles from `prescription-scan.css`)
- Test: `backend/tests/test_medicine_reminders.py`

**Interfaces:**
- Produces: `GET /api/families/{family_id}/medicines/{medicine_id}/reminders` → `{"times": ["08:00","20:00"]}` (needs `medicines.view`); `PUT` same path body `{"times": [...]}` replaces all active reminders (needs `medicines.edit`), returns the same shape sorted ascending, duplicates removed.
- Produces (service): `list_reminder_times(db, medicine_id) -> list[str]`; `set_reminder_times(db, actor_id, family_id, medicine_id, times: list[str]) -> list[str]`.

- [ ] **Step 1: Write failing tests** — PUT `["20:00","08:00","08:00"]` returns `["08:00","20:00"]`; GET returns same; PUT `["25:00"]` → 422 (reuse the HH:MM validator from `PrescriptionMedicineIn`); Viewer PUT → 403; PUT `[]` clears.
- [ ] **Step 2: Run** → FAIL (404 route).
- [ ] **Step 3: Implement** service + routes. Replacing = set existing rows `active=False`, insert new rows. Frontend: on Edit load times via GET; on save call PUT after the medicine is created/updated (same pattern as price). Empty list allowed (once-a-day).
- [ ] **Step 4: Run** backend tests + tsc → PASS.
- [ ] **Step 5: Commit** `feat: reminder times for every medicine`

### Task 3: Dose log and "what's due today"

**Files:**
- Create: `backend/app/models/dose.py` (`MedicineDose`), `backend/alembic/versions/<rev>_add_medicine_doses.py`, `backend/migrations/007_add_medicine_doses.sql` (generated with `alembic upgrade <prev>:<rev> --sql`), `backend/app/services/doses.py`
- Modify: `backend/app/models/__init__.py`, `backend/app/api/medicines.py` (family read route)
- Test: `backend/tests/test_doses.py`

**Interfaces:**
- Produces model `MedicineDose`: `id, family_id, care_profile_id, medicine_id, dose_date: date, slot: str ("HH:MM" or "any"), status: str ("taken"|"not_taken"|"skipped"), recorded_at, recorded_by_user_id, source ("chatbot"|"manual"), remind_at: datetime|None, family_alerted_at: datetime|None`; unique (`medicine_id`, `dose_date`, `slot`).
- Produces `@dataclass DueDose(medicine_id: str, name: str, slot: str, due_at: datetime | None, status: str | None)`.
- Produces `local_now(profile: CareProfile) -> datetime`; `doses_today(db, profile, now: datetime) -> list[DueDose]` (all of today's slots, any status); `due_untaken(db, profile, now) -> list[DueDose]` (slots due at or before `now` — `"any"` always due — whose status is not `taken`, excluding slots whose `remind_at` is still in the future); `record_dose(db, profile, medicine_id, slot, status, actor_id, source, now) -> MedicineDose` (upsert on the unique key); `set_remind_later(db, profile, medicine_id, slot, minutes: int, now) -> MedicineDose` (validates minutes ∈ ALLOWED_DELAY_MINUTES).
- Produces `GET /api/families/{family_id}/medicines/doses/today?care_profile_id=` → `[{medicine_id, slot, status, recorded_at}]` (needs `medicines.view`).

- [ ] **Step 1: Write failing tests**
  - medicine with reminders 08:00/20:00 at local 09:00 → `due_untaken` returns only the 08:00 slot.
  - medicine with no reminders → one `"any"` slot; after `record_dose(... "taken")` it is no longer in `due_untaken`.
  - recording twice for the same slot updates, not duplicates.
  - profile timezone Asia/Kolkata, `now` = 2026-11-22 18:20 UTC (23:50 IST) → `dose_date == date(2026,11,22)`.
  - `set_remind_later(..., 7, ...)` → `ValueError`.
  - after `set_remind_later(..., 15, now)` the slot is absent from `due_untaken(now + 10 min)` and present at `now + 16 min`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** model, migration (one table + unique constraint), services (use `zoneinfo.ZoneInfo(profile.timezone)`), and the family read route.
- [ ] **Step 4: Run** `alembic upgrade head` on a scratch SQLite DB and the test suite → PASS; `alembic heads` shows one head.
- [ ] **Step 5: Commit** `feat: medicine dose log and due-today service`

### Task 4: Who is the parent? (care profile link)

**Files:**
- Create: `backend/app/services/parent_context.py`
- Modify: `backend/app/services/auth.py` or `families.py` where the parent invite is accepted (set `linked_user_id`)
- Test: `backend/tests/test_parent_context.py`

**Interfaces:**
- Produces `@dataclass ParentContext(user_id: str, family_id: str, profile: CareProfile, language: str, greeting_name: str)`.
- Produces `resolve_parent(db, user: User) -> ParentContext`: profile with `linked_user_id == user.id`; else, if the user is an active member whose role name is `"Parent"` in exactly one family with exactly one care profile, link it (set `linked_user_id`, commit) and return it; otherwise raise `ParentNotLinked` (new exception → HTTP 409 with detail "Ask your family to link your profile").
- Requires permission `voice.use_parent_mode` on that family.

- [ ] **Step 1: Write failing tests** — linked profile returned; unlinked Parent with one profile gets linked automatically; two profiles → `ParentNotLinked`; accepting a parent invite sets `linked_user_id` when the family has one profile; a Viewer → `PermissionDenied`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; register `ParentNotLinked` → 409 in `app/main.py`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: resolve and link the parent's care profile`

### Task 5: ElevenLabs speech adapters

**Files:**
- Modify: `backend/app/services/adapters/speech.py`, `backend/app/core/config.py`
- Test: `backend/tests/test_speech_adapters.py`

**Interfaces:**
- Settings added: `elevenlabs_stt_model: str = "scribe_v1"`, `elevenlabs_tts_model: str = "eleven_multilingual_v2"`, `elevenlabs_voice_id: str | None = None` (one default voice; per-language override left to builder).
- Produces `ElevenLabsSpeechToText.transcribe(audio: bytes, language: str, mime_type: str) -> str` (POST `https://api.elevenlabs.io/v1/speech-to-text`, multipart `file` + `model_id` + `language_code`, header `xi-api-key`); `ElevenLabsTextToSpeech.synthesize(text: str, language: str) -> tuple[bytes, str]` (POST `/v1/text-to-speech/{voice_id}`, returns `(mp3_bytes, "audio/mpeg")`).
- Produces `SpeechUnavailable(Exception)` raised when the key/voice is missing or the request fails; `get_speech_to_text()`, `get_text_to_speech()` factories (single mock points for tests).

- [ ] **Step 1: Write failing tests** with `urllib.request.urlopen` monkeypatched: request has `xi-api-key`, correct URL and `language_code`; STT returns the `text` field; missing key → `SpeechUnavailable`; HTTP error → `SpeechUnavailable`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** with `urllib.request` (multipart body built by hand), 20 s timeout.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: ElevenLabs speech-to-text and text-to-speech`

### Task 6: Understanding the parent's answers

**Files:**
- Create: `backend/app/services/understanding.py`
- Test: `backend/tests/test_understanding.py`

**Interfaces:**
- Produces `is_urgent(text: str) -> bool` — keyword list in all six languages (fall, fell, chest pain, can't breathe, breathless, dizzy/faint, bleeding, help, emergency + Tamil/Hindi/Telugu/Malayalam/Kannada equivalents; exact list builder's call).
- Produces `@dataclass MedicineAnswer(medicine_id: str, outcome: str)` with outcome ∈ `"taken" | "not_taken" | "remind_later" | "finished"`, and `@dataclass MedicineAnswers(items: list[MedicineAnswer], delay_minutes: int | None, unclear: bool)`.
- Produces `understand_medicines(text: str, due: list[DueDose], mode: str) -> MedicineAnswers`: when `mode` is online and Gemini is configured, one Gemini call returning JSON `{"answers":[{"medicine_id","outcome"}],"delay_minutes"}` constrained to the given due medicine ids; otherwise (or on any Gemini error) the existing `RuleBasedIntentParser`: with one due medicine map the intent to it; with several, a clear "yes/took all" or "no/not yet" applies to all, anything else → `unclear=True` (the engine then asks medicine by medicine).
- Gemini call is a module-level function `ask_gemini(prompt: str) -> dict` (mock point), same HTTP pattern as `prescription_scan.scan_document`.

- [ ] **Step 1: Write failing tests** — `is_urgent("I fell in the bathroom")`, `is_urgent("விழுந்துட்டேன்")`, `is_urgent("मैं गिर गई")` are True; `is_urgent("my knee hurts a little")` False; rules: one due med + "I took it" → taken; two due + "yes took both" → both taken; two due + "the BP one only" in rules mode → `unclear`; Gemini mode with `ask_gemini` mocked → mapped answers; Gemini raising → falls back to rules (no exception).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: understand health and medicine answers`

### Task 7: Check-in records, replies and the step machine

**Files:**
- Create: `backend/app/models/checkin.py` (`HealthCheckin`, `ChatMessage`), migration `<rev>_add_health_checkins.py` + `migrations/008_add_health_checkins.sql`, `backend/app/services/replies.py`, `backend/app/services/checkin.py`, `backend/app/services/family_alerts.py` (immediate alerts only)
- Test: `backend/tests/test_checkin_engine.py`

**Interfaces:**
- `HealthCheckin`: `id, family_id, care_profile_id, parent_user_id, checkin_date: date, step: str ("greet"|"health"|"medicines"|"appointments"|"done"), health_text: str|None, urgent: bool, started_at, updated_at, summary_sent_at: datetime|None`; unique (`care_profile_id`, `checkin_date`).
- `ChatMessage`: `id, checkin_id, sender ("bot"|"parent"), text, language, created_at`.
- `replies.py`: `reply(key: str, language: str, **values) -> str`. Keys and English copy (builder translates to ta/hi/te/ml/kn, short and warm):
  `greet_morning` "Good morning, {name}!" · `greet_afternoon` "Good afternoon, {name}!" · `greet_evening` "Good evening, {name}!" ·
  `ask_health` "How are you feeling today?" · `health_noted` "Thank you for telling me. I've shared it with {family}." ·
  `health_urgent` "I've alerted {family} right now. You can also call them using the button below." ·
  `meds_list` "You have {count} medicine(s) now: {names}. Did you take them?" · `meds_one` "Did you take {name}?" ·
  `meds_none` "You have no medicines due right now." · `meds_logged` "Okay, I've noted it." ·
  `meds_remind` "I'll remind you in {minutes} minutes." · `meds_finished` "I've told {family} that {name} has run out." ·
  `appt_today` "Today at {time} you have {reason} with {provider}." · `appt_tomorrow` "Tomorrow at {time} you have {reason} with {provider}." ·
  `goodbye` "Take care, {name}. Talk to you soon!" · `anything_else` "Is there anything else you'd like to tell me?" · `not_understood` "Sorry, I didn't catch that. Could you say it again?"
  Missing translation → English.
- `checkin.py`:
  - `@dataclass Turn(checkin: HealthCheckin, bot_messages: list[str], call_number: str | None, urgent: bool)`
  - `start_or_resume(db, ctx: ParentContext, now: datetime) -> Turn` — creates today's check-in at `greet` and produces greeting + `ask_health` (step → `health`); if one exists, re-greets and continues from its step (medicines step recomputes `due_untaken`).
  - `handle_parent_text(db, ctx: ParentContext, text: str, now: datetime) -> Turn` — stores the parent message, advances one step:
    - `health`: save `health_text`; `urgent = is_urgent(text)`; call `notify_family_urgent` if urgent, else `notify_family_update`; then move to `medicines`.
    - `medicines`: `understand_medicines` → `record_dose` / `set_remind_later`; `finished` → `notify_family_finished`; `unclear` → ask `meds_one` for the first remaining medicine; when none remain → `appointments`.
    - `appointments`: list scheduled/rescheduled appointments for the profile dated today or tomorrow (`services/appointments.list_appointments`), speak `appt_today`/`appt_tomorrow`, then `done` + `goodbye`.
    - `done`: `anything_else`; text is appended to `health_text` and shared.
  - `family_alerts.py` (this task): `family_recipients(db, family_id) -> list[User]` (all active members); `notify_family_update(db, ctx, checkin)` (in-app `notify(..., "checkin.update", ...)` to all); `notify_family_urgent(db, ctx, checkin, text)` (in-app `"checkin.urgent"` + email subject "Needs attention now: {name}"); `notify_family_finished(db, ctx, medicine)` (in-app + email).
  - Appointment `{time}` is shown in 12-hour form ("10:00 AM").
  - `call_number(db, ctx) -> str | None` — the family manager's onboarding profile `caregiver_phone`, else `doctor_contact_number`.
  - Bot and parent messages are written to `ChatMessage`; every step change writes an activity log entry (`checkin.updated`).

- [ ] **Step 1: Write failing tests** (time fixed via `now` argument; speech not involved):
  - start at 08:30 local → messages `["Good morning, Amma!", "How are you feeling today?"]`, step `health`.
  - second start the same day → no second `HealthCheckin` row.
  - "my knee hurts" → `health_text` saved, `urgent` False, next message lists due medicines.
  - "I fell" → `urgent` True, `call_number` returned, next message still lists medicines; a `checkin.urgent` notification exists for every member (manager, caregiver, viewer) and one email each (use the `RecordingEmail` fixture pattern from `tests/test_parent_invites.py`).
  - medicines "yes took both" (rules) → both `taken`; then appointment tomorrow 10:00 → `"Tomorrow at 10:00 AM you have Doctor follow-up with Dr. Rao"`; then step `done` with goodbye.
  - Tamil profile → greeting comes from the `ta` template.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** models, migration, replies, engine.
- [ ] **Step 4: Run** → PASS; `alembic heads` one head.
- [ ] **Step 5: Commit** `feat: parent check-in engine`

### Task 8: Family notifications, scheduled jobs and the parent API

**Files:**
- Create: `backend/app/services/scheduler.py`, `backend/app/api/parent.py`
- Modify: `backend/app/services/family_alerts.py` (add the scheduled functions)
- Modify: `backend/app/main.py` (router + start/stop scheduler on startup/shutdown, disabled when `settings.scheduler_enabled` is False), `backend/app/core/config.py` (`scheduler_enabled: bool = True`), `backend/app/schemas.py`
- Test: `backend/tests/test_family_alerts.py`, `backend/tests/test_parent_api.py`

**Interfaces:**
- Consumes from Task 7: `family_recipients`, `notify_family_update`, `notify_family_urgent`, `notify_family_finished`.
- Adds to `family_alerts.py`: `send_daily_summaries(db, now)` (one email per member per check-in with `summary_sent_at` null and date < today, or at 20:00 local for today; sets `summary_sent_at`); `alert_missed_doses(db, now)` (doses still not taken ≥ 60 min after `due_at`/`remind_at`, `family_alerted_at` null → in-app + email "Medicine not taken", set `family_alerted_at`).
- `scheduler.py`: APScheduler `BackgroundScheduler` running `alert_missed_doses` every 10 min and `send_daily_summaries` every 30 min, each in its own DB session.
- `api/parent.py` (prefix `/api/parent`, all resolve `ParentContext`):
  - `GET /checkin` → `CheckinOut {checkin_id, step, messages: [{sender, text, created_at}], call_number, language, reminders_due: [{medicine_id, name, slot, remind_at}]}` (starts/resumes today's check-in).
  - `POST /checkin/text` body `{"text": str}` → `TurnOut {messages: [{sender, text}], step, urgent, call_number, audio: str | None (base64 mp3 of the bot reply), audio_type: str | None}`.
  - `POST /checkin/voice` multipart `file` (audio, ≤ 2 MB) → same `TurnOut` plus `transcript: str`. STT failure → 503 `{"detail": "Voice isn't available right now. Please type instead."}`.
  - TTS failure on any turn → `audio: null`, still 200.
- [ ] **Step 1: Write failing tests** — daily summary sends exactly once per member; missed dose alerted once; parent API text turn returns messages and `audio` null when TTS raises `SpeechUnavailable`; voice turn with STT mocked returns `transcript`; Viewer calling `/api/parent/checkin` → 403; unlinked parent with two profiles → 409.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Tests set `settings.scheduler_enabled = False`.
- [ ] **Step 4: Run** full suite → PASS.
- [ ] **Step 5: Commit** `feat: family alerts, scheduled jobs and parent check-in API`

### Task 9: Parent chat page and parent routing

**Files:**
- Create: `frontend/src/pages/ParentChat.tsx`, `frontend/src/parent-chat.css`, `frontend/src/parentApi.ts`
- Modify: `frontend/src/App.tsx` (route `/parent/chat`; `/parent/home`, `/parent/checkin`, `/parent/confirmation`, `/parent/help` → `<Navigate to="/parent/chat" replace />`), `frontend/src/pages/ParentAcceptInvite.tsx` (navigate to `/parent/chat`), `frontend/src/pages/Landing.tsx` (after sign-in, `user.role === "parent"` or `families.me(...).role === "Parent"` → `/parent/chat`, others unchanged)

**Interfaces:**
- Consumes Task 8 endpoints. `parentApi.ts`: `getCheckin(): Promise<CheckinOut>`, `sendText(text): Promise<TurnOut>`, `sendVoice(blob: Blob): Promise<TurnOut>` (multipart, Bearer token like `medicineImage.ts`).
- Page behaviour: chat bubbles (bot left, parent right), text ≥ 20px; one large round mic button — tap to start `MediaRecorder` (`audio/webm`), tap again or 15 s max to stop and send; while waiting show "Listening…" / "Thinking…"; play `audio` automatically (base64 → `Blob` → `Audio`); "Type instead" input; red **Call {family}** button (`tel:` link) shown when `call_number` is set and always reachable from a Help button; when `reminders_due` has an item whose `remind_at` passes while the page is open, call `getCheckin()` and show/speak the new question. Mic permission denied → show the text input and a friendly message.

- [ ] **Step 1:** Implement `parentApi.ts` + page + routing.
- [ ] **Step 2: Run** `npx tsc -p . --noEmit` → exit 0.
- [ ] **Step 3: Verify in the browser** (backend running, a parent account linked to the demo profile): page greets by time of day, typed health answer → medicine question, "yes" → appointment reminder → goodbye; urgent text shows the Call button; at 390 px width no horizontal scroll; old `/parent/home` redirects to `/parent/chat`.
- [ ] **Step 4: Commit** `feat: parent voice chat page and parent routing`

### Task 10: Today's dose status on family medicine pages

**Files:**
- Modify: `frontend/src/api.ts` (`medicines.dosesToday(familyId, careProfileId)`), `frontend/src/pages/MedicineList.tsx`, `frontend/src/pages/MedicineDetail.tsx`, `frontend/src/medicines.css`

**Interfaces:**
- Consumes `GET /api/families/{family_id}/medicines/doses/today?care_profile_id=` (Task 3).
- List: "Next check-in" column shows the next reminder time and, per slot today, "✓ Taken 8:10 AM" / "Not taken" / "Due 8:00 PM". Detail: a "Today" card listing each slot with its status. Display only.

- [ ] **Step 1:** Implement.
- [ ] **Step 2: Run** `npx tsc -p . --noEmit` → exit 0.
- [ ] **Step 3: Verify in the browser:** log a dose via the parent chat, the family list shows "✓ Taken" with the time.
- [ ] **Step 4: Commit** `feat: show today's dose status to the family`
