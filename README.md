# CareCircle

CareCircle helps a family look after an elderly parent together, even when they live in different cities. The parent gets a simple app they can talk to in their own language. The rest of the family gets one shared place to see how the parent is doing and to split the work of caring for them.

## What CareCircle does

### For the parent

- **Talk instead of type.** The parent can speak to the app, and it replies out loud. It works in English, Tamil, Hindi, Telugu, Malayalam and Kannada.
- **Medicine reminders.** The parent is reminded when it's time for a medicine and can say they took it.
- **A daily "I'm fine" button.** One tap tells the family all is well. If the parent doesn't tap it, the family is told.
- **Today's plan.** The parent can see today's medicines, appointments and anything the family asked them to do.
- **Notes and reminders.** The parent can write a note, and set a reminder for themselves or for someone in the family.
- **Ask the family for help.** The parent can ask for something, like a lift to the doctor, and the family sees the request.
- **Video calls.** A family member can video-call the parent, and the parent answers with one big button. The parent can also choose to have calls answered automatically.
- **Emergency help.** There's a button that alerts the family, a button to call 108, and a link to the nearest hospital. The phone can also try to notice a fall, if the parent turns that on.
- **Refills.** When tablets are running low, the app asks whether to order more.

### For the family

- **Family chat with an assistant.** You can ask questions like "How was Amma last month?" and get a short summary with a dashboard of medicines, spending, conversations and incidents.
- **Overview and "This week".** These show at a glance how the parent is doing and what's coming up.
- **Care profile.** Keeps the parent's details, doctor, preferred hospital and emergency contacts in one place.
- **Medicines.** Add, change or stop medicines, see whether doses were taken, and keep a rough count of tablets left. You can also photograph a prescription so the app fills in the medicines for you.
- **CareVoice activity.** Shows what the parent said to the app and how they've been feeling.
- **Tasks.** Share out the jobs to be done (buy groceries, pay a bill) and tick them off.
- **Appointments.** Keep track of doctor visits, and record what the doctor said afterwards.
- **Records.** Store reports and bills.
- **Health notes.** Keep a list of allergies, conditions and readings like blood pressure and sugar. You get a warning when blood pressure keeps rising.
- **Insurance and renewals.** Get reminded before a policy is due.
- **Care circle.** Neighbours, friends and helpers the family trusts, who can be asked to check in.
- **Medical file.** Everything a new doctor needs, in one place. You can search it, and share it with a doctor through a link that stops working after 1, 7 or 30 days.
- **Sharing care.** For brothers and sisters. It shows who paid for what, who owes whom, and who visited this month.
- **Paperwork.** Reminds you about the yearly chores, like the pension life certificate, the income tax return, bank KYC and property tax.
- **Carer's day.** A paid carer at home can tick off meals and medicines and leave a note. They can also raise a concern, which alerts the family.
- **Weekly summary.** A short report on the parent's week.
- **Family members and permissions.** Invite family members, choose what each person can see and do, and decide how each person is notified (in the app, by email, or by SMS/WhatsApp).

## How to run it

These steps are for running CareCircle on your own Windows computer for testing. There are two parts. The **backend** is the server that stores the data. The **frontend** is the website you open in your browser. Run both at the same time, in two separate PowerShell windows.

### 1. Install the tools (once)

- [Python 3.11](https://www.python.org/downloads/). Tick "Add Python to PATH" when you install it.
- [Node.js 20 or newer](https://nodejs.org/). This includes `npm`.
- [Git](https://git-scm.com/download/win).
- [PostgreSQL](https://www.postgresql.org/download/windows/). This is optional. Without it, the app uses a small local database file (SQLite), which is fine for trying the app out.

### 2. Get the code (once)

```powershell
git clone https://github.com/vikramDlearners/wisperflowdemo.git
cd wisperflowdemo
```

### 3. Set up the backend (once)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `backend\.env` in a text editor and fill in what you need:

| Setting | What it is | Needed? |
|---------|------------|---------|
| `DATABASE_URL` | Your PostgreSQL address, for example `postgresql+psycopg://user:password@localhost:5432/carecircle`. Leave it blank to use the local SQLite file. | No |
| `SECRET_KEY` | Any long random text. It keeps sign-ins secure. | Yes |
| `DEV_FIXED_OTP` | Set it to `123456` while testing, so you can sign in without receiving an email. | Recommended for testing |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Your email server, used to send sign-in codes and alerts. | No |
| `GEMINI_API_KEY` | Google Gemini key. It powers the chat assistant, prescription reading and summaries. | No, but many smart features need it |
| `ELEVENLABS_API_KEY` | ElevenLabs key, used for the parent's voice (speech to text and text to speech). | No, but voice needs it |

Then create the database tables, and if you like, add some sample data:

```powershell
alembic upgrade head
python -m app.seed
```

### 4. Set up the frontend (once)

In a second PowerShell window, from the `wisperflowdemo` folder:

```powershell
cd frontend
npm install
```

### 5. Start the app (every time)

**Window 1, the backend:**

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --port 8000
```

**Window 2, the frontend:**

```powershell
cd frontend
npm run dev
```

Open **http://localhost:5173** in your browser. Sign in with your email address. If you set `DEV_FIXED_OTP=123456`, type `123456` as the code.

To stop the app, press `Ctrl+C` in each window.

### After pulling new code

Run these again, in case something new was added:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
```

```powershell
cd frontend
npm install
```

### Running the tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest -q
```

### Good to know

- The backend runs at http://127.0.0.1:8000. You can browse its API at http://127.0.0.1:8000/docs.
- SMS is simulated (`SMS_PROVIDER=mock`) unless you connect a real provider, so no real text messages are sent.
- Video calls use Google's public STUN server. On some office or mobile networks, a call may not connect.
- Ready-made Postman collections for the API are in the `postman` folder.
