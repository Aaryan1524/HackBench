# HackBench

> **Empirical, evidence-based hackathon project evaluation and pitch diagnostic engine.**

HackBench benchmarks your hackathon project against **over 700 real historical submissions, winners, and prize criteria** before you pitch to judges.

---

## Why HackBench?

In most hackathons, judges spend just **3 to 5 minutes** reviewing your project. High-potential projects routinely lose top placements not because the underlying code is lacking, but because:

1. **The problem statement is vague or buried**: Judges cannot easily understand *why* the product exists.
2. **The target audience is generic**: "Everyone" is not a target user.
3. **The demo does not prove the core claims**: Judges see slides or UI mockups instead of tangible evidence.
4. **Sponsor criteria are treated as an afterthought**: The submission tags a sponsor tool without solving the sponsor's explicit problem.

HackBench acts as an objective, pre-pitch review board. It inspects your narrative, target audience, demo proof, engineering depth, and sponsor requirements to highlight **concrete gaps and prioritized fixes** before submission deadlines close.

---

## Strict Core Invariants

HackBench is strictly designed around empirical evidence and integrity:

- 🚫 **NO Win / Loss Predictions**: HackBench **never** predicts whether you will win or outputs placement odds. Its sole purpose is diagnostic quality and constructive improvement.
- 🚫 **NO Fabricated Metrics**: Lines of code, framework detections, and API routes are derived strictly from deterministic static analysis. If a repo or link is missing, it is reported honestly without speculation.
- 🚫 **NO Code Execution**: Repositories are inspected solely via read-only static file analysis and AST parsing. HackBench **never** runs `npm install`, `pip install`, shell scripts, or container builds on untrusted code.

---

## 2-Minute Quickstart

