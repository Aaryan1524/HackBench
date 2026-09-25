"use client";

import React, { useState, useEffect } from "react";

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
    todo_fixme_count: number;
  };
  historical_comparison: {
    sample_sizes: {
      historical_winners: number;
      strong_non_winners: number;
      total_analyzed: number;
    };
    dimensions: Record<string, DimensionComparison>;
  };
  criteria_alignment: {
    target_award: string;
    criteria_summary: string;
    alignment_level: string;
  };
  recommendations: {
    summary: string;
    strengths: Strength[];
    gaps: Gap[];
    next_actions: NextAction[];
    limitations: string[];
  };
  disclaimer: string;
}

const PROGRESS_STEPS = [
  "Reading project submission & evidence...",
  "Running static analysis & code metrics (Layer 1: Deterministic Software)...",
  "Evaluating judge-facing presentation (Layer 2: Jev System One)...",
  "Assessing documented judging criteria & award alignment...",
  "Benchmarking against historical ShellHacks winners & strong non-winners...",
  "Synthesizing evidence-grounded takeaways (Layer 3: Gemini Synthesis)...",
];

export default function Home() {
  const [inputMode, setInputMode] = useState<"link" | "manual">("link");
  const [analyzing, setAnalyzing] = useState(false);
  const [progressIdx, setProgressIdx] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);

  // Form Fields
  const [targetHackathon, setTargetHackathon] = useState("shellhacks2025:2025");
  const [targetAward, setTargetAward] = useState("best_overall");
  const [githubUrl, setGithubUrl] = useState("");
  const [devpostUrl, setDevpostUrl] = useState("");
  const [demoUrl, setDemoUrl] = useState("");
  const [deploymentUrl, setDeploymentUrl] = useState("");

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
      }, 1600);
    } else {
      setProgressIdx(0);
    }
    return () => clearInterval(timer);
  }, [analyzing]);

  const loadSample = (sampleType: "ecoquest" | "hotelbot") => {
    if (sampleType === "ecoquest") {
      setInputMode("link");
      setName("EcoQuest");
      setTagline("Gamifying urban sustainability through verifiable recycling missions");
      setGithubUrl("https://github.com/example/ecoquest");
      setDevpostUrl("https://devpost.com/software/ecoquest");
      setDeploymentUrl("https://ecoquest-demo.vercel.app");
      setDemoUrl("https://youtube.com/watch?v=sample123");
    } else {
      setInputMode("manual");
      setName("ConciergePulse");
      setTagline("Autonomous guest feedback phone system extracting operational bottlenecks");
      setProblem(
        "Hotels suffer from low guest review rates (under 8%) and only discover operational failures like AC breakdowns or poor housekeeping after negative public reviews are posted on TripAdvisor."
      );
      setTargetUser("Independent boutique hotel general managers and operations directors.");
      setWhatItDoes(
        "Calls hotel guests via an autonomous voice agent post-checkout, conducts an empathetic 2-minute conversation, and extracts structured operational metrics."
      );
      setHowItWorks(
        "Uses Twilio for telephony, FastAPI backend to stream audio, OpenAI Whisper for transcription, and PostgreSQL to aggregate guest sentiment."
      );
      setTechTags("Python, FastAPI, Twilio, PostgreSQL, React, Next.js");
      setDeploymentUrl("https://concierge-pulse.vercel.app");
    }
  };

  const handleAnalyze = async (e: React.FormEvent) => {
    e.preventDefault();
    setAnalyzing(true);
    setError(null);
    setResult(null);

    const payload = {
      event_id: targetHackathon,
      award_id: targetAward,
      input_mode: inputMode,
      github_url: githubUrl.trim() || undefined,
      devpost_url: devpostUrl.trim() || undefined,
      demo_url: demoUrl.trim() || undefined,
      deployment_url: deploymentUrl.trim() || undefined,
      project: {
        name: name.trim() || "Candidate Project",
        tagline: tagline.trim(),
        problem: problem.trim(),
        target_user: targetUser.trim(),
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

  const getLabelColor = (label: string) => {
    const l = label.toLowerCase();
    if (l === "very_strong") return "bg-emerald-900/60 text-emerald-300 border-emerald-700/50";
    if (l === "strong") return "bg-teal-900/60 text-teal-300 border-teal-700/50";
    if (l === "moderate") return "bg-amber-900/60 text-amber-300 border-amber-700/50";
    if (l === "weak" || l === "very_weak") return "bg-rose-900/60 text-rose-300 border-rose-700/50";
    return "bg-slate-800 text-slate-400 border-slate-700";
  };

  return (
    <main className="max-w-5xl mx-auto px-4 py-10">
      {/* Header */}
      <header className="mb-10 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-950/80 border border-indigo-700/50 text-indigo-300 mb-4">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          HackBench Forensics V1 • Multi-Layer Empirical Engine
        </div>
        <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-200 to-indigo-300 bg-clip-text text-transparent">
          Historical Hackathon Forensics
        </h1>
        <p className="mt-3 text-slate-400 max-w-2xl mx-auto text-sm sm:text-base">
          Evaluate how your project compares with historical hackathon winners and strong non-winners based strictly
          on public evidence, verified code metrics, and documented judging criteria.
        </p>

        {/* Anti-Prediction Banner */}
        <div className="mt-4 max-w-xl mx-auto px-4 py-2 rounded-lg bg-slate-900/90 border border-slate-800 text-xs text-slate-400">
          <span className="font-semibold text-slate-300">Invariant:</span> HackBench does{" "}
          <strong className="text-rose-300">NOT</strong> predict winners or generate win probabilities. It provides
          deterministic gap analysis against past empirical distributions.
        </div>
      </header>

      {/* Main Container */}
      {!result && !analyzing && (
        <section className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6 sm:p-8 backdrop-blur shadow-2xl">
          {/* Preset Buttons */}
          <div className="flex flex-wrap items-center justify-between gap-3 mb-6 pb-6 border-b border-slate-800">
            <span className="text-xs font-medium text-slate-400">Quick Test Samples:</span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => loadSample("ecoquest")}
                className="text-xs px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 transition"
              >
                Sample A (Link-Based)
              </button>
              <button
                type="button"
                onClick={() => loadSample("hotelbot")}
                className="text-xs px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 transition"
              >
                Sample B (Manual Workflow)
              </button>
            </div>
          </div>

          {/* Path Selector */}
          <div className="flex rounded-xl bg-slate-950 p-1 mb-8 border border-slate-800 max-w-md mx-auto">
            <button
              type="button"
              onClick={() => setInputMode("link")}
              className={`flex-1 py-2 text-xs sm:text-sm font-semibold rounded-lg transition ${
                inputMode === "link"
                  ? "bg-indigo-600 text-white shadow"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Path A: Analyze From Links
            </button>
            <button
              type="button"
              onClick={() => setInputMode("manual")}
              className={`flex-1 py-2 text-xs sm:text-sm font-semibold rounded-lg transition ${
                inputMode === "manual"
                  ? "bg-indigo-600 text-white shadow"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Path B: Describe Manually
            </button>
          </div>

          <form onSubmit={handleAnalyze} className="space-y-6">
            {/* Global Meta */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
                  Historical Benchmark Hackathon
                </label>
                <select
                  value={targetHackathon}
                  onChange={(e) => setTargetHackathon(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                >
                  <option value="shellhacks2025:2025">ShellHacks 2025 (Empirical Dataset)</option>
                  <option value="shellhacks2026:2026">ShellHacks 2026 (Preparation Target)</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
                  Target Category / Award
                </label>
                <select
                  value={targetAward}
                  onChange={(e) => setTargetAward(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                >
                  <option value="best_overall">1st, 2nd, & 3rd Best Overall</option>
                  <option value="best_first_time">Best First-Time Hacker</option>
                  <option value="sponsor_challenge">Sponsor Track / Challenge</option>
                </select>
              </div>
            </div>

            {/* Path A Fields */}
            {inputMode === "link" ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                    GitHub Repository URL (Public)
                  </label>
                  <input
                    type="url"
                    placeholder="https://github.com/username/project"
                    value={githubUrl}
                    onChange={(e) => setGithubUrl(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                  <span className="text-[11px] text-slate-500 mt-1 block">
                    Read-only static inspection. Safe execution invariant: repositories are never executed.
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                      Devpost / Submission URL (Optional)
                    </label>
                    <input
                      type="url"
                      placeholder="https://devpost.com/software/..."
                      value={devpostUrl}
                      onChange={(e) => setDevpostUrl(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                      Live Deployment URL (Optional)
                    </label>
                    <input
                      type="url"
                      placeholder="https://my-project.vercel.app"
                      value={deploymentUrl}
                      onChange={(e) => setDeploymentUrl(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                    Video Demo URL (Optional)
                  </label>
                  <input
                    type="url"
                    placeholder="https://youtu.be/... or Loom link"
                    value={demoUrl}
                    onChange={(e) => setDemoUrl(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>
            ) : (
              /* Path B Fields */
              <div className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                      Project Name *
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. ConciergePulse"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                      One-Line Pitch / Tagline
                    </label>
                    <input
                      type="text"
                      placeholder="Short elevator summary"
                      value={tagline}
                      onChange={(e) => setTagline(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                    What Problem Are You Solving? *
                  </label>
                  <textarea
                    rows={2}
                    required
                    placeholder="Describe the real-world friction, pain point, or operational challenge..."
                    value={problem}
                    onChange={(e) => setProblem(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                    Who Is It For (Target User)? *
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="Specific demographic, profession, or user persona"
                    value={targetUser}
                    onChange={(e) => setTargetUser(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                  />
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                      What Does The Product Do?
                    </label>
                    <textarea
                      rows={2}
                      placeholder="Primary functionality and core user flow..."
                      value={whatItDoes}
                      onChange={(e) => setWhatItDoes(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                      How Does It Work (Architecture)?
                    </label>
                    <textarea
                      rows={2}
                      placeholder="Tech flow, APIs, database, and client interaction..."
                      value={howItWorks}
                      onChange={(e) => setHowItWorks(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                      Tech Stack (Comma-Separated)
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Next.js, FastAPI, PostgreSQL, Supabase"
                      value={techTags}
                      onChange={(e) => setTechTags(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                      Live Deployment URL (Optional)
                    </label>
                    <input
                      type="url"
                      placeholder="https://..."
                      value={deploymentUrl}
                      onChange={(e) => setDeploymentUrl(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                </div>
              </div>
            )}

            {error && (
              <div className="p-4 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-300 text-sm">
                <strong>Error:</strong> {error}
              </div>
            )}

            <button
              type="submit"
              className="w-full py-3.5 px-6 rounded-xl font-bold bg-indigo-600 hover:bg-indigo-500 text-white transition shadow-lg hover:shadow-indigo-500/25 flex items-center justify-center gap-2"
            >
              Analyze My Project
            </button>
          </form>
        </section>
      )}

      {/* Analyzing Progress State */}
      {analyzing && (
        <section className="bg-slate-900/80 border border-slate-800 rounded-2xl p-10 text-center backdrop-blur">
          <div className="w-12 h-12 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-6"></div>
          <h2 className="text-xl font-bold text-white mb-2">Analyzing Project Evidence</h2>
          <p className="text-sm font-medium text-indigo-400 mb-6">{PROGRESS_STEPS[progressIdx]}</p>

          <div className="max-w-md mx-auto space-y-2 text-left">
            {PROGRESS_STEPS.map((step, idx) => (
              <div
                key={idx}
                className={`flex items-center gap-3 text-xs py-1 transition-opacity ${
                  idx <= progressIdx ? "text-slate-200 opacity-100" : "text-slate-600 opacity-40"
                }`}
              >
                <span
                  className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] ${
                    idx < progressIdx
                      ? "bg-emerald-500 text-black font-bold"
                      : idx === progressIdx
                      ? "bg-indigo-500 text-white animate-pulse"
                      : "bg-slate-800 text-slate-500"
                  }`}
                >
                  {idx < progressIdx ? "✓" : idx + 1}
                </span>
                <span>{step}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Results Page */}
      {result && (
        <div className="space-y-8 animate-fadeIn">
          {/* Top Result Banner */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 sm:p-8 backdrop-blur flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-indigo-400 mb-1">
                Forensic Analysis Report
              </div>
              <h2 className="text-2xl sm:text-3xl font-extrabold text-white">{result.project.name}</h2>
              <p className="text-xs sm:text-sm text-slate-400 mt-1">
                Historical Benchmark: <span className="text-slate-200 font-semibold">ShellHacks 2025</span> •
                Target: <span className="text-slate-200 font-semibold">{result.criteria_alignment.target_award}</span>
              </p>
            </div>
            <button
              onClick={() => setResult(null)}
              className="text-xs px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 transition"
            >
              ← Analyze Another Project
            </button>
          </div>

          {/* Section A: Quick View */}
          <section className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6">
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400 mb-4">
              Section A — Quick View (9 Canonical Dimensions)
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {Object.entries(result.judge_surface).map(([dim, val]) => (
                <div key={dim} className="p-3 rounded-xl bg-slate-950 border border-slate-800/80">
                  <div className="text-[11px] font-medium text-slate-400 capitalize mb-1">
                    {dim.replace(/_/g, " ")}
                  </div>
                  <div
                    className={`inline-block text-xs font-semibold px-2.5 py-0.5 rounded-full border ${getLabelColor(
                      val.label
                    )}`}
                  >
                    {val.is_insufficient_evidence ? "Insufficient Evidence" : val.label.replace(/_/g, " ").toUpperCase()}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1.5 flex items-center justify-between">
                    <span>Provider: {val.provider}</span>
                    <span>Conf: {Math.round(val.confidence * 100)}%</span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Section B & C: Strengths and Gaps */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Section B: Biggest Strengths */}
            <section className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6">
              <h3 className="text-sm font-bold uppercase tracking-wider text-emerald-400 mb-4 flex items-center gap-2">
                <span>✓</span> Section B — Biggest Strengths
              </h3>
              <div className="space-y-4">
                {result.recommendations.strengths.map((str, idx) => (
                  <div key={idx} className="p-4 rounded-xl bg-slate-950 border border-slate-800/80">
                    <h4 className="text-sm font-bold text-slate-100">{str.title}</h4>
                    <p className="text-xs text-slate-300 mt-1">{str.evidence}</p>
                    <p className="text-[11px] text-slate-500 mt-2 border-t border-slate-800/60 pt-1.5">
                      <strong className="text-slate-400">Historical context:</strong> {str.historical_context}
                    </p>
                  </div>
                ))}
              </div>
            </section>

            {/* Section C: Biggest Gaps */}
            <section className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6">
              <h3 className="text-sm font-bold uppercase tracking-wider text-amber-400 mb-4 flex items-center gap-2">
                <span>!</span> Section C — Observable Gaps vs Winners
              </h3>
              <div className="space-y-4">
                {result.recommendations.gaps.map((gap, idx) => (
                  <div key={idx} className="p-4 rounded-xl bg-slate-950 border border-slate-800/80">
                    <h4 className="text-sm font-bold text-slate-100">{gap.title}</h4>
                    <p className="text-xs text-slate-300 mt-1">{gap.evidence}</p>
                    <p className="text-[11px] text-slate-500 mt-2 border-t border-slate-800/60 pt-1.5">
                      <strong className="text-slate-400">Historical context:</strong> {gap.historical_context}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          </div>

          {/* Section D: Historical Comparison */}
          <section className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400">
                Section D — Historical Comparison
              </h3>
              <span className="text-xs text-slate-500">
                Cohort Sample Sizes: Winners (n={result.historical_comparison.sample_sizes.historical_winners}) • Strong
                Non-Winners (n={result.historical_comparison.sample_sizes.strong_non_winners})
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 uppercase text-[11px]">
                    <th className="py-2.5 px-3">Dimension</th>
                    <th className="py-2.5 px-3">You</th>
                    <th className="py-2.5 px-3">Historical Winners</th>
                    <th className="py-2.5 px-3">Strong Non-Winners</th>
                    <th className="py-2.5 px-3">Interpretation</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {Object.entries(result.historical_comparison.dimensions).map(([dim, comp]) => (
                    <tr key={dim} className="hover:bg-slate-800/30 transition">
                      <td className="py-3 px-3 font-semibold text-slate-200 capitalize">
                        {dim.replace(/_/g, " ")}
                      </td>
                      <td className="py-3 px-3">
                        <span className={`px-2 py-0.5 rounded text-[11px] font-semibold border ${getLabelColor(comp.you)}`}>
                          {comp.you}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-slate-300 font-medium">{comp.historical_overall_winners}</td>
                      <td className="py-3 px-3 text-slate-400">{comp.strong_non_winners}</td>
                      <td className="py-3 px-3 text-slate-400 italic">{comp.interpretation}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* Section E: Judging Criteria Alignment */}
          <section className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6">
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400 mb-2">
              Section E — Documented Judging Criteria
            </h3>
            <p className="text-xs text-slate-400 mb-4">
              Criteria: <span className="text-slate-200 font-semibold">{result.criteria_alignment.criteria_summary}</span>
            </p>
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
              <div>
                <span className="text-xs text-slate-400 block mb-1">Assessed Alignment Level:</span>
                <span className={`px-3 py-1 rounded-full text-xs font-bold border ${getLabelColor(result.criteria_alignment.alignment_level)}`}>
                  {result.criteria_alignment.alignment_level.toUpperCase()}
                </span>
              </div>
              <span className="text-xs text-slate-500 max-w-sm text-right">
                Evaluates alignment between the project&apos;s primary workflow and the declared award rubrics.
              </span>
            </div>
          </section>

          {/* Section F: Engineering View */}
          <section className="bg-slate-900/70 border border-slate-800 rounded-2xl p-6">
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400 mb-4">
              Section F — Engineering & Codebase Verification (Zero Hallucination)
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs mb-4">
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <span className="text-slate-500 block">Verified LOC</span>
                <span className="text-base font-bold text-white">{result.engineering.approx_loc}</span>
              </div>
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <span className="text-slate-500 block">Test Files</span>
                <span className="text-base font-bold text-white">{result.engineering.test_files_count}</span>
              </div>
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <span className="text-slate-500 block">API Routes</span>
                <span className="text-base font-bold text-white">{result.engineering.api_routes_count}</span>
              </div>
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                <span className="text-slate-500 block">Live Deployment</span>
                <span
                  className={`text-xs font-bold px-2 py-0.5 rounded inline-block mt-1 ${
                    result.engineering.live_deployment_reachable
                      ? "bg-emerald-900/60 text-emerald-300 border border-emerald-700/50"
                      : "bg-slate-800 text-slate-400"
                  }`}
                >
                  {result.engineering.live_deployment_reachable ? "Reachable (HTTP 200)" : "Unreachable / None"}
                </span>
              </div>
            </div>

            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs space-y-2">
              <div>
                <strong className="text-slate-300">Frontend:</strong>{" "}
                <span className="text-slate-400">
                  {result.engineering.frontend_frameworks.join(", ") || "None detected"}
                </span>
              </div>
              <div>
                <strong className="text-slate-300">Backend:</strong>{" "}
                <span className="text-slate-400">
                  {result.engineering.backend_frameworks.join(", ") || "None detected"}
                </span>
              </div>
              <div>
                <strong className="text-slate-300">Databases:</strong>{" "}
                <span className="text-slate-400">{result.engineering.databases.join(", ") || "None detected"}</span>
              </div>
              <div>
                <strong className="text-slate-300">Model Providers:</strong>{" "}
                <span className="text-slate-400">
                  {result.engineering.model_providers.join(", ") || "None detected"}
                </span>
              </div>
            </div>
          </section>

          {/* Section G: What To Do Next */}
          <section className="bg-slate-900/70 border border-indigo-900/50 rounded-2xl p-6 bg-gradient-to-br from-slate-900 via-slate-900 to-indigo-950/30">
            <h3 className="text-sm font-bold uppercase tracking-wider text-indigo-300 mb-4 flex items-center gap-2">
              <span>⚡</span> Section G — What To Do Next (Top 3 Prioritized Improvements)
            </h3>
            <div className="space-y-3">
              {result.recommendations.next_actions.map((act) => (
                <div key={act.priority} className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 flex gap-4">
                  <span className="w-7 h-7 rounded-full bg-indigo-600 text-white font-bold flex items-center justify-center text-sm shrink-0">
                    {act.priority}
                  </span>
                  <div>
                    <h4 className="text-sm font-bold text-white">{act.action}</h4>
                    <p className="text-xs text-slate-300 mt-1">{act.reason}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Methodology and Disclaimer Footer */}
          <footer className="p-6 rounded-2xl bg-slate-950 border border-slate-800/80 text-xs text-slate-500 space-y-2">
            <div>
              <strong className="text-slate-400">Methodology Notice:</strong> {result.disclaimer}
            </div>
            <div>
              <strong className="text-slate-400">Limitations:</strong>{" "}
              {result.recommendations.limitations.join(" • ")}
            </div>
          </footer>
        </div>
      )}
    </main>
  );
}
