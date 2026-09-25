# Hackathon Forensics: Core Invariants & Non-Negotiable Rules

This document outlines the strict methodological and operational invariants of **Hackathon Forensics**. Every contributor, subagent, automated script, and LLM evaluator MUST adhere to these rules without exception.

---

## 1. The Separation Invariant: Blind First, Results Second

The core principle of Hackathon Forensics is logical, temporal, and physical separation between:
- **Stage A: Blind Project Evaluation**
- **Stage B: Outcome-Aware Comparative Analysis**

```
+-----------------------------------------------------------------------------------+
| STAGE A: BLIND PROJECT EVALUATION                                                 |
| - Inspects ONLY public evidence (Repo, Git history, Readme, Devpost text, Demo)  |
| - Zero knowledge of awards, winners, finalist status, placements, or sponsor pins|
| - Evaluates all projects on an identical 17-dimension rubric                     |
| - Stores immutable blind evaluation record with SHA256 integrity hash             |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| INTEGRITY SEAL / HASH VERIFICATION                                                |
| - Confirms blind evaluation cannot be modified post-reveal                        |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| STAGE B: OUTCOME COMPARISON & FORENSICS                                           |
| - Unseals official results (Overall winners, Sponsor prizes, Track awards)        |
| - Compares blind assessments vs real-world outcomes                              |
| - Identifies matches, mismatches, anomalies, and strong non-winners               |
| - NEVER mutates or overrides Stage A evaluations                                  |
+-----------------------------------------------------------------------------------+
```

### Invariant Rules:
1. **Zero Outcome Leakage into Stage A**:
   - Blind project bundles must be programmatically scrubbed of any winner ribbons, award badges, prize titles, or post-hackathon congratulatory edits before being passed to any blind evaluator or scoring system.
   - Pydantic models for blind evaluation input must omit all outcome fields by design.
2. **Permanent Immutability of Stage A**:
   - Once a blind evaluation is completed and recorded, it is cryptographically hashed and sealed.
   - **NEVER** re-run, regenerate, or edit a blind evaluation because the official result conflicts with the blind score.
   - Any script or model that attempts to back-propagate an official result into a blind score violates this invariant and must be rejected.

---

## 2. The Anti-Justification Rule (Never Rationalize Judges' Decisions)

Official hackathon results are ground truth only for **what judges selected on that day**, NOT ground truth for objective software quality, technical depth, or completeness.

- **Prohibition**: You must NEVER manipulate analysis, adjust weighting, or re-interpret evidence to rationalize an official result.
- **Preservation of Disagreement**: If a winning project scored lower on code completeness, architecture, and technical depth than a non-winning project during blind evaluation, that disagreement must be explicitly highlighted as an outcome mismatch:
  `evidence_conflicts_with_outcome`
- **Candidate Explanations as Possibilities Only**: When investigating why an outcome differed from the blind evidence, formulate hypotheses (e.g., live stage presence, judge background, unrecorded sponsor interactions, networking) strictly as *unverified possibilities*, never as asserted facts.

---

## 3. Provenance & Anti-Hallucination Invariant

Every claim, extracted metric, and interpretive judgment must carry strict source provenance.

### Provenance Structure:
```json
{
  "claim": "Repository implements custom WebSockets communication protocol",
  "evidence_type": "repository",
  "source": "https://github.com/team/project/blob/main/server/ws.py",
  "location": "lines 14-85",
  "confidence": 0.95
}
```

### Invariant Rules:
1. **Distinguish Claimed vs. Verified**:
   - A claim in a README or Devpost ("We trained a custom transformer") is classified as `claimed`.
   - Only inspection of code, model weights, training scripts, or commit history verifies it as `verified`.
2. **No Hallucination of Completeness**:
   - If a repository is empty, 404s, or private, record `repository_status: unavailable`. Do NOT infer project quality from the description alone without noting the high uncertainty.
   - If a demo video is inaccessible, record `demo_status: unavailable`.
3. **Evidence-Bounded Confidence**:
   - High confidence (0.8 - 1.0) requires multi-source verification (e.g., repo code + git history + live deployment).
   - Low confidence (< 0.5) must be explicitly flagged in all generated reports.

---

## 4. No Fake Precision (Rubric-Anchored Scoring)

Avoid arbitrary fractional scores (e.g., "Originality: 8.43 / 10").

### Invariant Rules:
1. Every numerical score (0 to 5) must be tied to an explicit, documented rubric anchor (see `EVALUATION_RUBRIC.md`).
2. Dual Representation: All dimensions must be stored with both:
   - **Ordinal Label**: `very_weak`, `weak`, `moderate`, `strong`, `very_strong`
   - **Rubric-Anchored Integer**: `0`, `1`, `2`, `3`, `4`, `5`
   - **Explicit Justification & Evidence Citations**
3. Multi-Pass Evaluator Agreement:
   - Run at least 3 independent evaluation passes.
   - Report mean absolute deviation and variance.
   - If evaluators diverge significantly on key dimensions, label the finding:
     `"Low evaluator agreement — conclusion unstable"`
     Do not mask disagreement with artificial mathematical smoothing.

---

## 5. Award Specificity (Categorical Separation)

Do not treat all hackathon awards as equivalent.

### Award Categories:
1. `Best Overall` (1st, 2nd, 3rd place)
2. `Sponsor Challenge` (Specific company prize based on their proprietary API or prompt)
3. `Track Prize` (e.g., Best Healthcare, Best FinTech, Best Game)
4. `Beginner / First-Time Hacker`
5. `People's Choice / Community Vote`
6. `Specialty / Hardware Prize`

### Invariant Rule:
- Comparative analysis must evaluate each category independently.
- A sponsor prize winner cannot be analyzed using the same criteria as a Best Overall winner without explicitly isolating the sponsor alignment dimension.

---

## 6. Strong Non-Winner Cohort Invariant

The project discovery and evaluation pipeline must include the entire accessible population of submissions (winners and non-winners alike).

### Invariant Rules:
1. Analysis without non-winners is methodologically invalid.
2. The system must automatically identify the **Strong Non-Winner Cohort** based strictly on blind criteria:
   - Functional primary workflow
   - Verifiable repository engineering
   - Complete or near-complete execution (Score >= 3)
   - High blind evaluator agreement
3. Compare winners against this cohort to answer: *“Among projects that were actually built and functional, what distinguished winners?”*

---

## 7. Counterfactual & Base-Rate Checking

Before accepting any causal or correlative finding (e.g., "AI projects win more often"), the system must execute counterfactual and base-rate checks:
- What was the base rate of this characteristic across all non-winners?
- Are there counterexamples of non-winners possessing the same trait at a higher quality?
- Are there counterexamples of winners succeeding completely without this trait?
- Phrase all statistical findings descriptively (e.g., "X appeared in 68% of winners vs 24% of non-winners") and never causally ("Using X caused them to win").
