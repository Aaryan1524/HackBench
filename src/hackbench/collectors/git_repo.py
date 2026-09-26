import os
import re
import shutil
import time
import subprocess
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
import httpx
import git
import urllib.parse

from ..models import (
    RepositoryMetrics,
    TechStackDetection,
    GitCommitTimeline,
    DeploymentCheck,
    ProvenanceRecord,
    EvidenceType,
)

MAX_REPO_BYTES = 300 * 1024 * 1024  # abort analysis of anything larger

from ..netsafety import safe_fetch_text

logger = logging.getLogger("hackbench.git_repo")

# File extension mappings to language
EXT_TO_LANG = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "CSS",
    ".java": "Java",
    ".cpp": "C++",
    ".c": "C",
    ".h": "C/C++",
    ".cs": "C#",
    ".go": "Go",
    ".rs": "Rust",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".dart": "Dart",
    ".php": "PHP",
    ".rb": "Ruby",
    ".sh": "Shell",
    ".sql": "SQL",
}

# Known library signatures
FRAMEWORK_SIGNATURES = {
    "react": ("frontend", "React"),
    "next": ("frontend", "Next.js"),
    "vue": ("frontend", "Vue.js"),
    "svelte": ("frontend", "Svelte"),
    "angular": ("frontend", "Angular"),
    "vite": ("frontend", "Vite"),
    "tailwindcss": ("frontend", "TailwindCSS"),
    "flutter": ("frontend", "Flutter"),
    "fastapi": ("backend", "FastAPI"),
    "flask": ("backend", "Flask"),
    "express": ("backend", "Express.js"),
    "django": ("backend", "Django"),
    "nestjs": ("backend", "NestJS"),
    "supabase": ("database", "Supabase"),
    "firebase": ("database", "Firebase"),
    "mongoose": ("database", "MongoDB"),
    "prisma": ("database", "Prisma"),
    "pg": ("database", "PostgreSQL"),
    "psycopg2": ("database", "PostgreSQL"),
    "sqlite": ("database", "SQLite"),
    "redis": ("database", "Redis"),
    "openai": ("model_provider", "OpenAI"),
    "anthropic": ("model_provider", "Anthropic"),
    "google-generativeai": ("model_provider", "Gemini"),
    "@google/genai": ("model_provider", "Gemini"),
    "groq": ("model_provider", "Groq"),
    "cohere": ("model_provider", "Cohere"),
    "elevenlabs": ("model_provider", "ElevenLabs"),
    "langchain": ("ai_ml", "LangChain"),
    "llamaindex": ("ai_ml", "LlamaIndex"),
    "torch": ("ai_ml", "PyTorch"),
    "tensorflow": ("ai_ml", "TensorFlow"),
    "transformers": ("ai_ml", "HuggingFace Transformers"),
    "sklearn": ("ai_ml", "Scikit-Learn"),
    "scikit-learn": ("ai_ml", "Scikit-Learn"),
    "arduino": ("hardware", "Arduino"),
    "pyserial": ("hardware", "Serial Communication"),
    "rpi.gpio": ("hardware", "Raspberry Pi GPIO"),
}

DEFAULT_IGNORE_DIRS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    ".expo",
    "data",
    "reports",
    ".gemini",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    "target",
    "vendor",
}


