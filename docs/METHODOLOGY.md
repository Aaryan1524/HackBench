# Hackathon Forensics: End-to-End Methodology

## 1. System Architecture & Pipeline

Hackathon Forensics (`hackbench`) is designed as a modular, repeatable analytical pipeline that evaluates hackathon submissions completely blind before examining official judging outcomes.

```
       [ Public Hackathon URL ]
                  │
                  ▼
         ┌──────────────────┐
         │ Event Ingestion  │ ──► data/raw/<event>/event.html
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │ Project Discovery│ ──► data/raw/<event>/projects/<id>.html
         └────────┬─────────┘     data/raw/<event>/gallery_page_*.html
                  │
                  ▼
         ┌──────────────────┐
         │ Outcome Staging  │ ──► data/raw/<event>/outcomes_raw.json
         │ (STRICTLY SEALED)│     (Kept in quarantine until Phase 6)
         └──────────────────┘
                  │
                  ▼
         ┌──────────────────┐
         │ Repo Collection  │ ──► data/raw/<event>/repos/<project_id>/
         │ & Git Analytics  │     Deterministic Metrics Extraction
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │ Blind Bundler    │ ──► data/processed/<event>/blind_bundles/<id>.json
         │ (Sanitization)   │     Cryptographic SHA256 Sealing
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │ Blind Multi-Pass │ ──► data/processed/<event>/blind_evaluations.jsonl
         │ Evaluation (AI)  │     (Evaluators have 0 knowledge of outcomes)
         └────────┬─────────┘
                  │
                  ▼
    ==============================
    [ HASH INTEGRITY VERIFICATION ]
    ==============================
                  │
                  ▼
         ┌──────────────────┐
         │ Outcome Reveal   │ ──► Unseal outcomes_raw.json
         │ (Stage B)        │     Join with Blind Evaluations
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │ Mismatch & Cohort│ ──► Winner vs Non-Winner Comparisons
         │ Analysis         │     Strong Non-Winner Cohort Analysis
         └────────┬─────────┘     Counterfactual & Base-Rate Audits
                  │
                  ▼
         ┌──────────────────┐
         │ Report Generator │ ──► reports/<event>/*.md
         │                  │     Structured JSON / DuckDB
         └──────────────────┘
```

---

## 2. Data Collection & Provenance

### Event-Level Metadata
From the event homepage and rules pages:
- Official Hackathon Name, Year, Dates, Location, Organizer
- Published Judging Criteria & Category Descriptions
- Sponsor Challenges & Specific API / Technology Requirements
- Eligibility Rules & Submission Guidelines
- Total Registrations / Submissions / Projects Count

### Project-Level Metadata
From Devpost gallery and project detail pages:
- Name, Tagline, Full Description (Problem, Inspiration, What it does, How it was built, Challenges, Accomplishments, Lessons learned, Future plans)
- Built-with Tech Tags
- Team Roster & Team Size
- Demonstration Assets: Demo video URLs (YouTube, Vimeo, Loom, Devpost video), Live Deployment URLs, Presentation Slide URLs
- Code Repositories: GitHub, GitLab, Bitbucket URLs
- Submission Timestamps

### Provenance Tracking
Every record retains its source URL, extraction timestamp, content hash, and extraction selector. Unsupported claims are flagged with `confidence < 0.5`.

---

## 3. Deterministic Repository & Git Analytics

Code repositories provide objective ground truth regarding actual software development during the hackathon window.

### Measured Features:
1. **Repository Existence & Accessibility**: Public, Private, 404, or Missing.
2. **Commit Timeline**:
   - Total commits, total contributors.
   - Commits within the hackathon window (e.g. ShellHacks 2025: Sept 26 18:00 - Sept 28 12:00 EDT).
   - Time of first commit, time of last commit, time until submission.
   - Sequence reconstruction: When was the core workflow added? When was UI work committed? Did massive rewrites happen near the deadline?
3. **Codebase Geometry**:
   - File counts, directory structure depth.
   - Approximate Lines of Code (LOC) grouped by primary language.
   - File extensions inventory.
4. **Stack & Dependency Parsing**:
   - Frontend: React, Next.js, Vue, Svelte, Angular, Flutter, Tailwind, etc.
   - Backend: FastAPI, Flask, Express, Django, NestJS, Go, Spring, etc.
   - Database / BaaS: PostgreSQL, MongoDB, SQLite, Supabase, Firebase, Redis, Prisma, etc.
   - AI / ML: PyTorch, TensorFlow, Scikit-learn, LangChain, LlamaIndex, Transformers, HuggingFace, etc.
   - Model Providers & APIs: OpenAI, Anthropic, Gemini, Groq, Cohere, ElevenLabs, Deepgram, etc.
   - Cloud & DevOps: AWS, GCP, Azure, Vercel, Dockerfile, docker-compose, CI workflows.
   - Hardware: Arduino, Raspberry Pi, ESP32, Serial communications, Sensors.
