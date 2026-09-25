"""
Backward compatibility module aliasing GeminiClient to ChatGPTClient.
"""
from .chatgpt import (
    ChatGPTClient,
    ChatGPTResponse,
    ChatGPTUsage,
    ParticipantReportSynthesis,
    SynthesizedStrength,
    SynthesizedGap,
    SynthesizedNextAction,
    GeminiClient,
    GeminiResponse,
    GeminiUsage,
)

__all__ = [
    "ChatGPTClient",
    "ChatGPTResponse",
    "ChatGPTUsage",
    "GeminiClient",
    "GeminiResponse",
    "GeminiUsage",
    "ParticipantReportSynthesis",
    "SynthesizedStrength",
    "SynthesizedGap",
    "SynthesizedNextAction",
]
