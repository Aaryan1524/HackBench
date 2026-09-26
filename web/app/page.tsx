"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  durationBucket, failureStageFor, inputTypeFor, safeEventId, safePrizeEventId, statusClass,
  trackAnalysisCompleted, trackAnalysisFailed, trackAnalysisStarted, trackEvidenceOpened,
  trackModeSelected, trackPrizeFitViewed, trackReviewAgainClicked,
  type FailureStage, type StatusClass,
} from "@/lib/analytics";

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

interface PrizeFit {
  prize_id: string;
  award_title: string;
  sponsor_name?: string | null;
  prize_type: string;
  fit_level: "very_strong" | "strong" | "moderate" | "weak" | "very_weak" | "insufficient_criteria" | "insufficient_evidence";
  fit_label: string;
  why_it_fits: string;
  why_it_may_not_fit: string;
  documented_requirements: string[];
  what_must_be_demonstrated: string[];
  biggest_missing_requirement: string;
  sponsor_tech_role: "central" | "decorative" | "absent" | "not_applicable";
  historical_context?: string | null;
  insufficient_criteria: boolean;
}

interface PrizeFitResult {
  targeting_mode: "auto" | "specific";
  top_fits: PrizeFit[];
  evaluated_count: number;
  insufficient_criteria_count: number;
  summary: string;
}

interface AnalysisResult {
  analysis_id: string;
  analysis_mode?: "idea" | "project";
  idea?: {
    description: string;
    technologies_of_interest: string[];
    extracted?: {
      problem?: string;
      target_user?: string;
      proposed_product?: string;
      core_workflow?: string;
      intended_technologies?: string[];
      likely_sponsor_technologies?: string[];
      user_outcome?: string;
      notable_constraints?: string;
    };
  };
  prize_fits?: PrizeFitResult;
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
  engineering?: {
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
    takeaway?: string | null;
    baseline_label?: string;
  };
  criteria_alignment: {
    target_award: string;
    criteria_summary: string;
    alignment_level: string;
    sponsor_requirements?: string;
  };
  notes?: string[];
  telemetry?: { jev_used: boolean; gemini_used: boolean; fallback_used: boolean; result_quality: "full" | "partial" };
  recommendations: {
    summary: string;
    main_gap_headline?: string;
    strengths: Strength[];
    gaps: Gap[];
    next_actions: NextAction[];
    limitations: string[];
    build_first?: string;
    dont_build_yet?: string[];
    historical_takeaway?: string;
  };
  disclaimer: string;
}

const IDEA_PROGRESS_STEPS = [
  "Reading your idea",
  "Extracting core workflow and target user",
  "Checking scope and demo potential",
  "Comparing against historical winners",
  "Preparing your build guidance",
];

const PROJECT_PROGRESS_STEPS = [
  "Reading project",
  "Checking the implementation",
  "Comparing judging criteria",
  "Comparing historical projects",
  "Preparing your analysis",
];

// Which past hackathon(s) prizes and winner comparisons come from. Must match the backend's baselines.
const BASELINE_OPTIONS = [
  { id: "shellhacks2025:2025", label: "ShellHacks 2025" },
  { id: "shellhacks2024:2024", label: "ShellHacks 2024" },
  { id: "shellhacks-2023:2023", label: "ShellHacks 2023" },
  { id: "all:combined", label: "All years combined (2023–2025)" },
];

// Where the prizes you are matched against come from. ShellHacks 2026 is this year's challenges: it has no
// results yet, so it is a prize source only and is not offered as a comparison baseline.
const PRIZE_EVENT_OPTIONS = [
  { id: "shellhacks2026:2026", label: "ShellHacks 2026 (this year)" },
  ...BASELINE_OPTIONS.map((o) => ({ id: o.id, label: o.label })),
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
  if (clean === "not evaluated") return "Not evaluated (idea stage)";
  return raw.replace(/_/g, " ");
}

