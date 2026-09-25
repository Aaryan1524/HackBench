import time
from typing import Dict, Any, List
from pydantic import BaseModel, Field


class AnalysisUsageStats(BaseModel):
    jev_calls: int = 0
    jev_input_tokens: int = 0
    gemini_calls: int = 0
    gemini_prompt_tokens: int = 0
    gemini_completion_tokens: int = 0
    fallback_count: int = 0
    fallback_reasons: List[str] = Field(default_factory=list)
    total_duration_ms: float = 0.0
    cache_hits: int = 0

    def record_jev(self, input_tokens: int, duration_ms: float = 0.0):
        self.jev_calls += 1
        self.jev_input_tokens += input_tokens
        self.total_duration_ms += duration_ms

    def record_gemini(self, prompt_tokens: int, completion_tokens: int, duration_ms: float = 0.0):
        self.gemini_calls += 1
        self.gemini_prompt_tokens += prompt_tokens
        self.gemini_completion_tokens += completion_tokens
        self.total_duration_ms += duration_ms

    def record_fallback(self, reason: str):
        self.fallback_count += 1
        self.fallback_reasons.append(reason)

    def record_cache_hit(self):
        self.cache_hits += 1

    def to_summary_dict(self) -> Dict[str, Any]:
        return {
            "jev_classifications": self.jev_calls,
            "jev_input_tokens": self.jev_input_tokens,
            "gemini_calls": self.gemini_calls,
            "gemini_total_tokens": self.gemini_prompt_tokens + self.gemini_completion_tokens,
            "fallbacks_used": self.fallback_count,
            "cache_hits": self.cache_hits,
            "total_duration_ms": round(self.total_duration_ms, 1),
        }
