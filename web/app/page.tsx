"use client";

import React, { useState, useEffect } from "react";

// Types matching the HackBench backend API
interface Strength {
  title: string;
  evidence: string;
  historical_context: string;
}

interface Gap {
  title: string;
  evidence: string;
  historical_context: string;
}

interface NextAction {
  priority: number;
  action: string;
  reason: string;
}

interface DimensionComparison {
  you: string;
  historical_overall_winners: string;
  strong_non_winners: string;
  interpretation: string;
}

interface AnalysisResult {
  analysis_id: string;
  project: {
    name: string;
    tagline: string;
    github_url?: string;
    devpost_url?: string;
    demo_url?: string;
    deployment_url?: string;
    tech_tags?: string[];
  };
  judge_surface: Record<
    string,
    {
      dimension: string;
      label: string;
      score: number;
      confidence: number;
      provider: string;
      fallback_used?: boolean;
      fallback_reason?: string;
      jev_confidence?: number;
      is_insufficient_evidence?: boolean;
    }
  >;
  engineering: {
    status: string;
    approx_loc: number;
    primary_languages: string[];
    frontend_frameworks: string[];
    backend_frameworks: string[];
    databases: string[];
    model_providers: string[];
    test_files_count: number;
    api_routes_count: number;
    has_ci: boolean;
    live_deployment_reachable: boolean;
    deployment_url_status?: string;
    deployment_verification?: string;
    deployment_evidence?: string;
    todo_fixme_count: number;
  };
  historical_comparison: {
    sample_sizes: {
      historical_winners: number;
      non_winners?: number;
      strong_non_winners: number;
      total_analyzed: number;
      cohort_description?: string;
    };
    dimensions: Record<string, DimensionComparison>;
  };
  criteria_alignment: {
    target_award: string;
    criteria_summary: string;
    alignment_level: string;
    sponsor_requirements?: string;
  };
  recommendations: {
    summary: string;
    main_gap_headline?: string;
    strengths: Strength[];
    gaps: Gap[];
    next_actions: NextAction[];
    limitations: string[];
  };
  disclaimer: string;
}

const PROGRESS_STEPS = [
  "Reading project",
  "Checking the implementation",
  "Comparing judging criteria",
  "Comparing historical projects",
  "Preparing your analysis",
];

const TRACK_OPTIONS = [
  { id: "best_overall", label: "Best Overall" },
  { id: "best_ai_track", label: "AI & Machine Learning" },
  { id: "best_fintech_track", label: "FinTech & Blockchain" },
  { id: "best_health_track", label: "Healthcare & Life Sciences" },
  { id: "best_social_good", label: "Social Good & Impact" },
  { id: "best_beginner", label: "Beginner Track" },
  { id: "best_hardware", label: "Hardware & IoT" },
];

function formatLabel(raw: string): string {
  const clean = raw.toLowerCase().replace(/_/g, " ");
  if (clean === "very strong") return "Very strong";
  if (clean === "strong") return "Strong";
  if (clean === "moderate") return "Moderate";
  if (clean === "weak") return "Needs work";
  if (clean === "very weak") return "Needs work";
  if (clean === "insufficient evidence") return "Insufficient evidence";
  return raw.replace(/_/g, " ");
}

function getEditorialHeadline(result: AnalysisResult): string {
  if (result.recommendations.main_gap_headline?.trim()) {
    return result.recommendations.main_gap_headline.trim();
  }

  const gaps = result.recommendations.gaps || [];
  const strengths = result.recommendations.strengths || [];
  const dims = result.judge_surface || {};

  const demoScore = dims.demo_strength?.score ?? 3;
  const engLoc = result.engineering?.approx_loc ?? 0;
  const probScore = dims.problem_clarity?.score ?? 3;
  const userScore = dims.user_clarity?.score ?? 3;
  const alignScore = dims.award_alignment?.score ?? 3;

  if (engLoc > 200 && demoScore <= 3) {
    return "Strong engineering. Demo proof is the gap.";
  }
  if (probScore >= 4 && alignScore <= 3) {
    return "Clear product. Award alignment is the gap.";
  }
  if (probScore <= 2 || userScore <= 2) {
    return "Technically ambitious, but harder to understand than it should be.";
  }
  if (demoScore >= 4 && probScore >= 4 && alignScore >= 4) {
    return "Compelling narrative with verified working software.";
  }
  if (strengths.length > 0 && gaps.length > 0) {
    const s = strengths[0]?.title?.replace(/^(Strong|Solid|Clear)\s+/i, "") || "Solid core";
    const g = gaps[0]?.title?.replace(/^(Gap:\s*|Weak\s*|Missing\s*)/i, "") || "presentation";
    return `${s}. ${g} is the main opportunity.`;
  }
  return "Solid execution. The clearest gap is presentation.";
}

