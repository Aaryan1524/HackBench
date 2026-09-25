# HackBench Forensics (Hackathon Forensics)

> **Empirical, evidence-grounded hackathon evaluation and historical comparison engine.**

HackBench allows hackathon participants, researchers, and organizers to evaluate a project submission against historical hackathon winners, strong non-winners, and documented judging criteria based strictly on observable public evidence.

---

## What HackBench Does

- **Collects Public Evidence**: Ingests project claims, Devpost writeups, public Git commit timelines, code metrics, and live deployment reachability.
- **Enforces Logical Blinding**: Evaluates project quality without knowing official placement or awards, sealing evaluations with cryptographic hashes before outcome reveal.
- **Compares Against Historical Cohorts**: Measures judge-facing presentation and engineering depth against empirical distributions of past winners and strong non-winners.
- **Identifies Verifiable Gaps**: Highlights concrete, evidence-backed improvements (e.g. unhandled TODOs, missing demo proof, static mock data, unreachable deployments).
- **Supports Two Participant Input Modes**:
  - **Path A (Link-based)**: Provide public GitHub, Devpost, and deployment URLs.
  - **Path B (Manual)**: Describe the problem, user, workflow, and tech stack directly.

---

## What HackBench Does NOT Do

- **NO Winner/Loser Predictions**: The system strictly **NEVER** predicts who will win, computes win probabilities, or generates placement odds.
- **NO Hallucinated Metrics**: Lines of code, framework detections, and API routes are derived strictly from deterministic static parsing. Missing repos are marked `not_found` with zero LOC.
- **NO Code Execution**: Repositories are inspected as untrusted static data; HackBench never runs `npm install`, `pip install`, shell scripts, or container builds on user code.
- **NO Post-Hoc Rationalization**: Evaluator results that conflict with judges' decisions are preserved as `evidence_conflicts_with_outcome` rather than adjusted to fit official outcomes.

---

## 3-Layer AI Architecture

HackBench avoids expensive, slow, and ungrounded LLM generation for routine decisions by employing a three-layer evaluation architecture:

```
Participant / Web UI / CLI
            ↓
  POST /api/analyze
            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Deterministic Software Engine                      │
│ - Verified LOC, AST framework detection, API routes         │
│ - Automated test suite detection (pytest, jest, vitest)     │
│ - Git commit crunch ratio & stage focus                     │
│ - Live HTTP deployment reachability check (status, latency) │
│ - Documented judging criteria lookup                        │
└─────────────────────────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Jev System One Decision Engine                     │
│ - Fast, structured, probabilistic classification            │
│ - Single shared-state batch evaluation across 9 rubrics     │
│ - Question Primitives: Choice, Score, Noul                  │
│ - Explicit rubric anchors (Very Weak -> Very Strong)        │
└─────────────────────────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────────────────────────┐
│ Confidence & Uncertainty Gate (Threshold = 0.80)            │
│ - High Confidence (≥ 0.80) → Accept Jev result directly     │
│ - Low Confidence / Ambiguous (< 0.80) → Route to Gemini     │
│ - Missing Evidence Boundary → Deterministic insufficient    │
└─────────────────────────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Gemini Synthesis & Fallback Engine                 │
│ - Generative synthesis of structured executive summary      │
│ - Observable strengths, gaps, and top 3 prioritized actions │
│ - Content inside <PROJECT_EVIDENCE> treated as untrusted    │
└─────────────────────────────────────────────────────────────┘
            ↓
  Structured JSON Report → Rendered Results Page
```

---

## Quickstart

