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
uv run uvicorn hackbench.api.server:app --host 0.0.0.0 --port 8000
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

## Deployment

### Backend (Docker / Cloud Run / Railway / Fly.io)
```bash
# Build production image
docker build -t hackbench-api .

# Run container
docker run -p 8000:8000 \
  -e JEV_API_KEY="your_key" \
  -e CHATGPT_API_KEY="your_key" \
  hackbench-api
```

### Frontend (Vercel)
1. Import the repository into Vercel.
2. Set the Root Directory to `web`.
3. Set the environment variable `BACKEND_URL` to your production backend endpoint.

---

## Contributing & License

HackBench is open-source under the [MIT License](LICENSE). Contributions, bug reports, and dataset additions are welcome via pull requests.