class RepositoryAnalyzer:
    """
    Clones or inspects public code repositories, extracting deterministic metrics,
    git commit history, stack dependencies, code quality signals, and live deployment status.
    """

    def __init__(
        self,
        repos_storage_dir: Path,
        max_files: Optional[int] = None,
        max_read_bytes: Optional[int] = None,
        budget_seconds: Optional[float] = None,
    ):
        """
        The limits are for analysing repositories submitted by strangers: at most `max_files` files are looked
        at, no file is read past `max_read_bytes`, and analysis stops after `budget_seconds`. All default to
        unlimited so the offline research pipeline behaves exactly as before.
        """
        self.repos_storage_dir = repos_storage_dir
        self.repos_storage_dir.mkdir(parents=True, exist_ok=True)
        self.max_files = max_files
        self.max_read_bytes = max_read_bytes
        self.budget_seconds = budget_seconds
        self._deadline: Optional[float] = None
        self.analysis_truncated = False

    def _walk(self, top: Path):
        """os.walk that stops at the file-count limit or the time budget (and says so)."""
        seen = 0
        for root, dirs, files in os.walk(top):
            if self._deadline is not None and time.monotonic() > self._deadline:
                self.analysis_truncated = True
                return
            if self.max_files is not None:
                room = self.max_files - seen
                if room <= 0:
                    self.analysis_truncated = True
                    return
                if len(files) > room:
                    files = files[:room]
                    self.analysis_truncated = True
            seen += len(files)
            yield root, dirs, files

    def _read(self, path: Path) -> str:
        """Read a text file, never more than max_read_bytes of it."""
        if self.max_read_bytes is None:
            return Path(path).read_text(encoding="utf-8", errors="ignore")
        with open(path, "rb") as fh:
            return fh.read(self.max_read_bytes).decode("utf-8", errors="ignore")

    def _count_lines(self, path: Path) -> int:
        if self.max_read_bytes is None:
            with open(path, "r", encoding="utf-8", errors="ignore") as fp:
                return sum(1 for _ in fp)
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            chunk = fh.read(self.max_read_bytes)
        lines = chunk.count(b"\n") + (1 if chunk and not chunk.endswith(b"\n") else 0)
        # Beyond the cap, extrapolate from what was read instead of reading it all.
        return int(lines * size / len(chunk)) if chunk and size > len(chunk) else lines

    def analyze_repository(
        self,
        repo_url: str,
        project_id: str,
        claimed_tech_tags: Optional[List[str]] = None,
        deployment_url: Optional[str] = None,
        project_name: Optional[str] = None,
        hackathon_start: Optional[datetime] = None,
        hackathon_end: Optional[datetime] = None,
    ) -> RepositoryMetrics:
        """
        Clones and analyzes a repository, capturing deterministic metrics.
        Never throws unhandled exceptions; returns a structured status on failure.
        """
        provenance = [
            ProvenanceRecord(
                claim=f"Inspected repository {repo_url}",
                evidence_type=EvidenceType.REPOSITORY,
                source=repo_url,
                location="root",
                confidence=1.0,
            )
        ]

        # Normalize git clone URL
        clean_url = repo_url.strip()
        clean_url = re.sub(r"/(?:tree|blob)/.*$", "", clean_url)
        if clean_url.endswith("/"):
            clean_url = clean_url[:-1]
        if not clean_url.endswith(".git") and ("github.com" in clean_url or "gitlab.com" in clean_url):
            clean_url += ".git"

        target_dir = self.repos_storage_dir / project_id

        # Clone if not already cloned
        repo = None
        if not target_dir.exists() or not (target_dir / ".git").exists():
            try:
                logger.info("Cloning repository into %s", target_dir)
                target_dir.mkdir(parents=True, exist_ok=True)
                env = {
                    **os.environ,
                    "GIT_TERMINAL_PROMPT": "0",
                    "GIT_ASKPASS": "/bin/echo",
                }
                env.update({
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_ALLOW_PROTOCOL": "https",  # nothing but https, even if a config or submodule asks
                    "GIT_LFS_SKIP_SMUDGE": "1",  # never download Git LFS payloads (can be gigabytes)
                })
                # Untrusted repo: https only, no hooks, no symlinks (a symlinked README must not read local files).
                cmd = [
                    "git", "-c", "core.symlinks=false", "-c", f"core.hooksPath={os.devnull}",
                    "-c", "protocol.allow=never", "-c", "protocol.https.allow=always",
                    "clone", "--depth", "50", "--single-branch", "--no-tags", clean_url, str(target_dir),
                ]
                proc = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25, text=True)
                if proc.returncode != 0:
                    raise RuntimeError(f"git clone failed (code {proc.returncode}): {proc.stderr[:200]}")
                repo = git.Repo(target_dir)
                if self._dir_size(target_dir) > MAX_REPO_BYTES:
                    shutil.rmtree(target_dir, ignore_errors=True)
                    return RepositoryMetrics(repo_url=repo_url, status="repo_too_large", provenance=provenance)
                self._remove_symlinks(target_dir)
            except subprocess.TimeoutExpired:
                logger.warning("Git clone timed out (repository may contain giant binary assets)")
                shutil.rmtree(target_dir, ignore_errors=True)
                dep_check = self._check_deployment(deployment_url, project_name=project_name) if deployment_url else None
                return RepositoryMetrics(
                    repo_url=repo_url,
                    status="clone_timeout_large_repo",
                    deployment_check=dep_check,
                    provenance=provenance,
                )
            except Exception as e:
                logger.warning("Failed to clone repository: %s", str(e)[:120])
                shutil.rmtree(target_dir, ignore_errors=True)
                status = "not_found" if "not found" in str(e).lower() else "private_or_failed"
                # Check deployment status anyway if deployment_url provided
                dep_check = self._check_deployment(deployment_url, project_name=project_name) if deployment_url else None
                return RepositoryMetrics(
                    repo_url=repo_url,
                    status=status,
                    deployment_check=dep_check,
                    provenance=provenance,
                )
        else:
            try:
                repo = git.Repo(target_dir)
            except Exception as e:
                logger.warning(f"Error opening existing git repo at {target_dir}: {e}")
                return RepositoryMetrics(
                    repo_url=repo_url,
                    status="corrupt_local_clone",
                    provenance=provenance,
                )

        self.analysis_truncated = False
        self._deadline = (time.monotonic() + self.budget_seconds) if self.budget_seconds else None

        # 1. Default branch & commit timeline
        try:
            default_branch = repo.active_branch.name
        except Exception:
            default_branch = "main"

        timeline = self._analyze_git_history(
            repo, hackathon_start=hackathon_start, hackathon_end=hackathon_end
        )

        # 2. File counts, LOC, languages
        file_count, approx_loc, loc_by_lang, langs = self._analyze_files_and_loc(target_dir)

        # 3. Stack & dependency detection
        stack = self._detect_tech_stack(target_dir)

        # 4. Rigor & Engineering indicators
        test_files, test_frameworks = self._detect_tests(target_dir)
        has_ci, ci_configs = self._detect_ci(target_dir)
        has_docker = (target_dir / "Dockerfile").exists() or (target_dir / "docker-compose.yml").exists() or (target_dir / "docker-compose.yaml").exists()
        has_env = (target_dir / ".env.example").exists() or (target_dir / ".env.sample").exists() or (target_dir / "example.env").exists()
        
        # README inspection
        readme_size = 0
        readme_excerpt = ""
        has_arch_docs = False
        for fname in ["README.md", "README", "readme.md", "Readme.md"]:
            rpath = target_dir / fname
            if rpath.exists():
                readme_size = rpath.stat().st_size
                try:
                    raw_readme = self._read(rpath)
                    readme_excerpt = self._readme_excerpt(raw_readme)
                    rtext = raw_readme.lower()
                    if any(term in rtext for term in ["architecture", "system design", "diagram", "workflow", "flowchart"]):
                        has_arch_docs = True
                except Exception:
                    pass
                break

        # API routes and Schema counts
        api_routes = self._count_api_routes(target_dir)
        db_schemas = self._count_db_schemas(target_dir)

        # Mock data & TODOs
        mock_indicators = self._detect_mock_data(target_dir)
        todo_count = self._count_todos(target_dir)
        boilerplate_indicators = self._detect_boilerplate(target_dir)

        # 5. Live deployment check
        dep_check = self._check_deployment(deployment_url, project_name=project_name) if deployment_url else None

        # 6. Consistency between claims and actual code
        consistency, explanation, actual_ints, unsupported = self._verify_consistency(
            claimed_tags=claimed_tech_tags or [],
            detected_stack=stack,
            target_dir=target_dir,
        )

        return RepositoryMetrics(
            repo_url=repo_url,
            status="accessible",
            default_branch=default_branch,
            file_count=file_count,
            approx_loc=approx_loc,
            loc_by_language=loc_by_lang,
            primary_languages=langs,
            tech_stack=stack,
            git_timeline=timeline,
            test_files_count=test_files,
            test_frameworks=test_frameworks,
            has_ci=has_ci,
            ci_configs=ci_configs,
            has_docker=has_docker,
            has_env_template=has_env,
            readme_size_bytes=readme_size,
            readme_excerpt=readme_excerpt,
            has_architecture_docs=has_arch_docs,
            api_routes_count=api_routes,
            db_migrations_or_schema_count=db_schemas,
            mock_data_detected=bool(mock_indicators),
            mock_data_indicators=mock_indicators,
            todo_fixme_count=todo_count,
            boilerplate_detected=bool(boilerplate_indicators),
            boilerplate_indicators=boilerplate_indicators,
            deployment_check=dep_check,
            consistency_with_claims=consistency,
            consistency_explanation=explanation,
            actual_integrations_found=actual_ints,
            readme_claims_unsupported_by_code=unsupported,
            provenance=provenance,
        )

    @staticmethod
    def _dir_size(path: Path) -> int:
        total = 0
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.lstat(os.path.join(root, f)).st_size
                except OSError:
                    pass
        return total

    @staticmethod
    def _remove_symlinks(path: Path) -> None:
        for root, dirs, files in os.walk(path):
            for name in dirs + files:
                full = os.path.join(root, name)
                if os.path.islink(full):
                    try:
                        os.unlink(full)
                    except OSError:
                        pass

    @staticmethod
    def _readme_excerpt(text: str, limit: int = 2500) -> str:
        """Readable prose from a README: no badges, images, HTML, code blocks, or bare link lines."""
        text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
        lines = [ln.strip() for ln in text.splitlines()]
        kept = [ln for ln in lines if ln and not re.fullmatch(r"[-=*_ |:#]+", ln)]
        return "\n".join(kept)[:limit].strip()

    def _analyze_git_history(
        self,
        repo: git.Repo,
        hackathon_start: Optional[datetime] = None,
        hackathon_end: Optional[datetime] = None,
    ) -> GitCommitTimeline:
        timeline = GitCommitTimeline()
        try:
            commits = list(repo.iter_commits())
        except Exception:
            timeline.history_is_squashed_or_minimal = True
            return timeline

        if not commits:
            timeline.history_is_squashed_or_minimal = True
            return timeline

        timeline.total_commits = len(commits)
        contributors = set()
        timestamps: List[datetime] = []
        messages: List[str] = []

        for c in commits:
            c_time = datetime.fromtimestamp(c.committed_date, tz=timezone.utc)
            timestamps.append(c_time)
            if c.author and c.author.name:
                contributors.add(c.author.name)
            messages.append(c.message.strip().lower())

        timestamps.sort()
        timeline.first_commit_time = timestamps[0]
        timeline.last_commit_time = timestamps[-1]
        timeline.contributors = list(contributors)
        timeline.contributor_count = len(contributors)
        timeline.commit_timestamps = timestamps

        # Commits during hackathon window
        if hackathon_start and hackathon_end:
            in_window = [t for t in timestamps if hackathon_start <= t <= hackathon_end]
            timeline.commits_in_window = len(in_window)
        else:
            timeline.commits_in_window = len(timestamps)

        # Detect squashed or single commit history
        if timeline.total_commits <= 2:
            timeline.history_is_squashed_or_minimal = True
            timeline.final_stage_focus = "squashed"
            return timeline

        # Deadline crunch ratio (commits in final 25% of timeline duration)
        duration = (timeline.last_commit_time - timeline.first_commit_time).total_seconds()
        if duration > 3600:
            late_threshold = timeline.first_commit_time.timestamp() + (0.75 * duration)
            late_commits = [t for t in timestamps if t.timestamp() >= late_threshold]
            timeline.deadline_crunch_ratio = round(len(late_commits) / len(timestamps), 2)

        # Final stage focus based on final 20% commit messages
        recent_count = max(2, int(len(messages) * 0.25))
        recent_msgs = " ".join(messages[:recent_count])  # repo.iter_commits returns newest first

        if any(w in recent_msgs for w in ["fix", "bug", "patch", "error", "solve"]):
            timeline.final_stage_focus = "debugging"
        elif any(w in recent_msgs for w in ["readme", "doc", "presentation", "video", "slide"]):
            timeline.final_stage_focus = "docs"
        elif any(w in recent_msgs for w in ["clean", "polish", "style", "css", "ui", "format"]):
            timeline.final_stage_focus = "polish"
        elif any(w in recent_msgs for w in ["integrate", "api", "connect", "hook"]):
            timeline.final_stage_focus = "integration"
        else:
            timeline.final_stage_focus = "features"

        return timeline

    def _analyze_files_and_loc(self, target_dir: Path) -> Tuple[int, int, Dict[str, int], List[str]]:
        file_count = 0
        approx_loc = 0
        loc_by_lang: Dict[str, int] = {}

        for root, dirs, files in self._walk(target_dir):
            dirs[:] = [d for d in dirs if d not in DEFAULT_IGNORE_DIRS]
            for f in files:
                file_count += 1
                ext = Path(f).suffix.lower()
                lang = EXT_TO_LANG.get(ext)
                if not lang:
                    continue

                f_path = Path(root) / f
                try:
                    # quick line count
                    lines = self._count_lines(f_path)
                    approx_loc += lines
                    loc_by_lang[lang] = loc_by_lang.get(lang, 0) + lines
                except Exception:
                    pass

        # Sort languages by LOC
        sorted_langs = [l for l, _ in sorted(loc_by_lang.items(), key=lambda item: item[1], reverse=True)]
        return file_count, approx_loc, loc_by_lang, sorted_langs

    def _detect_tech_stack(self, target_dir: Path) -> TechStackDetection:
        stack = TechStackDetection()
        all_deps = set()

        # Check package.json
        p_json = target_dir / "package.json"
        if p_json.exists():
            try:
                import json
                data = json.loads(self._read(p_json))
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                for d in deps:
                    all_deps.add(d.lower())
            except Exception:
                pass

        # Check requirements.txt, pyproject.toml
        req_txt = target_dir / "requirements.txt"
        if req_txt.exists():
            try:
                for line in self._read(req_txt).splitlines():
                    dep = re.split(r"[=<>]", line.strip())[0].strip().lower()
                    if dep and not dep.startswith("#"):
                        all_deps.add(dep)
            except Exception:
                pass

        # Scan code files for key import signatures
        for root, dirs, files in self._walk(target_dir):
            dirs[:] = [d for d in dirs if d not in DEFAULT_IGNORE_DIRS]
            for f in files:
                if f.endswith((".py", ".js", ".ts", ".jsx", ".tsx")):
                    try:
                        content = self._read(Path(root) / f)
                        for sig in FRAMEWORK_SIGNATURES:
                            pat = rf"(?:import\s+.*?\b{re.escape(sig)}\b|from\s+{re.escape(sig)}\b|require\s*\(\s*['\"][^'\"]*{re.escape(sig)}|from\s+['\"][^'\"]*{re.escape(sig)})"
                            if re.search(pat, content, re.IGNORECASE):
                                all_deps.add(sig)
                    except Exception:
                        pass

        # Categorize detected deps
        for dep in all_deps:
            for sig, (cat, name) in FRAMEWORK_SIGNATURES.items():
                if sig in dep:
                    if cat == "frontend" and name not in stack.frontend_frameworks:
                        stack.frontend_frameworks.append(name)
                    elif cat == "backend" and name not in stack.backend_frameworks:
                        stack.backend_frameworks.append(name)
                    elif cat == "database" and name not in stack.databases:
                        stack.databases.append(name)
                    elif cat == "model_provider" and name not in stack.model_providers:
                        stack.model_providers.append(name)
                    elif cat == "ai_ml" and name not in stack.ai_ml_libraries:
                        stack.ai_ml_libraries.append(name)
                    elif cat == "hardware" and name not in stack.hardware_components:
                        stack.hardware_components.append(name)

        stack.package_dependencies = sorted(list(all_deps))
        return stack

    def _detect_tests(self, target_dir: Path) -> Tuple[int, List[str]]:
        test_count = 0
        frameworks = set()
        test_patterns = [r"test_.*\.py$", r".*_test\.py$", r".*\.test\.[jt]sx?$", r".*\.spec\.[jt]sx?$"]

        for root, dirs, files in self._walk(target_dir):
            dirs[:] = [d for d in dirs if d not in DEFAULT_IGNORE_DIRS]
            for f in files:
                if any(re.match(pat, f) for pat in test_patterns):
                    test_count += 1
                    try:
                        content = self._read(Path(root) / f).lower()
                        if "pytest" in content:
                            frameworks.add("pytest")
                        if "unittest" in content:
                            frameworks.add("unittest")
                        if "jest" in content:
                            frameworks.add("jest")
                        if "describe(" in content:
                            frameworks.add("vitest/jest")
                    except Exception:
                        pass
        return test_count, list(frameworks)

    def _detect_ci(self, target_dir: Path) -> Tuple[bool, List[str]]:
        ci_configs = []
        gh_actions = target_dir / ".github" / "workflows"
        if gh_actions.exists() and any(gh_actions.iterdir()):
            ci_configs.append("github_actions")
        if (target_dir / ".gitlab-ci.yml").exists():
            ci_configs.append("gitlab_ci")
        return bool(ci_configs), ci_configs

    def _count_api_routes(self, target_dir: Path) -> int:
        count = 0
        patterns = [
            r"@(?:app|router)\.(?:get|post|put|delete|patch)\(",
            r"app\.(?:get|post|put|delete|patch)\(",
            r"router\.(?:get|post|put|delete|patch)\(",
            r"export\s+async\s+function\s+(?:GET|POST|PUT|DELETE)\(",
        ]
        regex = re.compile("|".join(patterns))

        for root, dirs, files in self._walk(target_dir):
            dirs[:] = [d for d in dirs if d not in DEFAULT_IGNORE_DIRS]
            for f in files:
                if f.endswith((".py", ".js", ".ts")):
                    try:
                        content = self._read(Path(root) / f)
                        count += len(regex.findall(content))
                    except Exception:
                        pass
        return count

    def _count_db_schemas(self, target_dir: Path) -> int:
        count = 0
        for root, dirs, files in self._walk(target_dir):
            dirs[:] = [d for d in dirs if d not in DEFAULT_IGNORE_DIRS]
            for f in files:
                if f.endswith((".prisma", ".sql")) or "migration" in f.lower() or "schema" in f.lower():
                    count += 1
        return count

    def _detect_mock_data(self, target_dir: Path) -> List[str]:
        indicators = []
        mock_keywords = ["mock_data", "dummy_data", "fake_users", "mock_response", "sample_json"]
        for root, dirs, files in self._walk(target_dir):
            dirs[:] = [d for d in dirs if d not in DEFAULT_IGNORE_DIRS]
            for f in files:
                f_lower = f.lower()
                if any(kw in f_lower for kw in mock_keywords):
                    indicators.append(f"Mock file: {f}")
                elif f.endswith((".json", ".js", ".ts", ".py")):
                    try:
                        sample = self._read(Path(root) / f)[:3000].lower()
                        if "mock response" in sample or "hardcoded for demo" in sample:
                            indicators.append(f"Mock text inside {f}")
                    except Exception:
                        pass
        return indicators[:10]

    def _count_todos(self, target_dir: Path) -> int:
        count = 0
        for root, dirs, files in self._walk(target_dir):
            dirs[:] = [d for d in dirs if d not in DEFAULT_IGNORE_DIRS]
            for f in files:
                if f.endswith((".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".c", ".cpp")):
                    try:
                        content = self._read(Path(root) / f)
                        count += len(re.findall(r"\b(?:TODO|FIXME|XXX)\b", content))
                    except Exception:
                        pass
        return count

    def _detect_boilerplate(self, target_dir: Path) -> List[str]:
        indicators = []
        p_json = target_dir / "package.json"
        if p_json.exists():
            try:
                import json
                data = json.loads(self._read(p_json))
                name = data.get("name", "")
                if any(b in name for b in ["create-react-app", "nextjs-starter", "my-app", "template", "vite-project"]):
                    indicators.append(f"Default starter package name: '{name}'")
            except Exception:
                pass
        return indicators

    def _check_deployment(self, url: str, project_name: Optional[str] = None) -> DeploymentCheck:
        check = DeploymentCheck(url=url)
        try:
            start_t = datetime.now()
            # Redirects are validated hop by hop and the body is capped: see safe_fetch_text.
            status_code, page_text, _final_url = safe_fetch_text(url, headers={"User-Agent": "HackBench-Forensics/1.0"})
            check.status_code = status_code
            check.is_reachable = status_code < 400
            check.response_time_ms = round((datetime.now() - start_t).total_seconds() * 1000, 1)

            if not check.is_reachable:
                check.deployment_url_status = "unreachable"
                check.deployment_verification = "unrelated"
                check.verification_evidence = f"Deployment URL returned HTTP error {status_code}."
                return check

            check.deployment_url_status = "reachable"

            # Parse domain to identify generic or unrelated domains
            parsed = urllib.parse.urlparse(url)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]

            generic_domains = {
                "example.com", "example.org", "example.net",
                "google.com", "github.com", "gitlab.com",
                "apple.com", "microsoft.com", "facebook.com",
                "wikipedia.org", "twitter.com", "x.com",
                "linkedin.com", "youtube.com", "youtu.be",
                "devpost.com", "medium.com"
            }

            if domain in generic_domains:
                check.deployment_verification = "unrelated"
                check.verification_evidence = (
                    f"URL is reachable (HTTP {status_code}), but points to an unrelated public domain '{domain}', "
                    "not a dedicated project deployment."
                )
                return check

            # Inspect page title and body content
            body_text = page_text[:100000] if page_text else ""
            title_match = re.search(r"<title[^>]*>(.*?)</title>", body_text, re.IGNORECASE | re.DOTALL)
            page_title = title_match.group(1).strip() if title_match else ""

            meta_desc_match = re.search(
                r'<meta\s+(?:name|property)=["\'](?:description|og:title|og:description)["\']\s+content=["\'](.*?)["\']',
                body_text,
                re.IGNORECASE,
            )
            meta_desc = meta_desc_match.group(1).strip() if meta_desc_match else ""

            if project_name and len(project_name.strip()) > 2:
                pname = project_name.strip().lower()
                pname_no_spaces = pname.replace(" ", "")

                if pname in page_title.lower() or pname in meta_desc.lower():
                    check.deployment_verification = "verified_project"
                    check.verification_evidence = f"Page title or meta description explicitly matches project '{project_name}'."
                elif pname_no_spaces in domain or pname in body_text.lower():
                    check.deployment_verification = "likely_project"
                    check.verification_evidence = f"Deployment domain or text content references '{project_name}'."
                else:
                    check.deployment_verification = "unknown"
                    check.verification_evidence = (
                        f"Server responded (HTTP {status_code}), but page title/content does not contain evidence "
                        f"matching project '{project_name}'."
                    )
            else:
                check.deployment_verification = "unknown"
                check.verification_evidence = f"Server responded (HTTP {status_code}), but no project name was provided to verify content."
        except Exception as e:
            # Never reflect the underlying error: it can reveal what is (or is not) listening behind a redirect.
            logger.warning("Deployment probe failed: %s", type(e).__name__)
            check.is_reachable = False
            check.deployment_url_status = "unreachable"
            check.deployment_verification = "unrelated"
            check.verification_evidence = "The deployment could not be reached."
        return check

    def check_deployment(self, url: str, project_name: Optional[str] = None) -> DeploymentCheck:
        return self._check_deployment(url, project_name=project_name)

    def _verify_consistency(
        self,
        claimed_tags: List[str],
        detected_stack: TechStackDetection,
        target_dir: Path,
    ) -> Tuple[str, str, List[str], List[str]]:
        all_detected = set(
            [f.lower() for f in detected_stack.frontend_frameworks]
            + [b.lower() for b in detected_stack.backend_frameworks]
            + [d.lower() for d in detected_stack.databases]
            + [m.lower() for m in detected_stack.model_providers]
            + [a.lower() for a in detected_stack.ai_ml_libraries]
            + [h.lower() for h in detected_stack.hardware_components]
            + [p.lower() for p in detected_stack.package_dependencies]
        )

        actual_integrations = []
        unsupported_claims = []

        for tag in claimed_tags:
            tag_clean = tag.lower().strip()
            # Check if tag is substantiated
            matched = any(tag_clean in det or det in tag_clean for det in all_detected)
            if matched:
                actual_integrations.append(tag)
            else:
                unsupported_claims.append(tag)

        if not claimed_tags:
            return "unverifiable", "No tech tags claimed on submission page.", [], []

        support_ratio = len(actual_integrations) / len(claimed_tags)
        if support_ratio >= 0.7:
            consistency = "consistent"
            exp = f"Strong evidence: {len(actual_integrations)}/{len(claimed_tags)} claimed technologies verified in codebase."
        elif support_ratio >= 0.3:
            consistency = "partial"
            exp = f"Partial evidence: {len(actual_integrations)}/{len(claimed_tags)} claimed technologies found in codebase."
        else:
            consistency = "inconsistent"
            exp = f"Weak evidence: Only {len(actual_integrations)}/{len(claimed_tags)} claimed technologies detected in codebase."

        return consistency, exp, actual_integrations, unsupported_claims
