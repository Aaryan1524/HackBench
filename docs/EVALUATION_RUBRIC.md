# Hackathon Forensics: Evaluation Rubric & Measurement Anchors

To eliminate "vibes" and prevent arbitrary numerical scoring, this rubric establishes explicit, observable criteria for all 17 dimensions evaluated during blind analysis.

Every evaluation must output both an ordinal classification and an integer score (0–5) rooted in these observable criteria.

---

## The 17 Evaluation Dimensions

### 1. Problem Clarity
Can a reviewer understand the problem being addressed quickly without deciphering buzzwords?
- **0 (Very Weak)**: Incoherent problem statement; purely a list of buzzwords; problem is unstated.
- **1 (Weak)**: Extremely vague problem (e.g. "people have stress"); hard to tell what pain point is being targeted.
- **2 (Moderate)**: Understandable problem area, but poorly scoped or presented generically.
- **3 (Strong)**: Clear, identifiable problem statement described in concrete, everyday terms.
- **4 (Very Strong)**: Crisp, compelling problem statement with tangible context and immediate lucidity.
- **5 (Exemplary)**: Masterful articulation; defines the exact bottleneck, root cause, or failure mode clearly in under 30 seconds.

### 2. User Specificity
Is there a recognizable, well-defined target user persona?
- **0 (Very Weak)**: No target user identified ("for everyone in the world").
- **1 (Weak)**: Overly broad category with conflicting user needs (e.g. "enterprises and toddlers").
- **2 (Moderate)**: Broad persona identified (e.g. "college students", "doctors") without role nuance.
- **3 (Strong)**: Specific target role identified with identifiable workflow constraints (e.g. "solo emergency room triage nurses").
- **4 (Very Strong)**: Distinct user segment with detailed day-in-the-life empathy and tailored workflow touchpoints.
- **5 (Exemplary)**: Hyper-targeted persona with documented user friction, niche domain requirements, and tailored UX constraints.

### 3. Problem Importance
Does the problem address a consequential, painful, or meaningful bottleneck?
- **0 (Very Weak)**: Trivial or artificial problem manufactured solely to showcase an API.
- **1 (Weak)**: Minor convenience issue with minimal real-world friction.
- **2 (Moderate)**: Noticeable everyday annoyance or recreational optimization.
- **3 (Strong)**: Meaningful operational, financial, educational, or logistical problem with measurable friction.
- **4 (Very Strong)**: High-stakes or severe bottleneck affecting critical workflows, safety, cost, or accessibility.
- **5 (Exemplary)**: Critical, transformative challenge with substantial systemic impact or acute human necessity.

### 4. Originality & Differentiated Concept
Is the core concept differentiated from standard hackathon tropes (e.g. generic chat-with-PDF, another recipe recommender)?
- **0 (Very Weak)**: Carbon copy of standard tutorial or hackathon cliché with zero novel twist.
- **1 (Weak)**: Generic application with superficial thematic dressing (e.g. standard ChatGPT wrapper for study notes).
- **2 (Moderate)**: Familiar concept with one or two thoughtful, unconventional features or mechanics.
- **3 (Strong)**: Distinct angle or novel synthesis of two disparate domains; fresh take on an existing category.
- **4 (Very Strong)**: Highly creative, unexpected framing; tackles a problem rarely explored in hackathon environments.
- **5 (Exemplary)**: Radical paradigm shift; groundbreaking product insight that challenges conventional assumptions.

### 5. Product Coherence
Do the features form a unified, single, logical workflow rather than a disjointed bag of APIs?
- **0 (Very Weak)**: Fragmented assortment of disconnected demos on separate pages with no linking narrative.
- **1 (Weak)**: Loose collection of features sharing a nav bar but lacking a coherent end-to-end data flow.
- **2 (Moderate)**: Clear primary feature, but multiple secondary features feel tacked on or unintegrated.
- **3 (Strong)**: Logical end-to-end flow where step A cleanly feeds into step B and step C.
- **4 (Very Strong)**: Tight, polished workflow where every single feature directly reinforces the core value proposition.
- **5 (Exemplary)**: Seamless, frictionless product harmony; every interaction feels deliberate, necessary, and unified.

### 6. Scope Discipline
Was the project scoped realistically enough to be executed with high fidelity within a 36-hour window?
- **0 (Very Weak)**: Grossly over-scoped fantasy platform with dozens of empty stubs, 404 links, and unfinished screens.
- **1 (Weak)**: Overambitious scope resulting in widespread shallow, half-broken implementations.
- **2 (Moderate)**: Ambitious scope with several compromised or non-functioning edges.
- **3 (Strong)**: Well-bounded scope; focused on a tight core with clean execution and few broken paths.
- **4 (Very Strong)**: Disciplined scope management; intentionally cut non-essential features to achieve high polish.
- **5 (Exemplary)**: Flawless surgical scoping; delivered a complete, high-fidelity experience without a single loose end.