export default function Home() {
  const [inputMode, setInputMode] = useState<"link" | "manual">("link");
  const [analyzing, setAnalyzing] = useState(false);
  const [progressIdx, setProgressIdx] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [showMethodology, setShowMethodology] = useState(false);
  const [showAdditionalSources, setShowAdditionalSources] = useState(false);

  // Form Fields
  const [primaryLink, setPrimaryLink] = useState("");
  const [targetHackathon, setTargetHackathon] = useState("shellhacks2025:2025");
  const [targetAward, setTargetAward] = useState("best_overall");
  const [githubUrl, setGithubUrl] = useState("");
  const [devpostUrl, setDevpostUrl] = useState("");
  const [demoUrl, setDemoUrl] = useState("");
  const [deploymentUrl, setDeploymentUrl] = useState("");
  const [sponsorRequirements, setSponsorRequirements] = useState("");

  const [name, setName] = useState("");
  const [tagline, setTagline] = useState("");
  const [problem, setProblem] = useState("");
  const [targetUser, setTargetUser] = useState("");
  const [whatItDoes, setWhatItDoes] = useState("");
  const [howItWorks, setHowItWorks] = useState("");
  const [techTags, setTechTags] = useState("");

  // Cycle progress messages during analysis
  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (analyzing) {
      timer = setInterval(() => {
        setProgressIdx((prev) => (prev < PROGRESS_STEPS.length - 1 ? prev + 1 : prev));
      }, 1400);
    } else {
      setProgressIdx(0);
    }
    return () => clearInterval(timer);
  }, [analyzing]);

  // Smart detect link type when primaryLink changes
  const handlePrimaryLinkChange = (value: string) => {
    setPrimaryLink(value);
    const trimmed = value.trim();
    if (trimmed.includes("github.com")) {
      setGithubUrl(trimmed);
    } else if (trimmed.includes("devpost.com")) {
      setDevpostUrl(trimmed);
    } else if (trimmed.includes("youtube.com") || trimmed.includes("youtu.be") || trimmed.includes("loom.com")) {
      setDemoUrl(trimmed);
    } else if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
      setDeploymentUrl(trimmed);
    }
  };

  const loadSample = (sampleType: "hotelbot" | "ecoquest") => {
    if (sampleType === "hotelbot") {
      setInputMode("manual");
      setName("ConciergePulse");
      setTagline("Autonomous guest feedback phone system extracting operational bottlenecks");
      setProblem(
        "Hotels suffer from low guest review rates (under 8%) and only discover operational failures like AC breakdowns or poor housekeeping after negative public reviews are posted on TripAdvisor."
      );
      setTargetUser("Independent boutique hotel general managers and operations directors.");
      setSponsorRequirements("Must provide an autonomous voice integration using Twilio or telephony API and output structured operational metrics rather than free-form text.");
      setWhatItDoes(
        "Calls hotel guests via an autonomous voice agent post-checkout, conducts an empathetic 2-minute conversation, and extracts structured operational metrics."
      );
      setHowItWorks(
        "Uses Twilio for telephony, FastAPI backend to stream audio, OpenAI Whisper for transcription, and PostgreSQL to aggregate guest sentiment."
      );
      setTechTags("Python, FastAPI, Twilio, PostgreSQL, React, Next.js");
      setDeploymentUrl("https://concierge-pulse.vercel.app");
      setTargetAward("best_overall");
    } else {
      setInputMode("link");
      setPrimaryLink("https://devpost.com/software/ecoquest");
      setGithubUrl("https://github.com/example/ecoquest");
      setDevpostUrl("https://devpost.com/software/ecoquest");
      setDeploymentUrl("https://ecoquest-demo.vercel.app");
      setName("EcoQuest");
      setTagline("Gamifying urban sustainability through verifiable recycling missions");
      setSponsorRequirements("");
      setTargetAward("best_social_good");
    }
  };

  const handleAnalyze = async (e: React.FormEvent) => {
    e.preventDefault();
    setAnalyzing(true);
    setError(null);
    setResult(null);

    // Resolve URLs from primaryLink if set
    let finalGithub = githubUrl.trim();
    let finalDevpost = devpostUrl.trim();
    let finalDemo = demoUrl.trim();
    let finalDeployment = deploymentUrl.trim();

    if (inputMode === "link" && primaryLink.trim()) {
      const link = primaryLink.trim();
      if (link.includes("github.com") && !finalGithub) finalGithub = link;
      else if (link.includes("devpost.com") && !finalDevpost) finalDevpost = link;
      else if ((link.includes("youtube.com") || link.includes("youtu.be")) && !finalDemo) finalDemo = link;
      else if (!finalDeployment && !finalGithub && !finalDevpost) finalDeployment = link;
    }

    const payload = {
      event_id: targetHackathon,
      award_id: targetAward,
      input_mode: inputMode,
      github_url: finalGithub || undefined,
      devpost_url: finalDevpost || undefined,
      demo_url: finalDemo || undefined,
      deployment_url: finalDeployment || undefined,
      sponsor_requirements: sponsorRequirements.trim() || undefined,
      project: {
        name: name.trim() || (finalDevpost ? finalDevpost.split("/").pop() || "Candidate Project" : "Candidate Project"),
        tagline: tagline.trim(),
        problem: problem.trim(),
        target_user: targetUser.trim(),
        sponsor_requirements: sponsorRequirements.trim() || "",
        what_it_does: whatItDoes.trim(),
        how_it_works: howItWorks.trim(),
        tech_tags: techTags
          ? techTags
              .split(",")
              .map((t) => t.trim())
              .filter(Boolean)
          : [],
      },
    };

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned error status ${res.status}`);
      }

      const data: AnalysisResult = await res.json();
      setResult(data);
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Failed to analyze project.";
      setError(errorMsg);
    } finally {
      setAnalyzing(false);
    }
  };

  const resetAnalysis = () => {
    setResult(null);
    setError(null);
  };

  return (
    <div className="min-h-screen bg-canvas text-ink flex flex-col justify-between selection:bg-[#EAE7DF] selection:text-ink">
      {/* 1. Minimal Navigation */}
      <header className="border-b border-edge">
        <div className="max-w-5xl mx-auto px-6 h-20 flex items-center justify-between">
          <button
            onClick={resetAnalysis}
            className="text-left group flex items-baseline gap-2 cursor-pointer focus:outline-none"
          >
            <span className="font-serif text-2xl font-bold tracking-tight text-ink group-hover:opacity-80 transition-opacity">
              HackBench
            </span>
          </button>

          <nav className="flex items-center gap-6 text-sm">
            <button
              onClick={() => setShowMethodology(true)}
              className="text-ink-secondary hover:text-ink transition-colors cursor-pointer"
            >
              Methodology
            </button>
            <a
              href="https://github.com/Aaryan1524/ShellhacksHackathonAnalysis"
              target="_blank"
              rel="noreferrer"
              className="text-ink-secondary hover:text-ink transition-colors"
            >
              GitHub
            </a>
          </nav>
        </div>
      </header>

      {/* 2. Main Content Area */}
      <main className="flex-1 max-w-5xl w-full mx-auto px-6 py-12 md:py-20">
        {/* State A: Input Flow (Hero + Form) */}
        {!result && !analyzing && (
          <div>
            {/* Hero */}
            <section className="mb-14 md:mb-20 max-w-3xl">
              <div className="h-[2px] w-12 bg-gradient-to-r from-amber-600 via-rose-500 to-sky-600 mb-8" />
              <h1 className="font-serif text-5xl sm:text-7xl font-normal tracking-[-0.025em] leading-[1.06] text-ink text-balance">
                See how your hackathon project compares.
              </h1>
              <p className="mt-6 text-lg sm:text-xl text-ink-secondary font-normal leading-relaxed max-w-2xl text-pretty">
                Add your project and compare it with historical winners, strong non-winners, and documented judging
                criteria.
              </p>
            </section>

            {/* Input Container */}
            <section className="max-w-2xl">
              {/* Mode Switcher */}
              <div className="flex items-center gap-3 mb-8 text-sm">
                <button
                  type="button"
                  onClick={() => setInputMode("link")}
                  className={`pb-1.5 transition-all border-b-2 ${
                    inputMode === "link"
                      ? "border-ink font-medium text-ink"
                      : "border-transparent text-ink-secondary hover:text-ink"
                  }`}
                >
                  Analyze from links
                </button>
                <span className="text-edge">/</span>
                <button
                  type="button"
                  onClick={() => setInputMode("manual")}
                  className={`pb-1.5 transition-all border-b-2 ${
                    inputMode === "manual"
                      ? "border-ink font-medium text-ink"
                      : "border-transparent text-ink-secondary hover:text-ink"
                  }`}
                >
                  Enter manually
                </button>
              </div>

              {/* Error Notice */}
              {error && (
                <div className="mb-8 p-4 bg-white border border-rose-300 text-rose-900 rounded text-sm leading-relaxed">
                  {error}
                </div>
              )}

              {/* Form */}
              <form onSubmit={handleAnalyze} className="space-y-8">
                {inputMode === "link" ? (
                  /* --- Mode 1: Links --- */
                  <div className="space-y-6">
                    <div>
                      <label htmlFor="primaryLink" className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-2">
                        Project link
                      </label>
                      <input
                        id="primaryLink"
                        type="url"
                        value={primaryLink}
                        onChange={(e) => handlePrimaryLinkChange(e.target.value)}
                        placeholder="GitHub or Devpost URL"
                        required
                        className="w-full px-4 py-3.5 bg-white border border-edge rounded text-base text-ink placeholder:text-ink-muted focus:outline-none focus:border-ink transition-colors"
                      />
                      <p className="mt-2 text-xs text-ink-secondary">
                        We&apos;ll pull the project information we can find.
                      </p>
                    </div>

                    {/* Secondary Sources (Expandable) */}
                    <div>
                      {!showAdditionalSources ? (
                        <button
                          type="button"
                          onClick={() => setShowAdditionalSources(true)}
                          className="text-xs text-ink-secondary hover:text-ink underline underline-offset-4"
                        >
                          + Add another source (GitHub, Devpost, Demo)
                        </button>
                      ) : (
                        <div className="space-y-4 pt-2 border-t border-edge">
                          <div>
                            <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-1">
                              GitHub repository
                            </label>
                            <input
                              type="url"
                              value={githubUrl}
                              onChange={(e) => setGithubUrl(e.target.value)}
                              placeholder="https://github.com/..."
                              className="w-full px-3.5 py-2.5 bg-white border border-edge rounded text-sm text-ink focus:outline-none focus:border-ink"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-1">
                              Devpost URL
                            </label>
                            <input
                              type="url"
                              value={devpostUrl}
                              onChange={(e) => setDevpostUrl(e.target.value)}
                              placeholder="https://devpost.com/software/..."
                              className="w-full px-3.5 py-2.5 bg-white border border-edge rounded text-sm text-ink focus:outline-none focus:border-ink"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-1">
                              Live demo or video
                            </label>
                            <input
                              type="url"
                              value={demoUrl}
                              onChange={(e) => setDemoUrl(e.target.value)}
                              placeholder="https://youtube.com/... or https://..."
                              className="w-full px-3.5 py-2.5 bg-white border border-edge rounded text-sm text-ink focus:outline-none focus:border-ink"
                            />
                          </div>
                        </div>
                      )}
                    </div>

                    <div>
                      <label htmlFor="sponsorReqLink" className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-1">
                        Sponsor or Track Requirements (optional)
                      </label>
                      <input
                        id="sponsorReqLink"
                        type="text"
                        value={sponsorRequirements}
                        onChange={(e) => setSponsorRequirements(e.target.value)}
                        placeholder="e.g. Must integrate sponsor XYZ API or address specific track prompt"
                        className="w-full px-3.5 py-2.5 bg-white border border-edge rounded text-sm text-ink placeholder:text-ink-muted focus:outline-none focus:border-ink"
                      />
                      <p className="mt-1 text-xs text-ink-secondary">
                        If targeting a specific sponsor challenge, describe what they require.
                      </p>
                    </div>
                  </div>
                ) : (
                  /* --- Mode 2: Manual Fields --- */
                  <div className="space-y-6">
                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-2">
                        Project name <span className="text-rose-600">*</span>
                      </label>
                      <input
                        type="text"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="e.g. ConciergePulse"
                        required
                        className="w-full px-4 py-3 bg-white border border-edge rounded text-base text-ink focus:outline-none focus:border-ink"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-2">
                        One-line pitch
                      </label>
                      <input
                        type="text"
                        value={tagline}
                        onChange={(e) => setTagline(e.target.value)}
                        placeholder="What does it do in one crisp sentence?"
                        className="w-full px-4 py-3 bg-white border border-edge rounded text-base text-ink focus:outline-none focus:border-ink"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-2">
                        What problem are you solving? <span className="text-rose-600">*</span>
                      </label>
                      <textarea
                        rows={3}
                        value={problem}
                        onChange={(e) => setProblem(e.target.value)}
                        placeholder="Describe the specific pain point..."
                        required
                        className="w-full px-4 py-3 bg-white border border-edge rounded text-base text-ink focus:outline-none focus:border-ink resize-y"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-2">
                        Who is it for? <span className="text-rose-600">*</span>
                      </label>
                      <input
                        type="text"
                        value={targetUser}
                        onChange={(e) => setTargetUser(e.target.value)}
                        placeholder="e.g. Boutique hotel general managers"
                        required
                        className="w-full px-4 py-3 bg-white border border-edge rounded text-base text-ink focus:outline-none focus:border-ink"
                      />
                    </div>

                    {/* Mandatory Sponsor Requirements */}
                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-2">
                        Sponsor or Track Requirements <span className="text-rose-600">*</span>
                      </label>
                      <textarea
                        rows={3}
                        value={sponsorRequirements}
                        onChange={(e) => setSponsorRequirements(e.target.value)}
                        placeholder="Paste the sponsor challenge, required API/SDK, or prize criteria (e.g. Must integrate Twilio voice, or best use of Hedera)..."
                        required
                        className="w-full px-4 py-3 bg-white border border-edge rounded text-base text-ink focus:outline-none focus:border-ink resize-y"
                      />
                      <p className="mt-1.5 text-xs text-ink-secondary">
                        Mandatory. Tells us what the sponsor specifically expects so we can evaluate actual requirement fit without guessing.
                      </p>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-2">
                        What does it do? <span className="text-rose-600">*</span>
                      </label>
                      <textarea
                        rows={3}
                        value={whatItDoes}
                        onChange={(e) => setWhatItDoes(e.target.value)}
                        placeholder="What happens when a user touches your product?"
                        required
                        className="w-full px-4 py-3 bg-white border border-edge rounded text-base text-ink focus:outline-none focus:border-ink resize-y"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-2">
                        How does the core flow work? <span className="text-rose-600">*</span>
                      </label>
                      <textarea
                        rows={3}
                        value={howItWorks}
                        onChange={(e) => setHowItWorks(e.target.value)}
                        placeholder="Key technical components and user steps..."
                        required
                        className="w-full px-4 py-3 bg-white border border-edge rounded text-base text-ink focus:outline-none focus:border-ink resize-y"
                      />
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-1">
                          GitHub (optional)
                        </label>
                        <input
                          type="url"
                          value={githubUrl}
                          onChange={(e) => setGithubUrl(e.target.value)}
                          placeholder="https://github.com/..."
                          className="w-full px-3.5 py-2.5 bg-white border border-edge rounded text-sm text-ink focus:outline-none focus:border-ink"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-1">
                          Demo link (optional)
                        </label>
                        <input
                          type="url"
                          value={demoUrl}
                          onChange={(e) => setDemoUrl(e.target.value)}
                          placeholder="https://..."
                          className="w-full px-3.5 py-2.5 bg-white border border-edge rounded text-sm text-ink focus:outline-none focus:border-ink"
                        />
                      </div>
                    </div>
                  </div>
                )}

                {/* Common Track / Benchmark Selectors */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-edge">
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-1.5">
                      Hackathon baseline
                    </label>
                    <select
                      value={targetHackathon}
                      onChange={(e) => setTargetHackathon(e.target.value)}
                      className="w-full px-3.5 py-2.5 bg-white border border-edge rounded text-sm text-ink focus:outline-none focus:border-ink cursor-pointer"
                    >
                      <option value="shellhacks2025:2025">ShellHacks 2025</option>
                      <option value="shellhacks2024:2024">ShellHacks 2024</option>
                      <option value="shellhacks-2023:2023">ShellHacks 2023</option>
                      <option value="shellhacks2026:2026">ShellHacks 2026 (Preparation)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-1.5">
                      Target award
                    </label>
                    <select
                      value={targetAward}
                      onChange={(e) => setTargetAward(e.target.value)}
                      className="w-full px-3.5 py-2.5 bg-white border border-edge rounded text-sm text-ink focus:outline-none focus:border-ink cursor-pointer"
                    >
                      {TRACK_OPTIONS.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Action CTA Button */}
                <div className="pt-4 flex flex-col sm:flex-row sm:items-center gap-4">
                  <button
                    type="submit"
                    className="px-8 py-3.5 bg-ink text-white rounded text-base font-medium hover:bg-neutral-800 transition-colors inline-flex items-center justify-center gap-2 cursor-pointer shadow-sm"
                  >
                    Analyze project →
                  </button>

                  <div className="text-xs text-ink-secondary">
                    Or try a sample:{" "}
                    <button
                      type="button"
                      onClick={() => loadSample("hotelbot")}
                      className="text-ink font-medium underline underline-offset-2 hover:text-neutral-700"
                    >
                      ConciergePulse
                    </button>{" "}
                    ·{" "}
                    <button
                      type="button"
                      onClick={() => loadSample("ecoquest")}
                      className="text-ink font-medium underline underline-offset-2 hover:text-neutral-700"
                    >
                      EcoQuest
                    </button>
                  </div>
                </div>
              </form>
            </section>
          </div>
        )}

        {/* State B: Calm Progress Transition */}
        {analyzing && (
          <section className="py-24 sm:py-36 max-w-xl">
            <h2 className="font-serif text-4xl sm:text-5xl font-normal tracking-tight text-ink mb-8">
              Looking at your project.
            </h2>
            <div className="space-y-4">
              {PROGRESS_STEPS.map((step, idx) => (
                <div
                  key={step}
                  className={`flex items-center gap-3 text-sm transition-opacity duration-300 ${
                    idx === progressIdx
                      ? "text-ink font-medium opacity-100"
                      : idx < progressIdx
                      ? "text-ink-secondary opacity-60"
                      : "text-ink-muted opacity-30"
                  }`}
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      idx === progressIdx
                        ? "bg-ink animate-pulse"
                        : idx < progressIdx
                        ? "bg-ink-secondary"
                        : "bg-edge"
                    }`}
                  />
                  <span>{step}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* State C: Editorial Results Presentation */}
        {result && (
          <article className="space-y-16 sm:space-y-24">
            {/* Top Back Action */}
            <div>
              <button
                type="button"
                onClick={resetAnalysis}
                className="text-xs text-ink-secondary hover:text-ink font-medium flex items-center gap-1.5 cursor-pointer"
              >
                ← Analyze another project
              </button>
            </div>

            {/* 1. Results Hero */}
            <section className="max-w-3xl border-b border-edge pb-12 sm:pb-16">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xs uppercase font-semibold tracking-widest text-ink font-mono">
                  {result.project.name}
                </span>
                <span className="text-edge">·</span>
                <span className="text-xs uppercase font-medium tracking-wider text-ink-secondary">
                  What stands out
                </span>
              </div>
              <h1 className="font-serif text-4xl sm:text-6xl font-normal tracking-tight leading-[1.1] text-ink text-balance">
                {getEditorialHeadline(result)}
              </h1>
              {result.recommendations.summary && (
                <p className="mt-6 text-lg sm:text-xl text-ink-secondary leading-relaxed text-pretty">
                  {result.recommendations.summary}
                </p>
              )}
            </section>

            {/* 2. Top Analysis: 3 Concise Blocks */}
            <section className="grid grid-cols-1 md:grid-cols-3 gap-8 sm:gap-12 border-b border-edge pb-16">
              <div>
                <span className="text-xs uppercase font-semibold tracking-wider text-ink-secondary block mb-3 font-mono">
                  Strongest
                </span>
                <h3 className="font-serif text-xl sm:text-2xl font-normal text-ink mb-2">
                  {result.recommendations.strengths[0]?.title || "Problem & user clarity"}
                </h3>
                <p className="text-sm text-ink-secondary leading-relaxed">
                  {result.recommendations.strengths[0]?.evidence ||
                    "Demonstrated software progress and structured problem framing."}
                </p>
              </div>

              <div>
                <span className="text-xs uppercase font-semibold tracking-wider text-ink-secondary block mb-3 font-mono">
                  Biggest Gap
                </span>
                <h3 className="font-serif text-xl sm:text-2xl font-normal text-ink mb-2">
                  {result.recommendations.gaps[0]?.title || "Observable proof"}
                </h3>
                <p className="text-sm text-ink-secondary leading-relaxed">
                  {result.recommendations.gaps[0]?.evidence ||
                    "The judge must infer key user workflows rather than seeing them immediately verified."}
                </p>
              </div>

              <div>
                <span className="text-xs uppercase font-semibold tracking-wider text-ink-secondary block mb-3 font-mono">
                  Improve Next
                </span>
                <h3 className="font-serif text-xl sm:text-2xl font-normal text-ink mb-2">
                  {result.recommendations.next_actions[0]?.action || "Clarify the first 30 seconds"}
                </h3>
                <p className="text-sm text-ink-secondary leading-relaxed">
                  {result.recommendations.next_actions[0]?.reason ||
                    "Show the complete user outcome before detailing the underlying technical architecture."}
                </p>
              </div>
            </section>

            {/* 3. Streamlined Comparison Table */}
            <section className="max-w-3xl border-b border-edge pb-16">
              <h2 className="font-serif text-2xl sm:text-3xl font-normal text-ink mb-2">
                How you compare
              </h2>
              <p className="text-sm text-ink-secondary mb-8">
                Your evaluation across the 9 canonical hackathon dimensions compared directly against historical ShellHacks winners.
              </p>

              <div className="border border-edge rounded bg-white overflow-hidden shadow-xs">
                <div className="grid grid-cols-12 px-5 py-3 bg-canvas-subtle border-b border-edge text-xs font-semibold uppercase tracking-wider text-ink-secondary">
                  <span className="col-span-5 sm:col-span-5">Dimension</span>
                  <span className="col-span-3 sm:col-span-3">Your Assessment</span>
                  <span className="col-span-4 sm:col-span-4">Historical Winners</span>
                </div>
                <div className="divide-y divide-edge">
                  {Object.entries(result.judge_surface).map(([key, dim]) => {
                    const comp = result.historical_comparison.dimensions?.[key];
                    const winnerStat = comp?.historical_overall_winners?.split(" (")[0] || "Strong → Very strong";
                    return (
                      <div key={key} className="grid grid-cols-12 px-5 py-3.5 items-center text-sm">
                        <span className="col-span-5 sm:col-span-5 font-medium text-ink capitalize">
                          {dim.dimension.replace(/_/g, " ")}
                        </span>
                        <span className="col-span-3 sm:col-span-3">
                          <span
                            className={`inline-block px-2.5 py-0.5 rounded text-xs font-medium ${
                              dim.label === "very_strong" || dim.label === "strong"
                                ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                                : dim.label === "moderate"
                                ? "bg-neutral-100 text-neutral-800 border border-neutral-200"
                                : "bg-amber-50 text-amber-900 border border-amber-200"
                            }`}
                          >
                            {formatLabel(dim.label)}
                          </span>
                        </span>
                        <span className="col-span-4 sm:col-span-4 text-xs text-ink-secondary font-mono">
                          {winnerStat}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              <p className="mt-4 text-xs text-ink-muted">
                {result.historical_comparison.sample_sizes.cohort_description ||
                  `50 analyzed projects: ${result.historical_comparison.sample_sizes.historical_winners} award-winning projects and ${result.historical_comparison.sample_sizes.non_winners || 21} non-winners, including ${result.historical_comparison.sample_sizes.strong_non_winners} strong non-winners.`}
              </p>
            </section>

            {/* 4. Criteria Alignment */}
            <section className="max-w-2xl border-b border-edge pb-16">
              <h2 className="font-serif text-2xl sm:text-3xl font-normal text-ink mb-4">
                Alignment with {TRACK_OPTIONS.find((t) => t.id === targetAward)?.label || "Target Award"}
              </h2>
              <p className="text-sm sm:text-base text-ink-secondary leading-relaxed mb-6">
                {result.criteria_alignment.criteria_summary}
              </p>
              <div className="p-4 bg-white border border-edge rounded text-sm flex items-center justify-between">
                <span className="text-ink font-medium">Documented Track Fit</span>
                <span className="text-ink-secondary font-medium capitalize">
                  {result.criteria_alignment.alignment_level}
                </span>
              </div>
              {result.criteria_alignment.sponsor_requirements && (
                <div className="mt-4 p-4 bg-canvas-subtle border border-edge rounded text-xs space-y-1.5">
                  <span className="font-semibold text-ink uppercase tracking-wider block">
                    Targeted Sponsor Criteria:
                  </span>
                  <p className="text-ink-secondary leading-relaxed">
                    {result.criteria_alignment.sponsor_requirements}
                  </p>
                </div>
              )}
            </section>

            {/* 5. What To Fix Before Judging: The Speakeasy Dark Card */}
            <section className="bg-night text-white rounded-xl p-8 sm:p-14 border border-night-edge">
              <h2 className="font-serif text-3xl sm:text-5xl font-normal tracking-tight text-white mb-10 text-balance">
                What to fix
                <br />
                before judging.
              </h2>

              <div className="space-y-8 max-w-2xl">
                {result.recommendations.next_actions.slice(0, 3).map((action, idx) => (
                  <div key={action.action} className="flex items-start gap-5">
                    <span className="font-serif text-2xl text-neutral-500 font-light pt-0.5">
                      {String(idx + 1).padStart(2, "0")}
                    </span>
                    <div className="space-y-1.5">
                      <h3 className="text-base sm:text-lg font-medium text-neutral-100">
                        {action.action}
                      </h3>
                      <p className="text-sm text-neutral-400 leading-relaxed">
                        {action.reason}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* 6. Advanced Technical Details & Evidence (Collapsed by Default) */}
            <section className="max-w-3xl pt-4">
              <details className="group border border-edge rounded bg-white p-5 cursor-pointer">
                <summary className="text-xs uppercase font-semibold tracking-wider text-ink-secondary flex items-center justify-between focus:outline-none select-none">
                  <span>View evidence & engineering telemetry</span>
                  <span className="text-ink-muted group-open:rotate-180 transition-transform">↓</span>
                </summary>

                <div className="mt-6 pt-4 border-t border-edge space-y-6 text-sm">
                  <p className="text-xs text-ink-secondary">
                    Deterministic metrics extracted directly from repository structures and deployment checks:
                  </p>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
                    <div className="p-3 bg-canvas rounded border border-edge">
                      <span className="text-ink-muted block mb-1">Code volume</span>
                      <strong className="text-ink font-semibold">
                        ~{result.engineering.approx_loc.toLocaleString()} LOC
                      </strong>
                    </div>
                    <div className="p-3 bg-canvas rounded border border-edge">
                      <span className="text-ink-muted block mb-1">Test files</span>
                      <strong className="text-ink font-semibold">
                        {result.engineering.test_files_count} test files
                      </strong>
                    </div>
                    <div className="p-3 bg-canvas rounded border border-edge">
                      <span className="text-ink-muted block mb-1">API endpoints</span>
                      <strong className="text-ink font-semibold">
                        {result.engineering.api_routes_count} routes
                      </strong>
                    </div>
                    <div className="p-3 bg-canvas rounded border border-edge">
                      <span className="text-ink-muted block mb-1">TODO/FIXME</span>
                      <strong className="text-ink font-semibold">
                        {result.engineering.todo_fixme_count} markers
                      </strong>
                    </div>
                  </div>

                  {/* Deployment Verification Block */}
                  <div className="p-4 bg-canvas rounded border border-edge space-y-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-ink uppercase tracking-wider">Deployment Verification</span>
                      <span
                        className={`px-2 py-0.5 rounded font-mono text-[11px] ${
                          result.engineering.deployment_verification === "verified_project"
                            ? "bg-emerald-100 text-emerald-800"
                            : result.engineering.deployment_verification === "likely_project"
                            ? "bg-sky-100 text-sky-800"
                            : result.engineering.deployment_verification === "unrelated"
                            ? "bg-rose-100 text-rose-800"
                            : "bg-neutral-100 text-neutral-700"
                        }`}
                      >
                        {result.engineering.deployment_verification || "none"}
                      </span>
                    </div>
                    <div className="text-ink-secondary leading-relaxed">
                      <strong>Reachable:</strong> {result.engineering.live_deployment_reachable ? "Yes (HTTP 200)" : "No"} ·{" "}
                      <strong>Evidence:</strong> {result.engineering.deployment_evidence || "No deployment URL checked."}
                    </div>
                  </div>

                  {result.engineering.primary_languages?.length > 0 && (
                    <div className="text-xs text-ink-secondary">
                      <span className="font-medium text-ink">Languages & frameworks:</span>{" "}
                      {[
                        ...result.engineering.primary_languages,
                        ...result.engineering.frontend_frameworks,
                        ...result.engineering.backend_frameworks,
                      ].join(", ") || "Standard web stack"}
                    </div>
                  )}

                  {/* Routing & Provider Audit */}
                  <div className="border-t border-edge pt-3 space-y-2 text-xs">
                    <span className="font-semibold text-ink uppercase tracking-wider block">
                      Evaluation Routing Audit
                    </span>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 font-mono text-[11px]">
                      {Object.entries(result.judge_surface).map(([k, v]) => (
                        <div key={k} className="p-2 bg-canvas-subtle rounded border border-edge/60">
                          <span className="text-ink font-medium capitalize block">{k.replace(/_/g, " ")}</span>
                          <span className="text-ink-muted">
                            {v.provider} ({(v.confidence * 100).toFixed(0)}%)
                            {v.fallback_used && ` [fallback: ${v.fallback_reason || "active"}]`}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="text-xs text-ink-muted border-t border-edge pt-3">
                    {result.historical_comparison.sample_sizes.cohort_description ||
                      `Calibrated on 50 analyzed projects: 29 award-winning projects and 21 non-winners, including 6 strong non-winners from ShellHacks.`}
                  </div>
                </div>
              </details>
            </section>

            {/* Reset Button */}
            <div className="pt-8">
              <button
                type="button"
                onClick={resetAnalysis}
                className="px-6 py-3 bg-white border border-edge text-ink text-sm font-medium rounded hover:border-ink transition-colors cursor-pointer"
              >
                ← Analyze another project
              </button>
            </div>
          </article>
        )}
      </main>

      {/* 3. Minimal Methodology Dialog */}
      {showMethodology && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-canvas border border-edge max-w-xl w-full p-8 rounded-lg shadow-xl space-y-6">
            <div className="flex items-baseline justify-between border-b border-edge pb-4">
              <h2 className="font-serif text-2xl font-normal text-ink">Methodology</h2>
              <button
                onClick={() => setShowMethodology(false)}
                className="text-xs text-ink-secondary hover:text-ink cursor-pointer"
              >
                Close ✕
              </button>
            </div>
            <div className="text-sm text-ink-secondary space-y-4 leading-relaxed">
              <p>
                HackBench is an open-source evaluation system built on historical hackathon submissions (starting with
                ShellHacks 2025). Calibrated across 50 analyzed projects: 29 award-winning projects and 21 non-winners,
                including 6 strong non-winners.
              </p>
              <p>
                Every project is evaluated blindly on publicly observable artifacts—Devpost descriptions, repository
                commits, test suites, and demo workflows—using consistent judging rubrics.
              </p>
              <p>
                <strong>HackBench does not predict hackathon winners.</strong> Instead, it provides participants with
                evidence-grounded perspective on how their presentation and implementation compare against past
                distributions before they submit.
              </p>
            </div>
            <div className="pt-4 border-t border-edge flex justify-end">
              <button
                onClick={() => setShowMethodology(false)}
                className="px-4 py-2 bg-ink text-white text-xs font-medium rounded hover:bg-neutral-800 transition-colors cursor-pointer"
              >
                Understood
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 4. Small Editorial Footer */}
      <footer className="border-t border-edge py-8 mt-20">
        <div className="max-w-5xl mx-auto px-6 flex flex-col sm:flex-row items-baseline justify-between gap-4 text-xs text-ink-muted">
          <div>
            <span className="font-serif font-bold text-ink text-sm mr-3">HackBench</span>
            <span>Empirical hackathon analysis. We do not predict winners.</span>
          </div>
          <div className="flex items-center gap-6">
            <button
              onClick={() => setShowMethodology(true)}
              className="hover:text-ink transition-colors cursor-pointer"
            >
              How it works
            </button>
            <a
              href="https://github.com/Aaryan1524/ShellhacksHackathonAnalysis"
              target="_blank"
              rel="noreferrer"
              className="hover:text-ink transition-colors"
            >
              Source code
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
