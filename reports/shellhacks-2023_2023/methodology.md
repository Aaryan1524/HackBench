# Hackathon Forensics: Analytical Methodology & Integrity Guarantees

## 1. Logical Stage Separation
The analysis pipeline enforces a strict temporal and logical boundary:
- **Stage A (Blind Project Analysis)**: Evaluates project evidence (code, commits, tech stack, documentation, demo) without access to winner badges, placement, or award titles.
- **Stage B (Outcome-Aware Forensics)**: Unseals official results only after blind evaluations are sealed with SHA256 cryptographic hashes.

## 2. Invariant: Disagreement Preservation
Under no circumstances are blind scores edited post-reveal to rationalize official judging choices. When public evidence conflicts with an official award, the finding is explicitly cataloged as `evidence_conflicts_with_outcome`.

## 3. Rubric & Multi-Pass Evaluation
Every project is evaluated across 17 distinct dimensions using explicit rubric anchors (0 to 5) across at least 3 independent passes to calculate evaluator agreement and flag disputed dimensions.
