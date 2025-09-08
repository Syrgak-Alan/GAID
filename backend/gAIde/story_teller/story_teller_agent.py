# storyteller_agent/agent.py
from textwrap import dedent

from google.adk.agents import Agent

from .agent_tooling import research_attraction

def build_instruction(locale: str = "en-US") -> str:
    return dedent(f"""
        You are an orchestrator storyteller.
        - If the user message includes "facts", use them directly.
        - Otherwise, if the message includes "place" and "profile", FIRST call the tool `research_attraction` to obtain facts.
        Then write a {110}-{160} word, first-person, on-the-spot story about what the visitor is seeing here.
        Requirements:
          • Tone: warm, specific, no fluff. No URLs or citations.
          • Use at most 1–2 highlights and 1 nearby POI relevant to interests.
          • If closing within 60 minutes (from facts), mention it.
          • If locale is "de-DE", write German; else English.
        Input formats you may receive:
          A) {{"facts": ...}}  (preferred)
          B) {{"place": ..., "profile": ...}}  (then you MUST call research_attraction)
        Output:
        ===== STORY_SCRIPT =====
        (plain text only; no markdown fences)
    """)

def make_orchestrator(locale: str = "en-US") -> Agent:
    return Agent(
        name="orchestrator_storyteller",
        model="gemini-2.5-flash",
        instruction=build_instruction(locale),
        description="Orchestrates research (via tool) and writes a short on-site story.",
        tools=[research_attraction],
        # If supported by your ADK version, you can force plain text:
        # generation_config={"response_mime_type": "text/plain"},
    )

# Expose a default agent for `adk run storyteller_agent`
storry_teller = make_orchestrator(locale="en-US")