function getEditorialHeadline(result: AnalysisResult): string {
  if (result.recommendations.main_gap_headline?.trim()) {
    return result.recommendations.main_gap_headline.trim();
  }

  const gaps = result.recommendations.gaps || [];
  const strengths = result.recommendations.strengths || [];
  const dims = result.judge_surface || {};

  // Missing evidence is unknown, not weak: treat it as neutral.
  const scoreOf = (key: string) => {
    const d = dims[key];
    return !d || d.label === "insufficient_evidence" || d.label === "not_evaluated" ? 3 : d.score;
  };
  const demoScore = scoreOf("demo_strength");
  const engLoc = result.engineering?.approx_loc ?? 0;
  const probScore = scoreOf("problem_clarity");
  const userScore = scoreOf("user_clarity");
  const alignScore = scoreOf("award_alignment");

  if (result.analysis_mode === "idea") {
    if (strengths.length > 0 && gaps.length > 0) {
      return `${strengths[0].title}.\n${gaps[0].title} needs sharpening.`;
    }
    return "Clear problem.\nThe product hook needs sharpening.";
  }

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

function ComparisonSection({ result, embedded = false }: { result: AnalysisResult; embedded?: boolean }) {
  return (
  <section className={embedded ? "" : "max-w-3xl border-b border-edge pb-16"}>
    {embedded ? (
      <h3 className="text-xs uppercase font-semibold tracking-wider text-ink-secondary font-mono mb-2">
        How your concept compares
      </h3>
    ) : (
      <h2 className="font-serif text-2xl sm:text-3xl font-normal text-ink mb-2">
        How you compare
      </h2>
    )}
    <p className="text-sm text-ink-secondary mb-8">
      {result.analysis_mode === "idea"
        ? "How your concept reads across judging areas, next to past ShellHacks winners."
        : "How your project reads across nine judging areas, next to past ShellHacks winners."}
    </p>

    <div className="border border-edge rounded bg-white overflow-hidden shadow-xs">
      <div className="grid grid-cols-12 px-5 py-3 bg-canvas-subtle border-b border-edge text-xs font-semibold uppercase tracking-wider text-ink-secondary">
        <span className="col-span-5 sm:col-span-5">Dimension</span>
        <span className="col-span-3 sm:col-span-3">Your Assessment</span>
        <span className="col-span-4 sm:col-span-4">
            {result.historical_comparison?.baseline_label ? `Winners, ${result.historical_comparison.baseline_label}` : "Past winners"}
          </span>
      </div>
      <div className="divide-y divide-edge">
        {Object.entries(result.judge_surface).map(([key, dim]) => {
          const comp = result.historical_comparison?.dimensions?.[key];
          const winnerStat = comp?.historical_overall_winners?.split(" (")[0] || "No historical data";
          const isNotEval = dim.label === "not_evaluated" || dim.label === "insufficient_evidence";

          return (
            <div key={key} className="grid grid-cols-12 px-5 py-3.5 items-center text-sm">
              <span className="col-span-5 sm:col-span-5 font-medium text-ink capitalize">
                {key.replace(/_/g, " ")}
              </span>
              <span className="col-span-3 sm:col-span-3">
                <span
                  className={`inline-block px-2.5 py-0.5 rounded text-xs font-medium ${
                    isNotEval
                      ? "bg-slate-100 text-slate-600 border border-slate-200"
                      : dim.label === "very_strong" || dim.label === "strong"
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
      {result.historical_comparison?.sample_sizes?.cohort_description || "No historical data is available for this baseline."}
    </p>
  </section>
  );
}

export default function Home() {
  // Primary flow is "idea", secondary flow is "project"
  const [analysisMode, setAnalysisMode] = useState<"idea" | "project">("idea");
  const [projectInputSubmode, setProjectInputSubmode] = useState<"link" | "manual">("link");

  const [analyzing, setAnalyzing] = useState(false);
  const [progressIdx, setProgressIdx] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [showMethodology, setShowMethodology] = useState(false);
  const [showAdditionalSources, setShowAdditionalSources] = useState(false);

  // Common Fields
  const [targetHackathon, setTargetHackathon] = useState("shellhacks2025:2025"); // past results to compare against
  const [prizeEvent, setPrizeEvent] = useState("shellhacks2026:2026"); // whose prizes to match against
  const [targetAward, setTargetAward] = useState("best_overall");
  const [prizeTargetingMode, setPrizeTargetingMode] = useState<"auto" | "specific">("auto");
  const [availablePrizes, setAvailablePrizes] = useState<Array<{ id: string; label: string }>>(TRACK_OPTIONS);

  // Fetch documented prizes for hackathon
  useEffect(() => {
    let isMounted = true;
    async function fetchPrizes() {
      try {
        const res = await fetch(`/api/events/${encodeURIComponent(prizeEvent)}/prizes`);
        if (res.ok) {
          const data = await res.json();
          if (data.prizes && Array.isArray(data.prizes)) {
            const valid = data.prizes
              .filter((p: { has_sufficient_criteria: boolean }) => p.has_sufficient_criteria)
              .map((p: { prize_id: string; title: string }) => ({
                id: p.prize_id,
                label: p.title,
              }));
            if (isMounted && valid.length > 0) {
              setAvailablePrizes(valid);
              // A prize picked for another year may not exist in this one.
              setTargetAward((current) => (valid.some((v: { id: string }) => v.id === current) ? current : valid[0].id));
              return;
            }
          }
        }
      } catch {
        // Fallback to static TRACK_OPTIONS
      }
      if (isMounted) {
        setAvailablePrizes(TRACK_OPTIONS);
      }
    }
    fetchPrizes();
    return () => {
      isMounted = false;
    };
  }, [prizeEvent]);

  // Idea Mode Fields
  const [ideaDescription, setIdeaDescription] = useState("");
  const [technologiesOfInterest, setTechnologiesOfInterest] = useState("");

  // Project Mode Fields
  const [primaryLink, setPrimaryLink] = useState("");
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
  const [techTags] = useState("");

  const activeSteps = analysisMode === "idea" ? IDEA_PROGRESS_STEPS : PROJECT_PROGRESS_STEPS;

  // Cycle progress messages during analysis
  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (analyzing) {
      timer = setInterval(() => {
        setProgressIdx((prev) => (prev < activeSteps.length - 1 ? prev + 1 : prev));
      }, 1400);
    } else {
      setProgressIdx(0);
    }
    return () => clearInterval(timer);
  }, [analyzing, activeSteps.length]);

  // Smart detect link type when primaryLink changes
  // The link is classified once, at submit. Classifying per keystroke saved half-typed text as a deployment URL.
  const handlePrimaryLinkChange = (value: string) => {
    setPrimaryLink(value);
  };

  const RANDOM_IDEAS = [
    {
      description: "An offline peer-to-peer mesh communication app for university campuses that lets students broadcast emergency alerts and coordinate safe walks during cellular network blackouts.",
      technologies: "Bluetooth Low Energy, React Native, SQLite",
      award: "best_overall",
    },
    {
      description: "A smart pantry assistant that scans grocery receipts, monitors shelf life, and dynamically generates zero-waste dinner recipes based on ingredients expiring soon.",
      technologies: "Next.js, Python, OCR, Supabase",
      award: "best_overall",
    },
    {
      description: "An ambient clinical note-taking assistant for ER triage nurses that listens to patient intake check-ins and auto-populates structured EHR vitals and symptoms in real time.",
      technologies: "Whisper, FastAPI, WebSockets, Python",
      award: "best_overall",
    },
    {
      description: "A browser accessibility tool that converts complex financial dashboards and charts into interactive acoustic sonifications for visually impaired analysts.",
      technologies: "Web Audio API, Chrome Extensions API, TypeScript",
      award: "best_overall",
    },
    {
      description: "A hyper-local flood navigation app combining municipal storm drain sensor feeds with crowdsourced road hazard reports to guide drivers around sudden flash floods.",
      technologies: "Mapbox, Go, MQTT, React",
      award: "best_overall",
    },
  ];

  const loadSample = (sampleType: "idea" | "ecoquest") => {
    if (sampleType === "idea") {
      setAnalysisMode("idea");
      const available = RANDOM_IDEAS.filter((i) => i.description !== ideaDescription);
      const chosen = available.length > 0 ? available[Math.floor(Math.random() * available.length)] : RANDOM_IDEAS[0];
      setIdeaDescription(chosen.description);
      setTechnologiesOfInterest(chosen.technologies);
      setTargetHackathon("shellhacks2025:2025");
      setPrizeEvent("shellhacks2026:2026");
      setTargetAward(chosen.award);
      setPrizeTargetingMode("auto");
    } else {
      setAnalysisMode("project");
      setProjectInputSubmode("manual");
      setPrimaryLink("");
      setGithubUrl("");
      setDevpostUrl("");
      setDeploymentUrl("");
      setName("EcoQuest");
      setTagline("Gamifying urban sustainability through verifiable recycling missions");
      setProblem("People want to recycle correctly but get no feedback, so contamination in recycling bins stays high.");
      setTargetUser("City residents in apartment buildings");
      setWhatItDoes("Residents scan an item, learn which bin it belongs in, and earn points for completed recycling missions.");
      setHowItWorks("A React app sends item photos to a vision model, which returns the bin type; a Flask API tracks points.");
      setSponsorRequirements("");
      setTargetAward("best_overall");
      setTargetHackathon("shellhacks2025:2025");
      setPrizeEvent("shellhacks2026:2026");
    }
  };

  const handleAnalyze = async (e: React.FormEvent) => {
    e.preventDefault();
    setAnalyzing(true);
    setError(null);
    setResult(null);

    let payload: Record<string, unknown>;

    if (analysisMode === "idea") {
      if (!ideaDescription.trim()) {
        setError("Please describe what you are thinking of building.");
        setAnalyzing(false);
        return;
      }
      payload = {
        analysis_mode: "idea",
        prize_targeting_mode: prizeTargetingMode,
        event_id: targetHackathon,
        prize_event_id: prizeEvent,
        award_id: prizeTargetingMode === "specific" ? targetAward : "best_overall",
        idea: {
          description: ideaDescription.trim(),
          technologies_of_interest: technologiesOfInterest
            ? technologiesOfInterest
                .split(",")
                .map((t) => t.trim())
                .filter(Boolean)
            : [],
        },
      };
    } else {
      // Resolve URLs from primaryLink if set
      let finalGithub = githubUrl.trim();
      let finalDevpost = devpostUrl.trim();
      let finalDemo = demoUrl.trim();
      let finalDeployment = deploymentUrl.trim();

      if (projectInputSubmode === "link" && primaryLink.trim()) {
        const link = primaryLink.trim();
        if (link.includes("github.com") && !finalGithub) finalGithub = link;
        else if (link.includes("devpost.com") && !finalDevpost) finalDevpost = link;
        else if ((link.includes("youtube.com") || link.includes("youtu.be") || link.includes("loom.com")) && !finalDemo) finalDemo = link;
        else if (!finalDeployment && !finalGithub && !finalDevpost) finalDeployment = link;
      }

      payload = {
        analysis_mode: "project",
        event_id: targetHackathon,
        prize_event_id: prizeEvent,
        award_id: targetAward,
        input_mode: projectInputSubmode,
        github_url: finalGithub || undefined,
        devpost_url: finalDevpost || undefined,
        demo_url: finalDemo || undefined,
        deployment_url: finalDeployment || undefined,
        sponsor_requirements: sponsorRequirements.trim() || undefined,
        project: {
          name: name.trim(),
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
    }

    // Analytics: structured metadata only. Never the idea text, descriptions, or URLs.
    const analyticsCtx = {
      mode: analysisMode,
      event_id: safeEventId(targetHackathon),
      prize_event: safePrizeEventId(prizeEvent),
      input_type: inputTypeFor({
        mode: analysisMode,
        manualSubmode: projectInputSubmode === "manual",
        github: Boolean(payload.github_url),
        devpost: Boolean(payload.devpost_url),
      }),
      prize_targeting:
        analysisMode === "idea" ? (prizeTargetingMode === "specific" ? "specific" : "automatic") : "none",
      has_repo: Boolean(payload.github_url),
      has_demo: Boolean(payload.demo_url || payload.deployment_url),
    } as const;
    const startedAt = performance.now();
    let failureTracked = false;
    const trackFailure = (stage: FailureStage, cls: StatusClass) => {
      failureTracked = true;
      trackAnalysisFailed({
        mode: analyticsCtx.mode,
        event_id: analyticsCtx.event_id,
        input_type: analyticsCtx.input_type,
        failure_stage: stage,
        http_status_class: cls,
      });
    };
    trackAnalysisStarted(analyticsCtx);

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        trackFailure(failureStageFor(res.status, res.headers.get("x-failure-stage")), statusClass(res.status));
        const errData = await res.json().catch(() => ({}));
        const detail = typeof errData.detail === "string" ? errData.detail : "";
        if (detail) throw new Error(detail);
        if (res.status === 429) throw new Error("Too many reviews in a short time. Wait a minute and try again.");
        if (res.status >= 500) throw new Error("Something went wrong on our side. Try again in a moment.");
        throw new Error("We couldn't review that. Check your input and try again.");
      }

      const data: AnalysisResult = await res.json();
      if (!data || !data.recommendations) {
        trackFailure("unknown", "5xx");
        throw new Error("We couldn't finish that review. Try again in a moment.");
      }
      setResult(data);
      trackAnalysisCompleted({
        ...analyticsCtx,
        duration_bucket: durationBucket(performance.now() - startedAt),
        jev_used: data.telemetry?.jev_used ?? false,
        gemini_used: data.telemetry?.gemini_used ?? false,
        fallback_used: data.telemetry?.fallback_used ?? false,
        result_quality: data.telemetry?.result_quality ?? "partial",
      });
    } catch (err: unknown) {
      const isNetwork = err instanceof TypeError;
      if (!failureTracked) trackFailure("unknown", isNetwork ? "network" : "5xx");
      setError(
        isNetwork
          ? "We couldn't reach the review service. Check your connection and try again."
          : err instanceof Error
          ? err.message
          : "Something went wrong. Try again."
      );
    } finally {
      setAnalyzing(false);
    }
  };

  const resetAnalysis = () => {
    setResult(null);
    setError(null);
  };

  // Analytics: record that the prize-fit section was actually seen (once per result).
  const prizeSectionRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!result || result.analysis_mode !== "idea" || !result.prize_fits) return;
    const el = prizeSectionRef.current;
    if (!el) return;
    let fired = false;
    const fire = () => {
      if (fired) return;
      fired = true;
      const shown = (result.prize_fits?.top_fits ?? []).filter((f) =>
        ["very_strong", "strong", "moderate"].includes(f.fit_level)
      ).length;
      trackPrizeFitViewed({
        event_id: safeEventId(targetHackathon),
        prize_event: safePrizeEventId(prizeEvent),
        fit_count: Math.min(shown, 3),
        automatic_targeting: result.prize_fits?.targeting_mode === "auto",
      });
    };
    if (typeof IntersectionObserver === "undefined") {
      fire();
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          fire();
          io.disconnect();
        }
      },
      { threshold: 0.3 }
    );
    io.observe(el);
    return () => io.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result]);

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
              href="https://github.com/Aaryan1524/HackBench"
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
            {/* Hero Section */}
            <section className="mb-14 md:mb-20 max-w-3xl">
              <div className="h-[2px] w-12 bg-gradient-to-r from-amber-600 via-rose-500 to-sky-600 mb-8" />
              <h1 className="font-serif text-5xl sm:text-7xl font-normal tracking-[-0.025em] leading-[1.06] text-ink text-balance">
                {analysisMode === "idea" ? (
                  <>
                    Know what to build
                    <br />
                    before the hackathon starts.
                  </>
                ) : (
                  <>
                    See how your project
                    <br />
                    looks to judges.
                  </>
                )}
              </h1>
              <p className="mt-6 text-lg sm:text-xl text-ink-secondary font-normal leading-relaxed max-w-2xl text-pretty">
                See what is strong, what is missing, and what to do next, based on past ShellHacks projects and published prize criteria.
              </p>
            </section>

            {/* Input Container */}
            <section className="max-w-2xl">
              {/* Primary Mode Switcher */}
              <div role="tablist" aria-label="What do you want reviewed?" className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-8">
                {(
                  [
                    { id: "idea", title: "Review an idea", hint: "For before you start building." },
                    { id: "project", title: "Review a project", hint: "For when you already have something working." },
                  ] as const
                ).map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    role="tab"
                    aria-selected={analysisMode === m.id}
                    onClick={() => {
                      if (m.id !== analysisMode) trackModeSelected({ mode: m.id });
                      setAnalysisMode(m.id);
                      setError(null);
                    }}
                    className={`text-left px-4 py-3.5 rounded border transition-colors cursor-pointer ${
                      analysisMode === m.id
                        ? "border-ink bg-white shadow-xs"
                        : "border-edge bg-transparent hover:border-ink"
                    }`}
                  >
                    <span className={`block text-sm ${analysisMode === m.id ? "font-semibold text-ink" : "font-medium text-ink-secondary"}`}>
                      {m.title}
                    </span>
                    <span className="block text-xs text-ink-secondary mt-0.5">{m.hint}</span>
                  </button>
                ))}
              </div>

              {/* Error Notice */}
              {error && (
                <div className="mb-8 p-4 bg-white border border-rose-300 text-rose-900 rounded text-sm leading-relaxed">
                  {error}
                </div>
              )}

              {/* Form */}
              <form onSubmit={handleAnalyze} className="space-y-8">
                {analysisMode === "idea" ? (
                  /* ======================================================== */
                  /* FLOW 1: IDEA REVIEW MODE (PRIMARY)                      */
                  /* ======================================================== */
                  <div className="space-y-6">
                    <div>
                      <label htmlFor="ideaDescription" className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-2">
                        Tell us what you&apos;re thinking of building <span className="text-rose-600">*</span>
                      </label>
                      <textarea
                        id="ideaDescription"
                        rows={5}
                        value={ideaDescription}
                        onChange={(e) => setIdeaDescription(e.target.value)}
                        required
                        placeholder="e.g. An app that turns a photo of your fridge into a dinner recipe, and lists what you are missing."
                        className="w-full px-4 py-3.5 bg-white border border-edge rounded text-base text-ink placeholder:text-ink-muted focus:outline-none focus:border-ink transition-colors resize-y leading-relaxed"
                      />
                      <p className="mt-2 text-xs text-ink-secondary">
                        Say who it is for and what happens from start to finish. A few sentences is enough. No GitHub or demo needed.
                      </p>
                    </div>

                    <div>
                      <label htmlFor="technologiesOfInterest" className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-2">
                        Anything you already want to use? (optional)
                      </label>
                      <input
                        id="technologiesOfInterest"
                        type="text"
                        value={technologiesOfInterest}
                        onChange={(e) => setTechnologiesOfInterest(e.target.value)}
                        placeholder="“ElevenLabs, Google Cloud, Twilio…”"
                        className="w-full px-4 py-3 bg-white border border-edge rounded text-sm text-ink placeholder:text-ink-muted focus:outline-none focus:border-ink"
                      />
                      <p className="mt-1.5 text-xs text-ink-secondary">
                        Optional. Helps us match your idea to sponsor challenges.
                      </p>
                    </div>
                  </div>
                ) : (
                  /* ======================================================== */
                  /* FLOW 2: PROJECT REVIEW MODE (SECONDARY / PRESERVED)      */
                  /* ======================================================== */
                  <div className="space-y-6">
                    {/* Submode Switcher: Links vs Manual */}
                    <div className="flex items-center gap-2 mb-2 text-xs text-ink-secondary">
                      <span>Input format:</span>
                      <button
                        type="button"
                        onClick={() => setProjectInputSubmode("link")}
                        className={`px-2.5 py-1 rounded border transition-colors cursor-pointer ${
                          projectInputSubmode === "link"
                            ? "border-ink text-ink font-medium bg-canvas"
                            : "border-edge hover:border-ink hover:text-ink"
                        }`}
                      >
                        Public links
                      </button>
                      <button
                        type="button"
                        onClick={() => setProjectInputSubmode("manual")}
                        className={`px-2.5 py-1 rounded border transition-colors cursor-pointer ${
                          projectInputSubmode === "manual"
                            ? "border-ink text-ink font-medium bg-canvas"
                            : "border-edge hover:border-ink hover:text-ink"
                        }`}
                      >
                        Manual details
                      </button>
                    </div>

                    {projectInputSubmode === "link" ? (
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
                            We&apos;ll pull the repository code and public submission information we can find.
                          </p>
                        </div>

                        <div>
                          <label htmlFor="quickDescription" className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-2">
                            What does it do? (optional)
                          </label>
                          <input
                            id="quickDescription"
                            type="text"
                            value={whatItDoes}
                            onChange={(e) => setWhatItDoes(e.target.value)}
                            placeholder="One sentence. Helps if your repo has no README."
                            className="w-full px-3.5 py-2.5 bg-white border border-edge rounded text-sm text-ink placeholder:text-ink-muted focus:outline-none focus:border-ink"
                          />
                        </div>

                        {/* Secondary Sources (Expandable) */}
                        <div>
                          {!showAdditionalSources ? (
                            <button
                              type="button"
                              onClick={() => setShowAdditionalSources(true)}
                              className="text-xs text-ink-secondary hover:text-ink underline underline-offset-4 cursor-pointer"
                            >
                              + Add another source (GitHub, Devpost, Demo, Deployment)
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
                              <div>
                                <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-1">
                                  Live deployment URL
                                </label>
                                <input
                                  type="url"
                                  value={deploymentUrl}
                                  onChange={(e) => setDeploymentUrl(e.target.value)}
                                  placeholder="https://my-project.vercel.app"
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
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-6">
                        <div>
                          <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-2">
                            Project name <span className="text-rose-600">*</span>
                          </label>
                          <input
                            type="text"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="e.g. TrailBuddy"
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
                            placeholder="e.g. First-year college students"
                            required
                            className="w-full px-4 py-3 bg-white border border-edge rounded text-base text-ink focus:outline-none focus:border-ink"
                          />
                        </div>

                        <div>
                          <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-2">
                            Sponsor or track requirements (optional)
                          </label>
                          <textarea
                            rows={3}
                            value={sponsorRequirements}
                            onChange={(e) => setSponsorRequirements(e.target.value)}
                            placeholder="Paste the sponsor challenge, required API/SDK, or prize criteria..."
                            className="w-full px-4 py-3 bg-white border border-edge rounded text-base text-ink focus:outline-none focus:border-ink resize-y"
                          />
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
                              GitHub repository (optional)
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
                  </div>
                )}

                {/* Baseline & Prize Targeting Selectors */}
                {analysisMode === "idea" ? (
                  <div className="pt-6 border-t border-edge space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-1.5">
                          Prizes from
                        </label>
                        <select
                          value={prizeEvent}
                          onChange={(e) => setPrizeEvent(e.target.value)}
                          className="w-full px-3.5 py-2.5 bg-white border border-edge rounded text-sm text-ink focus:outline-none focus:border-ink cursor-pointer"
                        >
                          {PRIZE_EVENT_OPTIONS.map((o) => (
                            <option key={o.id} value={o.id}>
                              {o.label}
                            </option>
                          ))}
                        </select>
                        <p className="mt-1.5 text-xs text-ink-secondary">
                          Whose sponsor challenges and awards your idea is matched against.
                        </p>
                      </div>

                      <div>
                        <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-1.5">
                          Compare against
                        </label>
                        <select
                          value={targetHackathon}
                          onChange={(e) => setTargetHackathon(e.target.value)}
                          className="w-full px-3.5 py-2.5 bg-white border border-edge rounded text-sm text-ink focus:outline-none focus:border-ink cursor-pointer"
                        >
                          {BASELINE_OPTIONS.map((o) => (
                            <option key={o.id} value={o.id}>
                              {o.label}
                            </option>
                          ))}
                        </select>
                        <p className="mt-1.5 text-xs text-ink-secondary">
                          The past results your idea is compared with. ShellHacks 2026 has none yet.
                        </p>
                      </div>

                      <div>
                        <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-1.5">
                          Prize targeting
                        </label>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => setPrizeTargetingMode("auto")}
                            className={`flex-1 px-3 py-2 text-xs rounded border transition-colors cursor-pointer text-center ${
                              prizeTargetingMode === "auto"
                                ? "border-ink text-ink font-medium bg-canvas"
                                : "border-edge text-ink-secondary hover:border-ink hover:text-ink bg-white"
                            }`}
                          >
                            Find the best fits for me
                          </button>
                          <button
                            type="button"
                            onClick={() => setPrizeTargetingMode("specific")}
                            className={`flex-1 px-3 py-2 text-xs rounded border transition-colors cursor-pointer text-center ${
                              prizeTargetingMode === "specific"
                                ? "border-ink text-ink font-medium bg-canvas"
                                : "border-edge text-ink-secondary hover:border-ink hover:text-ink bg-white"
                            }`}
                          >
                            Choose a specific prize
                          </button>
                        </div>
                      </div>
                    </div>

                    {prizeTargetingMode === "auto" ? (
                      <p className="text-xs text-ink-muted">
                        We&apos;ll compare your idea with every ShellHacks track and sponsor challenge that has published criteria.
                      </p>
                    ) : (
                      <div className="pt-1">
                        <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-1.5">
                          Select target prize or track
                        </label>
                        <select
                          value={targetAward}
                          onChange={(e) => setTargetAward(e.target.value)}
                          className="w-full sm:max-w-md px-3.5 py-2.5 bg-white border border-edge rounded text-sm text-ink focus:outline-none focus:border-ink cursor-pointer"
                        >
                          {availablePrizes.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.label}
                            </option>
                          ))}
                        </select>
                        <p className="mt-1.5 text-xs text-ink-secondary">
                          Checked against this award&apos;s published criteria.
                        </p>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-4 border-t border-edge">
                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-1.5">
                        Prizes from
                      </label>
                      <select
                        value={prizeEvent}
                        onChange={(e) => setPrizeEvent(e.target.value)}
                        className="w-full px-3.5 py-2.5 bg-white border border-edge rounded text-sm text-ink focus:outline-none focus:border-ink cursor-pointer"
                      >
                        {PRIZE_EVENT_OPTIONS.map((o) => (
                          <option key={o.id} value={o.id}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-1.5">
                        Compare against
                      </label>
                      <select
                        value={targetHackathon}
                        onChange={(e) => setTargetHackathon(e.target.value)}
                        className="w-full px-3.5 py-2.5 bg-white border border-edge rounded text-sm text-ink focus:outline-none focus:border-ink cursor-pointer"
                      >
                        {BASELINE_OPTIONS.map((o) => (
                          <option key={o.id} value={o.id}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-wider text-ink-secondary mb-1.5">
                        Target Track / Award
                      </label>
                      <select
                        value={targetAward}
                        onChange={(e) => setTargetAward(e.target.value)}
                        className="w-full px-3.5 py-2.5 bg-white border border-edge rounded text-sm text-ink focus:outline-none focus:border-ink cursor-pointer"
                      >
                        {availablePrizes.map((track) => (
                          <option key={track.id} value={track.id}>
                            {track.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                )}

                {/* Submit Action */}
                <div className="pt-2 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                  <button
                    type="submit"
                    className="inline-flex items-center justify-center px-6 py-3.5 bg-ink text-white font-medium rounded text-sm hover:bg-neutral-800 transition-colors shadow-xs cursor-pointer"
                  >
                    {analysisMode === "idea" ? "Review this idea →" : "Review this project →"}
                  </button>

                  <div className="text-xs text-ink-secondary">
                    Or try a sample:{" "}
                    <button
                      type="button"
                      onClick={() => loadSample("idea")}
                      className="text-ink font-medium underline underline-offset-2 hover:text-neutral-700 cursor-pointer"
                    >
                      Random Idea
                    </button>{" "}
                    ·{" "}
                    <button
                      type="button"
                      onClick={() => loadSample("ecoquest")}
                      className="text-ink font-medium underline underline-offset-2 hover:text-neutral-700 cursor-pointer"
                    >
                      EcoQuest (Project)
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
              {analysisMode === "idea" ? "Reviewing your idea." : "Looking at your project."}
            </h2>
            <div className="space-y-4">
              {activeSteps.map((step, idx) => (
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
                onClick={() => {
                  trackReviewAgainClicked({ mode: result.analysis_mode === "idea" ? "idea" : "project" });
                  resetAnalysis();
                }}
                className="text-xs text-ink-secondary hover:text-ink font-medium flex items-center gap-1.5 cursor-pointer"
              >
                ← {result.analysis_mode === "idea" ? "Review another idea" : "Review another project"}
              </button>
            </div>

            {/* 1. Results Hero */}
            <section className="max-w-3xl border-b border-edge pb-12 sm:pb-16">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-xs uppercase font-semibold tracking-widest text-ink font-mono">
                  {result.analysis_mode === "idea" ? "Your Idea" : "Your Project"} · {result.project?.name || "Candidate"}
                </span>
                <span className="text-edge">·</span>
                <span className="text-xs uppercase font-medium tracking-wider text-ink-secondary">
                  What stands out
                </span>
              </div>
              <h1 className="font-serif text-4xl sm:text-6xl font-normal tracking-tight leading-[1.1] text-ink text-balance whitespace-pre-line">
                {getEditorialHeadline(result)}
              </h1>
              {result.analysis_mode !== "idea" && result.recommendations?.summary && (
                <p className="mt-6 text-lg sm:text-xl text-ink-secondary leading-relaxed text-pretty">
                  {result.recommendations.summary}
                </p>
              )}
            </section>

            {result.notes && result.notes.length > 0 && (
              <section className="max-w-3xl -mt-8 space-y-2" aria-label="Things to know about this review">
                {result.notes.map((n) => (
                  <p key={n} className="text-sm text-ink-secondary border-l-2 border-edge pl-3 leading-relaxed">
                    {n}
                  </p>
                ))}
              </section>
            )}

            {/* 2. Top Analysis: 3 Concise Blocks */}
            <section className="grid grid-cols-1 md:grid-cols-3 gap-8 sm:gap-12 border-b border-edge pb-16">
              <div>
                <span className="text-xs uppercase font-semibold tracking-wider text-ink-secondary block mb-3 font-mono">
                  Strongest
                </span>
                <h3 className="font-serif text-xl sm:text-2xl font-normal text-ink mb-2">
                  {result.recommendations?.strengths?.[0]?.title || "Not enough to judge yet"}
                </h3>
                <p className="text-sm text-ink-secondary leading-relaxed">
                  {result.recommendations?.strengths?.[0]?.evidence ||
                    "Add a project description or a link to a submission page to see what stands out."}
                </p>
              </div>

              <div>
                <span className="text-xs uppercase font-semibold tracking-wider text-ink-secondary block mb-3 font-mono">
                  Biggest Gap
                </span>
                <h3 className="font-serif text-xl sm:text-2xl font-normal text-ink mb-2">
                  {result.recommendations?.gaps?.[0]?.title || "No clear gap found"}
                </h3>
                <p className="text-sm text-ink-secondary leading-relaxed">
                  {result.recommendations?.gaps?.[0]?.evidence ||
                    "Nothing in what was submitted points to a specific gap."}
                </p>
              </div>

              <div>
                <span className="text-xs uppercase font-semibold tracking-wider text-ink-secondary block mb-3 font-mono">
                  {result.analysis_mode === "idea" ? "Build First" : "Improve Next"}
                </span>
                {result.analysis_mode === "idea" && result.recommendations?.build_first ? (
                  <ol className="space-y-2 text-sm text-ink leading-snug">
                    {result.recommendations.build_first.split("→").map((step, i, all) => (
                      <li key={i} className="flex items-start gap-2.5">
                        <span className="font-mono text-xs text-ink-muted pt-0.5">
                          {i < all.length - 1 ? `${i + 1}` : "✓"}
                        </span>
                        <span>{step.trim()}</span>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <>
                    <h3 className="font-serif text-xl sm:text-2xl font-normal text-ink mb-2 whitespace-pre-line">
                      {result.recommendations?.next_actions[0]?.action || "Clarify the core loop"}
                    </h3>
                    <p className="text-sm text-ink-secondary leading-relaxed">
                      {result.recommendations?.next_actions[0]?.reason ||
                        "Proves the complete user outcome before detailing the underlying technical architecture."}
                    </p>
                  </>
                )}
              </div>
            </section>

            {/* 3. Where This Idea Fits (Criteria Alignment) */}
            {result.prize_fits && (
              <section ref={prizeSectionRef} className="max-w-3xl border-b border-edge pb-16 space-y-8">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xs uppercase font-semibold tracking-wider text-ink-secondary font-mono">
                      Where this idea fits
                    </span>
                    <span className="text-edge">·</span>
                    <span className="text-xs uppercase font-medium tracking-wider text-ink-muted">
                      Documented tracks &amp; sponsors
                    </span>
                  </div>
                  <h2 className="font-serif text-2xl sm:text-3xl font-normal text-ink">
                    Closest documented fits
                  </h2>
                  <p className="mt-1 text-sm text-ink-secondary">
                    {result.prize_fits.targeting_mode === "specific"
                      ? "Alignment against your chosen award based on documented requirements."
                      : "Documented hackathon tracks and sponsor categories aligned with your concept. Ranked by how closely they match the published criteria."}
                  </p>
                </div>

                {/* If no strong fit exists */}
                {(!result.prize_fits.top_fits ||
                  result.prize_fits.top_fits.length === 0 ||
                  !result.prize_fits.top_fits.some(
                    (f) => f.fit_level === "very_strong" || f.fit_level === "strong"
                  )) && (
                  <div className="p-4 bg-canvas-subtle border border-edge rounded text-sm text-ink-secondary leading-relaxed">
                    No clearly strong sponsor fit yet. Best Overall currently aligns better than the available sponsor tracks based on the documented criteria.
                  </div>
                )}

                {/* Top Fits Cards (Up to 3) */}
                {result.prize_fits.top_fits && result.prize_fits.top_fits.length > 0 && (
                  <div className="space-y-6">
                    {result.prize_fits.top_fits
                      .filter((f) => ["very_strong", "strong", "moderate"].includes(f.fit_level))
                      .slice(0, 3)
                      .map((fit, idx) => {
                      const isStrong = fit.fit_level === "very_strong" || fit.fit_level === "strong";
                      const isModerate = fit.fit_level === "moderate";
                      return (
                        <div
                          key={fit.prize_id || idx}
                          className="border border-edge rounded-lg bg-white p-6 sm:p-7 shadow-xs space-y-5"
                        >
                          {/* Header: Rank + Title + Fit Badge */}
                          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 border-b border-edge pb-4">
                            <div className="flex items-start gap-3">
                              <span className="font-mono text-xs font-semibold text-ink-muted pt-1">
                                {String(idx + 1).padStart(2, "0")}
                              </span>
                              <div>
                                <h3 className="font-serif text-xl sm:text-2xl font-normal text-ink">
                                  {fit.award_title}
                                </h3>
                                {fit.sponsor_name && (
                                  <span className="text-xs text-ink-secondary block mt-0.5">
                                    Sponsor: <span className="font-medium text-ink">{fit.sponsor_name}</span>
                                  </span>
                                )}
                              </div>
                            </div>

                            <div className="flex flex-wrap items-center gap-2 self-start sm:self-auto">
                              {fit.sponsor_tech_role === "central" && (
                                <span className="px-2.5 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200">
                                  Central dependency
                                </span>
                              )}
                              {fit.sponsor_tech_role === "decorative" && (
                                <span className="px-2.5 py-0.5 rounded text-xs font-medium bg-amber-50 text-amber-800 border border-amber-200">
                                  Sponsor tech is a side feature
                                </span>
                              )}
                              <span
                                className={`px-2.5 py-0.5 rounded text-xs font-medium ${
                                  isStrong
                                    ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                                    : isModerate
                                    ? "bg-neutral-100 text-neutral-800 border border-neutral-200"
                                    : "bg-amber-50 text-amber-900 border border-amber-200"
                                }`}
                              >
                                {fit.fit_label}
                              </span>
                            </div>
                          </div>

                          {/* Why it fits / Why it may not fit */}
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                            <div className="p-3.5 bg-canvas-subtle rounded border border-edge">
                              <span className="text-xs font-semibold uppercase tracking-wider text-emerald-800 block mb-1">
                                Why it fits
                              </span>
                              <p className="text-ink leading-relaxed">
                                {fit.why_it_fits}
                              </p>
                            </div>

                            <div className="p-3.5 bg-canvas-subtle rounded border border-edge">
                              <span className="text-xs font-semibold uppercase tracking-wider text-ink-secondary block mb-1">
                                Main gap / Why it may not fit
                              </span>
                              <p className="text-ink-secondary leading-relaxed">
                                {fit.why_it_may_not_fit}
                              </p>
                            </div>
                          </div>

                          {/* What must be demonstrated */}
                          {fit.what_must_be_demonstrated && fit.what_must_be_demonstrated.length > 0 && (
                            <div className="space-y-1.5">
                              <span className="text-xs font-semibold uppercase tracking-wider text-ink-secondary block font-mono">
                                Must visibly demonstrate
                              </span>
                              <ol className="list-decimal pl-5 text-sm text-ink-secondary space-y-1">
                                {fit.what_must_be_demonstrated.map((item, dIdx) => (
                                  <li key={dIdx}>{item}</li>
                                ))}
                              </ol>
                            </div>
                          )}

                        </div>
                      );
                    })}
                  </div>
                )}
              </section>
            )}

            {/* 4. Comparison Table (project mode; idea mode keeps it inside "Why this analysis?") */}
            {result.analysis_mode !== "idea" && <ComparisonSection result={result} />}

            {/* 5. Criteria Alignment (Project Mode) */}
            {result.analysis_mode === "project" && (
              <section className="max-w-2xl border-b border-edge pb-16">
                <h2 className="font-serif text-2xl sm:text-3xl font-normal text-ink mb-4">
                  Alignment with {result.criteria_alignment?.target_award || "your target award"}
                </h2>
                <p className="text-sm sm:text-base text-ink-secondary leading-relaxed mb-6">
                  {result.criteria_alignment?.criteria_summary}
                </p>
                <div className="p-4 bg-white border border-edge rounded text-sm flex items-center justify-between">
                  <span className="text-ink font-medium">Documented Track Fit</span>
                  <span className="text-ink-secondary font-medium capitalize">
                    {result.criteria_alignment?.alignment_level}
                  </span>
                </div>
                {result.criteria_alignment?.sponsor_requirements && (
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
            )}

            {/* 5. What To Fix / Prioritize */}
            <section className="bg-night text-white rounded-xl p-8 sm:p-14 border border-night-edge">
              {result.analysis_mode === "idea" && (
                <span className="text-xs uppercase font-semibold tracking-widest text-neutral-400 font-mono block mb-4">
                  Before the hackathon
                </span>
              )}
              <h2 className="font-serif text-3xl sm:text-5xl font-normal tracking-tight text-white mb-10 text-balance">
                {result.analysis_mode === "idea" ? (
                  <>Do these three things first.</>
                ) : (
                  <>
                    What to fix
                    <br />
                    before judging.
                  </>
                )}
              </h2>

              <div className="space-y-8 max-w-2xl">
                {result.recommendations?.next_actions.slice(0, 3).map((action, idx) => (
                  <div key={action.action} className="flex items-start gap-5">
                    <span className="font-serif text-2xl text-neutral-500 font-light pt-0.5">
                      {String(idx + 1).padStart(2, "0")}
                    </span>
                    <div className="space-y-1.5">
                      <h3 className="text-base sm:text-lg font-medium text-neutral-100 whitespace-pre-line">
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

            {/* Idea mode: what to skip (only when the idea text points at something specific) */}
            {result.analysis_mode === "idea" && (result.recommendations?.dont_build_yet?.length ?? 0) > 0 && (
              <section className="max-w-3xl border-b border-edge pb-16">
                <span className="text-xs uppercase font-semibold tracking-wider text-ink-secondary block mb-3 font-mono">
                  Don&apos;t spend time on yet
                </span>
                <ul className="space-y-3">
                  {result.recommendations.dont_build_yet!.map((item) => {
                    const [label, ...rest] = item.split(" — ");
                    return (
                      <li key={item} className="text-sm sm:text-base text-ink leading-relaxed">
                        <strong className="font-medium">{label}</strong>
                        {rest.length > 0 && <span className="text-ink-secondary"> — {rest.join(" — ")}</span>}
                      </li>
                    );
                  })}
                </ul>
              </section>
            )}

            {/* 6. Technical Details & Evidence Drawer */}
            <section className="max-w-3xl pt-4">
              <details
                className="group border border-edge rounded bg-white p-5 cursor-pointer"
                onToggle={(e) => {
                  if (e.currentTarget.open) trackEvidenceOpened({ mode: result.analysis_mode === "idea" ? "idea" : "project" });
                }}
              >
                <summary className="text-xs uppercase font-semibold tracking-wider text-ink-secondary flex items-center justify-between focus:outline-none select-none">
                  <span>
                    {result.analysis_mode === "idea"
                      ? "Why this analysis?"
                      : "View the evidence behind this review"}
                  </span>
                  <span className="text-ink-muted group-open:rotate-180 transition-transform">↓</span>
                </summary>

                <div className="mt-6 pt-4 border-t border-edge space-y-6 text-sm">
                  {result.analysis_mode === "idea" ? (
                    <div className="space-y-4">
                      <div className="space-y-3">
                        <h3 className="text-xs uppercase font-semibold tracking-wider text-ink-secondary font-mono">
                          Historical evidence
                        </h3>
                        {result.historical_comparison?.takeaway ? (
                          <p className="text-sm text-ink leading-relaxed">{result.historical_comparison.takeaway}</p>
                        ) : (
                          <p className="text-sm text-ink-secondary leading-relaxed">
                            The historical data did not support a specific takeaway for this idea.
                          </p>
                        )}
                        {Object.values(result.judge_surface || {}).some(
                          (d) => d.provider !== "offline_calibrated" && d.provider !== "deterministic_rule"
                        ) && (
                          <ComparisonSection result={result} embedded />
                        )}
                      </div>

                      <div className="space-y-3 pt-4 border-t border-edge">
                        <h3 className="text-xs uppercase font-semibold tracking-wider text-ink-secondary font-mono">
                          Criteria sources
                        </h3>
                        <p className="text-sm text-ink-secondary leading-relaxed">
                          Prize fits use only documented prize descriptions and required technologies. Where a prize
                          has no published criteria, it is left out rather than guessed.
                        </p>
                        {result.criteria_alignment?.criteria_summary && (
                          <p className="text-xs text-ink-secondary leading-relaxed">
                            <strong className="text-ink font-medium">{result.criteria_alignment.target_award}:</strong>{" "}
                            {result.criteria_alignment.criteria_summary}
                          </p>
                        )}
                        {result.prize_fits?.top_fits
                          ?.filter((f) => f.documented_requirements?.length > 0)
                          .slice(0, 3)
                          .map((f) => (
                            <div key={f.prize_id} className="text-xs">
                              <span className="text-ink font-medium">{f.award_title}</span>
                              <div className="flex flex-wrap gap-1.5 mt-1">
                                {f.documented_requirements.map((req) => (
                                  <span key={req} className="px-2 py-0.5 bg-canvas border border-edge rounded text-ink-secondary">
                                    {req}
                                  </span>
                                ))}
                              </div>
                            </div>
                          ))}
                      </div>

                      {result.idea?.extracted && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs pt-4 border-t border-edge">
                          <div className="p-3.5 bg-canvas rounded border border-edge">
                            <span className="text-ink-muted block mb-1">Proposed Product</span>
                            <strong className="text-ink font-semibold">
                              {result.idea.extracted.proposed_product || "Not specified"}
                            </strong>
                          </div>
                          <div className="p-3.5 bg-canvas rounded border border-edge">
                            <span className="text-ink-muted block mb-1">Target User</span>
                            <strong className="text-ink font-semibold">
                              {result.idea.extracted.target_user || "Not specified"}
                            </strong>
                          </div>
                          <div className="p-3.5 bg-canvas rounded border border-edge sm:col-span-2">
                            <span className="text-ink-muted block mb-1">Core Workflow Loop</span>
                            <p className="text-ink font-medium leading-relaxed">
                              {result.idea.extracted.core_workflow || "Workflow outlined in idea description."}
                            </p>
                          </div>
                          {result.idea.extracted.intended_technologies && result.idea.extracted.intended_technologies.length > 0 && (
                            <div className="p-3.5 bg-canvas rounded border border-edge sm:col-span-2">
                              <span className="text-ink-muted block mb-1">Intended Technologies & Sponsors</span>
                              <div className="flex flex-wrap gap-1.5 mt-1">
                                {result.idea.extracted.intended_technologies.map((tech) => (
                                  <span key={tech} className="px-2 py-0.5 bg-white border border-edge rounded text-xs text-ink">
                                    {tech}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ) : (
                    <>
                      <p className="text-xs text-ink-secondary">
                        What we found in the repository and deployment:
                      </p>

                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
                        <div className="p-3 bg-canvas rounded border border-edge">
                          <span className="text-ink-muted block mb-1">Code volume</span>
                          <strong className="text-ink font-semibold">
                            ~{result.engineering?.approx_loc.toLocaleString()} LOC
                          </strong>
                        </div>
                        <div className="p-3 bg-canvas rounded border border-edge">
                          <span className="text-ink-muted block mb-1">Test files</span>
                          <strong className="text-ink font-semibold">
                            {result.engineering?.test_files_count} test files
                          </strong>
                        </div>
                        <div className="p-3 bg-canvas rounded border border-edge">
                          <span className="text-ink-muted block mb-1">API endpoints</span>
                          <strong className="text-ink font-semibold">
                            {result.engineering?.api_routes_count} routes
                          </strong>
                        </div>
                        <div className="p-3 bg-canvas rounded border border-edge">
                          <span className="text-ink-muted block mb-1">Deployment status</span>
                          <strong className="text-ink font-semibold capitalize">
                            {result.engineering?.deployment_verification || (result.engineering?.live_deployment_reachable ? "Reachable" : "None")}
                          </strong>
                        </div>
                      </div>

                      {result.engineering?.deployment_evidence && (
                        <div className="p-3 bg-canvas rounded border border-edge text-xs space-y-1">
                          <span className="text-ink-muted block font-semibold uppercase tracking-wider">
                            Deployment Evidence:
                          </span>
                          <p className="text-ink-secondary font-mono leading-relaxed">
                            {result.engineering.deployment_evidence}
                          </p>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </details>
            </section>
          </article>
        )}
      </main>

      {/* 3. Methodology Drawer */}
      {showMethodology && (
        <div className="fixed inset-0 z-50 bg-ink/40 backdrop-blur-xs flex items-center justify-center p-6">
          <div className="bg-canvas border border-edge rounded-xl max-w-2xl w-full p-8 sm:p-12 shadow-xl space-y-6">
            <div className="flex items-center justify-between border-b border-edge pb-4">
              <h2 className="font-serif text-2xl font-normal text-ink">Evaluation Methodology</h2>
              <button
                onClick={() => setShowMethodology(false)}
                className="text-ink-secondary hover:text-ink text-sm cursor-pointer"
              >
                Close ✕
              </button>
            </div>
            <div className="space-y-4 text-sm text-ink-secondary leading-relaxed">
              <p>
                <strong>HackBench</strong> evaluates hackathon submissions across two distinct workflows:
              </p>
              <ul className="list-disc pl-5 space-y-2">
                <li>
                  <strong>Review an idea (before you start building):</strong> Looks at the problem, the user, and the core workflow. It does not penalize an idea for having no code, repo, or demo yet. </li>
                <li>
                  <strong>Review a project (once you have something working):</strong> Looks at your public repository, live deployment, and demo, and compares them with past winners. Anything we can&apos;t see is marked as unavailable rather than weak. </li>
              </ul>
              <p className="text-xs text-ink-muted pt-4 border-t border-edge">
                Notice: HackBench is based on public evidence. It does not predict winners or guarantee outcomes. We measure anonymous usage (page visits and which actions are taken). We never collect what you type, your links, or your results.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 4. Editorial Footer */}
      <footer className="border-t border-edge py-8 mt-20">
        <div className="max-w-5xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between text-xs text-ink-secondary gap-4">
          <p>
            HackBench · Feedback on hackathon ideas and projects, based on past ShellHacks entries.
          </p>
          <div className="flex items-center gap-6">
            <button
              onClick={() => setShowMethodology(true)}
              className="hover:text-ink transition-colors cursor-pointer"
            >
              Methodology
            </button>
            <a
              href="https://github.com/Aaryan1524/HackBench"
              target="_blank"
              rel="noreferrer"
              className="hover:text-ink transition-colors"
            >
              GitHub
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