### Prerequisites
- **Python 3.12+**
- **Node.js 18+** and **npm**
- [**uv**](https://github.com/astral-sh/uv) (recommended Python package manager)

### 1. Clone & Setup Backend
```bash
git clone https://github.com/Aaryan1524/HackBench.git
cd HackBench

# Install backend dependencies
uv sync

# Configure environment variables
cp .env.example .env
```

### 2. Configure Environment (`.env`)
```bash
# Optional API Keys for enhanced analysis (falls back to calibrated deterministic offline evaluators if omitted)
JEV_API_KEY=your_jev_api_key_here
CHATGPT_API_KEY=your_chatgpt_api_key_here
CHATGPT_MODEL=gpt-5.6-terra

# Server defaults
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
FRONTEND_URL=http://localhost:3000
```

### 3. Start Backend API
```bash
uv run uvicorn hackbench.api.server:app --host 127.0.0.1 --port 8000
```
API health check: `http://localhost:8000/health`

### 4. Start Web Application
```bash
cd web
npm install
npm run dev
```
Open **[http://localhost:3000](http://localhost:3000)** in your browser.

---

## How to Evaluate Your Project

HackBench offers two flexible input workflows depending on where you are in the hackathon cycle:

### Path A: Manual Entry (Fastest during hackathon crunch)
Ideal when your project isn't published yet or your code is still in progress:
- **Project Name & Tagline**: A concise one-sentence pitch.
- **Problem Statement**: What real friction exists today?
- **Target Audience**: Exactly who encounters this problem regularly?
- **What It Does & How It Works**: The core workflow, architecture, and technology stack.
- **Sponsor & Track Requirements (Mandatory)**: Paste the exact criteria or prompt from the sponsor/grand prize track (e.g., *"Must use MongoDB Atlas Vector Search and solve healthcare accessibility"*). HackBench verifies your project specifically against this mandate.

### Path B: Public Links
Ideal once your submission materials are live:
- **GitHub Repository URL**: Verifies commit timelines, lines of code, frameworks, test suites, and API endpoints via static inspection.
- **Devpost Draft URL**: Pulls your submitted writeup and team claims.
- **Live Deployment & Video Demo URLs**: Performs live reachability checks and verifies video demonstration evidence.

---

## Multi-Year Empirical Baseline

HackBench benchmarks candidate submissions against **734 real hackathon submissions** collected across multiple years of Florida's largest hackathon (ShellHacks):

| Event | Total Submissions | Track / Sponsor Prizes | Overall Winners |
| :--- | :--- | :--- | :--- |
| **ShellHacks 2025** | 245 projects | 28 categories | 3 projects |
| **ShellHacks 2024** | 257 projects | 25 categories | 3 projects |
| **ShellHacks 2023** | 232 projects | 25 categories | 3 projects |
| **Total Baseline** | **734 projects** | **78 prize tracks** | **9 grand champions** |

You can choose your comparative benchmark year directly in the web UI dropdown (`ShellHacks 2025`, `2024`, or `2023`).

---

## What the Diagnostic Report Delivers

1. **Executive Verdict & 3 Core Blocks**:
   - **Audience & Problem Clarity**: Evaluates how crisply the problem is communicated and whether the user persona is sharp.
   - **Product & Demo Proof**: Checks for tangible evidence of functionality versus static claims.
   - **Technical Feasibility & Depth**: Verified engineering metrics, architectural sanity, and API surface.
2. **What to Fix Before Presenting**:
   - A prioritized, high-contrast action list targeting the highest-leverage improvements to make in your demo script, README, or UI before pitching to judges.
3. **Historical Dimension Comparisons**:
   - Benchmark your rating against the empirical distribution of past winners and strong non-winners across 9 rubrics (*Problem Clarity, User Clarity, Product Clarity, Demo Strength, Completion, Practicality, Story, Memorability, Track Alignment*).
4. **Targeted Sponsor & Track Alignment**:
   - A dedicated evaluation detailing how tightly your narrative meets the sponsor's technical and thematic requirements.
5. **Deterministic Engineering Verification**:
   - Lines of code, detected frontend/backend frameworks, test frameworks (`pytest`, `jest`, `vitest`), REST/GraphQL routes, and live HTTP deployment response status.

---

## CLI Tools

For power users, hackathon researchers, and organizers, HackBench provides an extensive command-line interface:

```bash
# Benchmark a local project repository or folder:
hackbench benchmark-project ./my-hackathon-repo \
  --name "Project Name" \
  --tagline "One-line pitch" \
  --what "Summary of what the project does" \
  --tags "React, FastAPI, PostgreSQL" \
  --deploy "https://my-app.vercel.app"

# Ingest event rules and prize categories from Devpost:
hackbench ingest-event https://shellhacks2025.devpost.com/

# Collect gallery submissions and quarantine official outcomes:
hackbench collect-projects shellhacks2025:2025 --all

# Run multi-pass blind evaluation:
hackbench evaluate-blind shellhacks2025:2025

# Unseal official awards and generate comparative forensics:
hackbench reveal-results shellhacks2025:2025
hackbench analyze shellhacks2025:2025
```

---

## Testing & Verification

The test suite enforces deterministic metric parsing, security boundaries, rate limiting, and core invariants:

```bash
uv run pytest tests/ -v
```

Test coverage includes:
- **SSRF Safeguards**: Rejection of localhost (`127.0.0.1`), RFC1918 private subnets, cloud metadata endpoints (`169.254.169.254`), and `file://` URIs.
- **Untrusted Input Boundaries**: Sanitization of XML delimiters, script injection, and untrusted user narrative text.
- **Outcome Quarantine**: Verification that award data is sealed with cryptographic hashes and never leaks into blind evaluation passes.
- **Mandatory Sponsor Flow**: Verification that custom sponsor requirements are routed into criteria alignment evaluations.

---

## This year's challenges (ShellHacks 2026)

ShellHacks 2026 is the default source of prizes: your idea is matched against its general awards and sponsor challenges. It has no results yet, so it is a **prize source only** and is not offered under "Compare against". The challenge list lives in `data/raw/shellhacks2026/2026/event/sponsor_challenges.yaml` (as provided by the organizers). To change it, edit that file and run:

```bash
uv run --with pyyaml python scripts/import_event_yaml.py data/raw/shellhacks2026/2026/event
```

This regenerates `event_metadata.json`. Prize items (gift cards, swag) are kept only in the raw record and never treated as judging criteria; nothing is invented (unknown URLs stay empty). Matching notes:
- **Required technology** (the MLH challenges): the idea must actually plan to use it. Named in the core workflow is a strong fit, only in the tech stack is moderate, absent is weak.
- **Stated rules:** for example Microsoft's "cannot be a chatbot" caps the fit of a chatbot idea and says why.
- **Other challenges:** ranked by shared subject matter with the challenge's own description.

The page has two selectors: **Prizes from** (default ShellHacks 2026) and **Compare against** (past results). The API takes `prize_event_id` and `event_id`; if `prize_event_id` is omitted, prizes come from `event_id`.

## Comparison baseline ("Compare against")

The dropdown chooses which past hackathon a review is measured against. It changes two things, and both follow your choice:

- **Prizes:** ideas are matched against that year's published prizes. Prizes with no real criteria (only a title, a slogan, or a swag item) are left out rather than guessed, and 1st/2nd/3rd "Overall" placements count as one target.
- **Past-winner comparison:** the averages, sample sizes and takeaways come from that year's own analysis (`reports/<event>/forensics_summary.json`).

Options: **ShellHacks 2025**, **2024**, **2023**, and **All years combined**. Combined pools every year's winners and non-winners weighted by sample size, uses one Overall prize (from the newest year) plus each other year's prizes de-duplicated by title, and only states a pattern when every year agrees with it.

Each year's history is produced by the same pipeline: `hackbench collect-repos`, `evaluate-blind`, `reveal-results`, `analyze`, `report` for that event. To add a year, ingest its event and projects, place its sealed outcomes, then run those five steps. The dropdown and the backend list are in `web/app/page.tsx` (`BASELINE_OPTIONS`) and `src/hackbench/ai/baselines.py` (`YEAR_BASELINES`). An unknown baseline falls back to ShellHacks 2025 and says so.

Limits: matching for sponsor prizes is rule-based (hand-written rules for a few sponsors, plus wording overlap with the prize's own description for the rest), so read a challenge in full before targeting it. The historical dimensions are the ones the blind evaluation measured, not every dimension the review shows.

## Analytics

HackBench uses [PostHog](https://posthog.com) to measure traffic and usage. It is optional, anonymous, and built so that nothing a user types can be sent.

### What is measured
- **Visitors, sessions, referrers, UTM campaigns:** PostHog's standard page view (one per page load), with anonymous visitor and session IDs. There are no accounts and nothing that identifies a person.
- **Product events:** a small fixed set, listed below. Each has only enumerated values, booleans, or a small integer.

### What is never collected
Idea text, project descriptions, README or source code, repository contents, generated analysis text, sponsor requirement text, GitHub/Devpost/demo URLs, email addresses, names, API keys, raw error messages, or anything typed into a form. Session recording, autocapture, feature flags, surveys and person profiles are all off.

This is enforced in `web/lib/analytics.ts`: every event has an explicit list of allowed properties and allowed values, and anything else is dropped before it reaches PostHog. Query strings on the page URL are stripped, except `utm_*` and `ref`, so attribution still works. Visitors with browser Do Not Track enabled are not counted.

### Vercel Analytics (page views)
The site also includes Vercel Analytics for simple page-view and visitor counts, next to PostHog. It is cookieless and collects no page content, and query strings are stripped (except `utm_*` and `ref`) before anything is sent. It only reports on a Vercel deployment: turn it on under the project's **Analytics** tab in the Vercel dashboard. `NEXT_PUBLIC_ANALYTICS_ENABLED=false` switches off both PostHog and Vercel Analytics. The package is pinned to `@vercel/analytics@1.3.2` because newer versions declare an optional SvelteKit peer that conflicts with the test tooling's Vite version, and the app does not use Svelte.

### Event schema

| Event | When | Properties |
|---|---|---|
| `$pageview` | Page load (PostHog built-in, once) | PostHog defaults, URLs scrubbed |
| `mode_selected` | User switches between idea and project | `mode` |
| `analysis_started` | User submits a review (not on client-side validation errors) | `mode`, `event_id`, `input_type`, `prize_targeting`, `has_repo`, `has_demo` |
| `analysis_completed` | A usable result is shown | the above, plus `duration_bucket`, `jev_used`, `gemini_used`, `fallback_used`, `result_quality` |
| `analysis_failed` | The review request failed | `mode`, `event_id`, `input_type`, `failure_stage`, `http_status_class` |
| `prize_fit_viewed` | The prize-fit section scrolls into view (idea reviews) | `event_id`, `fit_count`, `automatic_targeting` |
| `evidence_opened` | The "Why this analysis?" / evidence drawer is opened | `mode` |
| `review_again_clicked` | "Review another idea/project" is clicked | `mode` |

Values: `mode` is `idea` or `project`; `input_type` is `manual`, `github`, `devpost` or `mixed`; `prize_targeting` is `automatic`, `specific` or `none` (project reviews); `event_id` is one of the public ShellHacks identifiers or `other`; `duration_bucket` is `<2s`, `2-5s`, `5-10s`, `10-20s` or `20s+`; `failure_stage` is `validation`, `source_fetch`, `repo_analysis`, `ai_provider`, `historical_lookup` or `unknown`; `http_status_class` is `4xx`, `5xx` or `network`.

The routing flags come from the backend (`telemetry` in the analysis response), never guessed by the browser. `jev_used` means the Jev provider rated the dimensions. `gemini_used` is the name analytics uses for the second AI provider, which is ChatGPT in this deployment. `fallback_used` means built-in heuristics or a local fallback replaced a live AI result, or Jev handed a low-confidence rating to ChatGPT. `result_quality` is `partial` when the review carries notes, used a fallback, or (project reviews) lacked evidence for some dimension.

`failure_stage` is `validation` for any 4xx. For 5xx the backend sets an `X-Failure-Stage` header only where it knows the stage (currently `repo_analysis` for "busy" and `unknown` for unexpected errors). Most source and AI problems do not fail a review, they degrade it and show up as `result_quality: partial`, so `source_fetch`, `ai_provider` and `historical_lookup` are reserved and will normally be zero.

### Enable, disable, configure
1. Create a PostHog project and copy its **project API key** (safe for browsers; PostHog documents it as public). Never use a personal/management API key here.
2. Set in the root `.env` (local; the frontend config reads only `NEXT_PUBLIC_*` and `BACKEND_URL` from it, never your API keys) or in your host's environment settings (production):
   ```
   NEXT_PUBLIC_POSTHOG_KEY=phc_...
   NEXT_PUBLIC_POSTHOG_HOST=https://us.i.posthog.com   # or https://eu.i.posthog.com
   ```
   `NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN` is also accepted, which is the name PostHog's current docs use.
3. These are read at **build** time (`npm run build`), so rebuild after changing them.
4. Local `npm run dev` sends nothing unless you set `NEXT_PUBLIC_ANALYTICS_ENABLED=true`. Set it to `false` to force analytics off anywhere. With no key at all, every call is a silent no-op and the app behaves identically.
5. In PostHog project settings, also turn on **Discard client IP data** if you do not want IP-derived location.

Analytics never blocks the app: every call is fire-and-forget inside a try/catch, and ad blockers or network errors are ignored.

### Dashboard: "HackBench — V1 Traction"
Create these insights in PostHog and pin them to one dashboard:

| Insight | Type | Definition |
|---|---|---|
| Unique visitors | Trends | `$pageview`, **Unique users** |
| Sessions | Trends | `$pageview`, **Unique sessions** |
| Completed analyses | Trends | `analysis_completed`, **Total count** |
| Visitor to completion | Funnel | `$pageview` then `analysis_completed`, unique users; read the overall conversion |
| Returning users | Retention | Start `$pageview`, return `$pageview`, weekly (or Lifecycle, returning) |
| Main funnel | Funnel | `$pageview` then `analysis_started` then `analysis_completed`; break down by `mode` (`$pageview` has no `mode`, so the breakdown applies from the second step) |
| Idea vs project | Trends | `analysis_completed`, break down by `mode` |
| Input used | Trends | `analysis_started`, break down by `input_type` |
| Hackathon analysed | Trends | `analysis_completed`, break down by `event_id` |
| Reliability | Trends (formula) | `analysis_failed` / `analysis_started`; break down failures by `failure_stage` |
| AI fallback rate | Trends | `analysis_completed`, break down by `fallback_used`; also `result_quality` |
| Traffic sources | Trends | `$pageview`, unique users, break down by `Referring domain`, then `utm_source`, then `utm_campaign` |

Use UTM links when you share HackBench, for example `?utm_source=linkedin&utm_campaign=launch`. Referrers such as GitHub or ShellHacks appear automatically.

### Reading the numbers honestly
Counts reflect only what PostHog measured. They undercount visitors who block analytics or send Do Not Track, and a person on two browsers or devices counts twice (there are no accounts). Report figures as "measured by PostHog".

## Deployment (Railway backend + Vercel frontend)

The backend runs `git`, writes temporary files, and a review can take 20 to 45 seconds, so it needs a container host (Railway). The frontend is a Next.js app (Vercel). The backend will have a public URL, so it is protected by a **shared secret**: the frontend adds it on the server, and the backend refuses every `/api` call without it. Visitors' browsers never see the secret or the backend address.

### 0. Before you deploy
Commit and push everything the backend reads at runtime: `reports/` (each year's history), `data/raw/*/*/event/event_metadata.json` (prizes) and `data/processed/`. Railway builds from your GitHub repo, so anything not pushed is missing there. Generate one secret and keep it handy:

```bash
openssl rand -hex 32
```

### 1. Railway (backend)
1. New Project, Deploy from GitHub repo. Railway detects the `Dockerfile` in the repo root. Leave the root directory as the repo root.
2. Variables:

| Variable | Value |
|---|---|
| `BACKEND_SHARED_SECRET` | the secret you generated |
| `CHATGPT_API_KEY` | your OpenAI key |
| `CHATGPT_MODEL` | for example `gpt-5.6-luna` |
| `DAILY_ANALYSIS_LIMIT` | optional, default 1500 reviews per day (`0` turns the cap off) |
| `MAX_CONCURRENT_ANALYSES` | optional, default 8 |

   `HACKBENCH_ENV=production` is already set in the image. Do not set `PORT`: Railway assigns it and the container follows it.
3. Settings, Networking: **Generate Domain** (the frontend needs a public URL to call). Settings, Deploy: set the healthcheck path to `/health`.
4. Open `https://<your-domain>/health`: it should say `healthy` and `historical_dataset_ready: true`. Calling `/api/analyze` directly must return `401 Unauthorized`.
5. Set a monthly spend limit on the OpenAI key.

If the build fails with `failed to open file /app/README.md`, the Dockerfile in your repo is out of date: it must contain `COPY README.md LICENSE ./` before the second `uv sync`.

### 2. Vercel (frontend)
1. Import the repository. **Set Root Directory to `web`** and Framework Preset to Next.js. Without this, Vercel inspects the repo root, finds the Python backend, and fails with "No FastAPI entrypoint found".
2. Environment variables (Production):

| Variable | Value |
|---|---|
| `BACKEND_URL` | `https://<your-railway-domain>` (no trailing slash) |
| `BACKEND_SHARED_SECRET` | the same secret as Railway |
| `NEXT_PUBLIC_POSTHOG_KEY` | your PostHog project key |
| `NEXT_PUBLIC_POSTHOG_HOST` | `https://us.i.posthog.com` (or the EU host) |
| `NEXT_PUBLIC_ANALYTICS_ENABLED` | `true` |

   Only the `NEXT_PUBLIC_*` values are visible in the browser. `BACKEND_URL` and `BACKEND_SHARED_SECRET` are read only on the server, and they are read at request time, so changing them does not need a rebuild (the `NEXT_PUBLIC_*` ones do).
3. Deploy, then run one idea review and one project review on the live site.
4. A review can take up to about 45 seconds. The API route allows 60 seconds; if your Vercel plan caps functions lower, reviews will time out with a friendly "took too long" message, so pick a plan or setting that allows 60 seconds.

### 3. What protects the live site
- `/api` on the backend needs the shared secret; the frontend proxy only forwards `POST /api/analyze` and `GET /api/events/<id>/prizes`.
- Per-visitor rate limit (25 per minute) using the visitor address Vercel provides, plus a whole-service daily cap and a cap on reviews running at once.
- Submitted links are checked at every redirect hop, response sizes and times are capped, repositories are cloned over https only from GitHub, GitLab or Bitbucket with strict size, file-count and time limits, and every clone is deleted after the review.
- Nothing typed by users is stored, logged, or sent to analytics.

## Contributing & License

HackBench is open-source under the [MIT License](LICENSE). Contributions, bug reports, and dataset additions are welcome via pull requests.