### 7. Completion (Execution Anchor)
Does the evidence show a working, end-to-end software pipeline?
- **0 (None)**: No working workflow visible; repository is empty, broken, or contains only non-functional templates.
- **1 (Fragmentary)**: Isolated fragments or static UI mockups only; core data pipeline does not function.
- **2 (Partial)**: Partial workflow functions, but missing a critical intermediate or final step (e.g. inputs accept data but output is hardcoded).
- **3 (Functional Core)**: Primary end-to-end workflow functions from input to output, though edge cases fail or secondary features are stubbed.
- **4 (Complete Primary Workflow)**: Robust, fully functional primary workflow verifiable in code and demo without mock dependencies.
- **5 (Complete & Robust)**: Complete primary workflow plus error handling, edge-case coverage, and functional supporting features.

### 8. Technical Depth
Does the implementation demonstrate meaningful engineering beyond basic scaffolding and CRUD boilerplate?
- **0 (Trivial)**: Static HTML/CSS or unedited boilerplate generated directly from starter templates.
- **1 (Basic)**: Simple CRUD or single API pass-through with minimal custom logic (e.g. form sends prompt directly to OpenAI).
- **2 (Moderate)**: Standard multi-tier web application (database schema, authenticated API routes, client state management).
- **3 (Substantial)**: Custom algorithms, multi-stage data processing pipeline, non-trivial state synchronization, or hardware-software bridging.
- **4 (Advanced)**: Complex distributed architecture, custom computer vision/ML pipeline, real-time protocol handling, or intricate low-level systems logic.
- **5 (Exceptional)**: Remarkable engineering feat for a hackathon; custom model fine-tuning/architecture, kernel-level/hardware integration, or algorithmic novelty.

### 9. Technical Appropriateness
Is the technical stack chosen genuinely appropriate for the problem, or used merely to check buzzword boxes?
- **0 (Inappropriate)**: Absurd mismatch (e.g. using a blockchain to store local form state).
- **1 (Poor)**: Over-engineered or ill-suited tools that impede performance and add needless complexity.
- **2 (Acceptable)**: Workable stack, but suboptimal or exhibits obvious signs of resume-driven development.
- **3 (Sound)**: Pragmatic, well-suited stack that solves the core problem effectively.
- **4 (Optimal)**: High synergy between problem constraints and tool choices; efficient, scalable, and lean.
- **5 (Masterful)**: Ingenious architectural choices that solve difficult constraints with elegant simplicity.

### 10. Integration Depth
Are third-party services, APIs, hardware, or models deeply integrated or merely ornamental?
- **0 (None/Ornamental)**: Mentioned in README or tags but zero code references found in repository.
- **1 (Superficial)**: Single trivial call (e.g. default curl request or standard client import with 2 lines of code).
- **2 (Basic)**: Standard API interaction with basic response parsing.
- **3 (Meaningful)**: Multi-endpoint utilization with bidirectional data exchange, state handling, and error trapping.
- **4 (Deep)**: Complex orchestration, webhooks/event streaming, custom parameter optimization, or multi-service pipelines.
- **5 (Exemplary)**: Full-stack symbiosis; custom extensions, real-time bi-directional pipeline, or hybrid edge-cloud coordination.

### 11. AI Necessity
If artificial intelligence / machine learning is utilized, does it fundamentally unlock the product value?
- **0 (Gratuitous / None)**: Pure gimmick where deterministic logic or a regex would be faster, cheaper, and more reliable; or AI is absent.
- **1 (Superficial)**: Standard LLM wrapper adding little value beyond basic text paraphrasing.
- **2 (Helpful)**: AI provides nice-to-have enhancements (e.g. automated tagging) but core value exists without it.
- **3 (Substantive)**: AI is an integral component; the product solves the problem significantly better with ML than without.
- **4 (Essential)**: Core value proposition is impossible without machine intelligence; models handle complex unstructured reasoning.
- **5 (Pioneering)**: Sophisticated compound AI system (multi-agent, hybrid RAG, multimodal reasoning) that defines the entire breakthrough.

### 12. Demo Strength
Does the demo communicate the user journey, problem, and solution with immediate impact?
- **0 (Non-existent / Broken)**: No demo available, or video is private/unplayable.
- **1 (Confusing / Static)**: Unclear voiceover, slide-only presentation with no live software, or unreadable screen recording.
- **2 (Pedestrian)**: Standard feature walkthrough; slow pacing; fails to highlight what makes the project distinctive.
- **3 (Clear & Engaging)**: Crisp explanation of problem and live software demonstration within the first 60 seconds.
- **4 (Compelling)**: High energy, well-structured user journey, clearly proves live working software, memorable pacing.
- **5 (Electrifying)**: Unforgettable narrative arc, flawless live demonstration of technical difficulty, immediate emotional resonance.

