# JobPilot AI — Demo Script (about 6 minutes)

**Before the demo (10 minutes earlier)**
1. Start PostgreSQL, then the backend and frontend (see README → Getting started).
2. Open http://127.0.0.1:8000/health — it must answer.
3. Log in at http://localhost:3000.
4. Gmail is connected (Applications page shows "Gmail: <your address>").
5. Run "Apply with AI" once for Pakistan, so company research and recruiter emails are already saved (the demo is then fast).
6. Keep a second tab open on **Agent Transparency**.

---

## 1. The idea (30 s)
"JobPilot AI has three agents — CV, Job and Email — that take you from a CV to a ready job application.
Its rule is **real data only**: no invented jobs, scores, company facts or email addresses, and every step is visible."

## 2. CV Agent (1 min) — Confirm page
- Click **Choose CV file** and upload the CV.
- Point out: facts appear in a few seconds (quick read), then the AI improves them in the background.
- "Every value must be written in my CV. I confirm each fact before it is saved."
- Click **Sync to profile**.

## 3. Job Agent (1 min) — Jobs page
- Click **Find jobs for my CV**, then **Pakistan**, then **Remote**.
- Point out: city and province (e.g. *Lahore, Punjab, Pakistan*), honest match score, "Your CV covers X of Y skills; missing: …".
- Open one job: matched skills and gaps.

## 4. Email Agent (1.5 min) — Applications page
- Open an application.
- **Company Intelligence:** "read from the company's own website; every line appears on that page" + source link.
- **Email:** written by AI, then fact-checked; removed claims are shown in red.
- **Create Gmail Draft:** recipient filled from a real source (shown under the box), CV attached automatically.
- Approve → open Gmail Drafts: the email and the CV PDF are there. Nothing was sent.

## 5. One click: Apply with AI (1.5 min) — Overview page
- Choose **Pakistan**, keep **Only jobs with a recruiter email** on, click **Apply with AI**.
- Watch the six steps turn green; switch to **Agent Transparency** to show each agent's live run and its external calls (Gemini, SerpAPI, Apify, Firecrawl).
- Click **Review email & create draft**.

## 6. Honesty and safety (30 s)
- "If a company publishes no email (big companies like Coinbase), the agent says so and shows the Apply link — it never guesses an address."
- "Emails are only ever saved as Gmail drafts after my approval. Keys are never shown or logged."

---

## If something goes wrong live
| Problem | What to say / do |
|---|---|
| A provider is slow | "The agents call real services; the dashboard shows exactly which call is running." Show Agent Transparency. |
| No jobs with an email | Untick "Only jobs with a recruiter email" or choose another location. |
| Gmail not connected | Click **Connect Gmail** in the draft popup. |
| Backend not reachable ("Failed to fetch") | Restart the backend window. |
