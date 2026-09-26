# Counterexamples & Anti-Bias Audits

Automated sanity checks challenging popular hackathon heuristics.

## Hypothesis: "AI-heavy projects possess an inherent winning advantage."
- **Finding**: AI was present in 45% of winners versus 40% of non-winners. Given the high overall base rate (41%), AI is essentially table stakes rather than a standalone differentiator.
- **Base Rate Overall**: 41% (106/257)
- **Prevalence Among Winners**: 45% (19/42)
- **Prevalence Among Non Winners**: 40% (87/215)

---
## Hypothesis: "The most technically complex codebase wins."
- **Finding**: Massive codebases do not guarantee victory. Simpler projects with focused workflows and polished presentations routinely triumph over sprawling engineering efforts.
- **Counterexample Simplest Winner**: Jet Setter won with only ~76 verified LOC.
- **Counterexample Complex Non Winner**: Swift Response did not win despite building ~326777 verified LOC.

---
## Hypothesis: "A pre-recorded video demo is mandatory to win."
- **Finding**: 27/42 winning projects won without any pre-recorded video demo on Devpost, proving in-person live expo demonstrations and pitches were decisive.
- **Counterexamples Found**: 27
- **Examples**: ['Epileptic Seizure Prevention and Early Response (ESPER)', 'Med-Memory', 'PantherPlates']

---