### 13. Design & User Experience (UX)
Does the visual design and interaction model enhance user understanding and workflow speed?
- **0 (Dysfunctional)**: Unusable UI; broken layouts, overlapping text, unreadable contrast.
- **1 (Raw Prototype)**: Bare unstyled HTML or basic bootstrap default with awkward ergonomics.
- **2 (Functional)**: Clean but generic template; adequate usability without aesthetic refinement.
- **3 (Polished)**: Thoughtful layout, clear visual hierarchy, intuitive ergonomics, cohesive styling.
- **4 (Delightful)**: High craft; smooth transitions, responsive micro-interactions, accessible typography, tailored domain aesthetics.
- **5 (Studio Quality)**: World-class design execution rivaling venture-backed products; extraordinary attention to detail.

### 14. Practicality & Real-World Viability
Could this project plausibly be deployed or continued as an open-source or commercial utility?
- **0 (Impractical)**: Concept is fundamentally unworkable, violates physics, or creates unacceptable legal/safety hazards.
- **1 (Unlikely)**: Enormous barriers to adoption, prohibitive operational costs, or negligible incentives for users.
- **2 (Possible with Major Pivots)**: Core idea has merit, but requires complete rewriting and different economics to function.
- **3 (Plausible)**: Viable utility that could realistically serve beta testers with moderate engineering hardening.
- **4 (High Viability)**: Clear path to ongoing utility, realistic economic model, immediate practical appeal.
- **5 (Production-Ready Concept)**: Instantly deployable; addresses an urgent real-world need with defensible viability.

### 15. Memorability & "Wow" Factor
Is there a singular memorable hook, interaction, visual, or result that stands out in a judge's memory after seeing 50 projects?
- **0 (Forgettable)**: Indistinguishable from the background noise of standard projects.
- **1 (Low)**: Standard functionality with no standout moments.
- **2 (Noticeable)**: One interesting graphic, clever quip, or neat minor feature.
- **3 (Memorable)**: Strong, distinct visual or technical hook that lingers in the mind.
- **4 (Striking)**: Unusually clever mechanic or visceral live demo moment that commands attention.
- **5 (Legendary)**: A jaw-dropping hackathon moment that everyone at the venue talks about.

### 16. Story Clarity
Does the narrative arc (Problem -> Approach -> Execution -> Impact) form an airtight logical argument?
- **0 (Incoherent)**: Scattered thoughts; cannot tell why the project was built or how components connect.
- **1 (Muddled)**: Skips critical context, jumps into technical weeds before establishing why it matters.
- **2 (Adequate)**: Basic sequential structure, but lacks dramatic tension or compelling conclusion.
- **3 (Well-Structured)**: Clear, logical narrative arc that guides the reviewer smoothly from pain point to outcome.
- **4 (Persuasive)**: Highly compelling narrative; anticipates reviewer questions and answers them proactively with data.
- **5 (Masterclass)**: Flawless storytelling; builds undeniable urgency and proves technical victory with effortless lucidity.

### 17. Sponsor Alignment (Track/Sponsor Specific)
How directly and meaningfully does the project fulfill the sponsor's published prompt and technical requirements?
- **0 (No Alignment)**: Sponsor tool mentioned in tags but nowhere in code, or prompt completely disregarded.
- **1 (Nominal)**: Superficial token usage (e.g. calling sponsor API once to fetch dummy data).
- **2 (Moderate)**: Uses sponsor technology legitimately, but in a routine, generic manner.
- **3 (Strong)**: Core workflow directly leverages key sponsor capabilities to solve the designated challenge.
- **4 (Exceptional)**: Pushes sponsor technology to its limits, integrating advanced SDK features and addressing sponsor goals directly.
- **5 (Exemplary)**: Flagship showcase; solves the sponsor's exact challenge with unprecedented ingenuity and depth.

---

## Multi-Pass Evaluation & Disagreement Thresholds

For every project:
1. Conduct at least 3 independent blind evaluations.
2. For each dimension $d$, compute:
   $$\mu_d = \frac{1}{N} \sum_{i=1}^N x_{i,d}, \quad \sigma_d = \sqrt{\frac{1}{N}\sum_{i=1}^N (x_{i,d} - \mu_d)^2}$$
3. **Disagreement Alert**: If for any core dimension (Completion, Technical Depth, Originality), the spread $\max(x_d) - \min(x_d) \ge 2.0$, record the dimension as disputed.
4. If $\ge 3$ dimensions are disputed, classify the overall project evaluation as:
   `"Low evaluator agreement — conclusion unstable"`