### Prerequisites
- Python 3.12+
- Node.js 18+ and npm
- [uv](https://github.com/astral-sh/uv) (fast Python package installer)

### 1. Clone & Setup Backend
```bash
git clone https://github.com/Aaryan1524/ShellhacksHackathonAnalysis.git
cd ShellhacksHackathonAnalysis

# Install python dependencies with uv
uv sync

# Configure environment variables
cp .env.example .env
```

### 2. Configure Environment Variables (`.env`)
```bash
# Layer 2: Jev System One Decision Engine
JEV_API_KEY=your_jev_api_key_here
JEV_MODEL=jev-latest
JEV_CONFIDENCE_THRESHOLD=0.80

# Layer 3: Gemini Synthesis
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# Backend & Web
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
FRONTEND_URL=http://localhost:3000
```

*(Note: If API keys are omitted, HackBench falls back to calibrated deterministic offline evaluators.)*

### 3. Run the Backend API Server
```bash
uv run uvicorn hackbench.api.server:app --host 0.0.0.0 --port 8000 --reload
```
Health endpoint: `http://localhost:8000/health`

### 4. Run the Web Application
```bash
cd web
npm install
npm run dev
```
Open `http://localhost:3000` in your browser.

---

## CLI Usage

The CLI (`hackbench`) provides end-to-end command-line tools for researchers and developers:

```bash
# Benchmark a single candidate project (local path or Git URL) for ShellHacks 2026:
hackbench benchmark-project ./my-hackathon-repo \
  --name "Project Name" \
  --tagline "One-line pitch" \
  --what "Summary of project" \
  --tags "React, FastAPI, PostgreSQL" \
  --deploy "https://my-app.vercel.app"

# Ingest hackathon event rules and criteria:
hackbench ingest-event https://shellhacks2025.devpost.com/

# Collect project gallery submissions (quarantining awards):
hackbench collect-projects shellhacks2025:2025 --all

# Clone public repositories and extract deterministic metrics:
hackbench collect-repos shellhacks2025:2025 --all

# Run multi-pass blind evaluations (sealed with SHA256):
hackbench evaluate-blind shellhacks2025:2025

# Unseal official outcomes:
hackbench reveal-results shellhacks2025:2025

# Run comparative forensics (mismatches and strong non-winners):
hackbench analyze shellhacks2025:2025

# Generate all 14 markdown forensic reports:
hackbench report shellhacks2025:2025

# Or run the entire pipeline end-to-end in one command:
hackbench run https://shellhacks2025.devpost.com/ --all
```

---

## Running Tests

All unit and integration tests are automated via pytest:

```bash
uv run pytest tests/ -v
```

Test coverage includes:
- **Jev Engine**: Choice, Score, Noul parsing, multi-question batching, cache invalidation, and fallback routing.
- **Security & SSRF**: Rejection of localhost, RFC1918 private IPs, cloud metadata (`169.254.169.254`), and file:// URLs.
- **Prompt Injection**: Sanitization of closing XML tags and delimited untrusted text blocks.
- **Core Invariants**: Verification of sealed outcomes, immutability of frozen blind evaluations, and absence of win probabilities.

---

## Jev Validation Report

Jev classifications have been validated against the historical ShellHacks dataset. View the detailed empirical report at:
[`reports/jev_validation.md`](reports/jev_validation.md).

Key validation findings:
- **Adjacent + Exact Agreement**: Exceeds **88%** across primary judge-facing clarity dimensions.
- **Confidence Calibration**: Mean confidence on agreements is **0.86**, dropping to **0.68** on disagreements, proving effective routing.

---

## Deployment Instructions

### Option 1: Docker Container Deployment (Railway, Render, Fly.io, Cloud Run)
Build and run the production backend container:

```bash
# Build Docker image
docker build -t hackbench-api .

# Run container
docker run -p 8000:8000 \
  -e JEV_API_KEY="your_key" \
  -e GEMINI_API_KEY="your_key" \
  hackbench-api
```

### Option 2: Vercel Frontend Deployment
Deploy the `web/` directory directly to Vercel:
1. Set the root directory in Vercel to `web`.
2. Configure the environment variable `BACKEND_URL` to point to your deployed backend API URL.

---

## Security Considerations

1. **SSRF Safeguards**: All external URL fetches undergo DNS resolution and IP validation before connection. Localhost (`127.0.0.0/8`, `::1`), private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), and cloud metadata (`169.254.169.254`) are strictly blocked.
2. **Untrusted Code Sandboxing**: Repositories are inspected solely via static file reading and AST parsing. User code is never executed, dependencies are never installed, and package scripts are never triggered.
3. **Prompt Injection Boundaries**: All project text (README, descriptions, comments) is enclosed within `<PROJECT_EVIDENCE>` tags with explicit model instructions to treat content as untrusted evidence.
4. **Secret Isolation**: `JEV_API_KEY` and `GEMINI_API_KEY` remain strictly server-side and are never exposed in frontend bundles or logs.

---

## Adding Another Hackathon

To analyze a new hackathon (e.g. `hackmit2025` or `calhacks2025`):
1. Ingest event rules and prizes:
   ```bash
   hackbench ingest-event https://hackmit2025.devpost.com/
   ```
2. Run the end-to-end pipeline:
   ```bash
   hackbench run https://hackmit2025.devpost.com/ --all
   ```
All historical datasets, SQLite/DuckDB records, and markdown reports will be automatically isolated in `data/processed/<slug>/<year>/` and `reports/<slug>_<year>/`.