5. **Engineering Rigor Indicators**:
   - Test suites (pytest, jest, vitest, unittest) & test files count.
   - Continuous Integration configurations (`.github/workflows/`).
   - Configuration templates (`.env.example`).
   - API endpoints declared in routing files.
   - Database schema files and migration scripts.
   - Hardcoded / Mock data presence (regex detection for `"mock"`, `"fake"`, `"test_data"`, static JSON returns).
   - Unfinished code markers (`TODO`, `FIXME`, `pass`, `unimplemented!()`).
   - Scaffolding ratio: generated boilerplate vs custom domain code.
6. **Deployment Verification**:
   - HTTP ping to claimed live deployment URL (status code, latency, headers).

---

## 4. Blind Sanitization & Integrity Sealing

To ensure zero outcome contamination:
1. All Devpost winner ribbons, award badges, prize titles, and winner announcements are quarantined in `outcomes_raw.json`.
2. Project descriptions are sanitized via regex to remove explicit post-hackathon winner edits (e.g., "Winner of 1st place overall!").
3. A `BlindProjectBundle` is generated for each project containing:
   - Sanitized project details
   - Deterministic repository metrics
   - Verified integration signals
   - Git timeline facts
   - Demo metadata
4. The bundle is hashed (`sha256(bundle)`) and recorded in an immutable ledger.

---

## 5. Multi-Pass Blind Evaluation

Blind evaluations are conducted across the 17 dimensions defined in `docs/EVALUATION_RUBRIC.md`.
- Evaluators evaluate solely the `BlindProjectBundle`.
- Evaluators must answer:
  1. What problem is being solved?
  2. Who is the user?
  3. What is the core insight?
  4. What is the primary workflow?
  5. What is technically difficult?
  6. What works vs. what appears incomplete?
  7. What evidence supports completion?
  8. What is the likely demo "wow moment"?
  9. What is memorable vs. generic?
  10. What technology is substantive vs. ornamental?
  11. What claims cannot be verified?
  12. Strongest and weakest aspects?
  13. Overall assessment confidence?
- Run at least 3 passes per project. Compute inter-evaluator variance. High variance flags the result as unstable.

---

## 6. Outcome Reveal & Comparative Analysis

Once all blind evaluations are saved and cryptographically verified, the sealed outcomes are attached.

### Cohort Comparisons:
1. **Overall Winners vs. Non-Winners**
2. **Sponsor Winners vs. Non-Winners**
3. **Overall Winners vs. Sponsor Winners**
4. **Winners vs. Strong Non-Winners** (Projects scoring $\ge 3$ on Completion, $\ge 3$ on Technical Depth, with functional repos/demos)
5. **Completed Winners vs. Completed Non-Winners**
6. **High-Technical-Depth Winners vs. High-Technical-Depth Non-Winners**

### Statistical Metrics:
- Proportions and base rates.
- Effect sizes (Cohen’s $d$).
- Odds ratios.
- All framed descriptively with explicit sample sizes.

---

## 7. Mismatch Classification Taxonomy

For every winning project, we evaluate the degree of alignment between the blind assessment and the official award:

1. **`evidence_strongly_supports_outcome`**:
   The winner objectively outperforms comparable non-winners across core dimensions (Completion, Technical Depth, Product Coherence, Demo).
2. **`evidence_moderately_supports_outcome`**:
   The winner has identifiable strengths, though several non-winning projects achieved comparable public evidence quality.
3. **`evidence_does_not_clearly_distinguish_winner`**:
   The winner is indistinguishable in public evidence from a substantial pool of non-winning projects.
4. **`evidence_conflicts_with_outcome`**:
   One or more comparable non-winners appear substantially stronger on verified technical, architectural, and product completion metrics, while the winner exhibits significant gaps.
   *Invariant*: In this case, both facts are preserved without rationalization.
5. **`insufficient_evidence`**:
   Public evidence (missing repo, broken demo, sparse description) is inadequate to evaluate the project's real-world merit.

---

## 8. Counterfactual & Bias Audits

To prevent narrative bias, the engine runs automated sanity checks:
- **Base-Rate Audit**: If 75% of winners use LLMs, but 73% of all submissions used LLMs, the effect is near zero.
- **Complexity vs. Simplicity**: Identify the simplest project that won, and the most complex project that did not win.
- **Sponsor Cannibalization**: Identify projects that excelled at sponsor prompts but were passed over for general awards.
