# agent_function.py
import asyncio, json, re, uuid
from typing import Any, Dict
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from Test.gAIde.story_teller.research_agent import make_agent  # your factory that bakes place/profile into instruction

def _parse_loose_json(text: str) -> Dict[str, Any]:
    """Tolerant JSON parser: strips ``` fences & returns the first {...} block."""
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    i, j = s.find("{"), s.rfind("}")
    if i == -1 or j == -1 or j <= i:
        raise ValueError("No JSON object found in final response.")
    return json.loads(s[i:j+1])

async def generate_facts(place: Dict[str, Any],
                         profile: Dict[str, Any],
                         timeout_s: int = 90) -> Dict[str, Any]:
    """Run your agent once and return the JSON as a Python dict. No human prompt."""
    agent = make_agent(place, profile)

    session = InMemorySessionService()
    app_name, user_id, session_id = "facts_app", "svc", f"task-{uuid.uuid4()}"
    await session.create_session(app_name=app_name, user_id=user_id, session_id=session_id)

    runner = Runner(agent=agent, app_name=app_name, session_service=session)

    # Internal trigger: empty user message (no real prompt needed)
    content = types.Content(role="user", parts=[types.Part(text="")])

    async def _run_once() -> str | None:
        final = None
        async for ev in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
            if ev.is_final_response() and ev.content.parts:
                final = ev.content.parts[0].text
        return final

    text = await asyncio.wait_for(_run_once(), timeout=timeout_s)
    if not text:
        raise RuntimeError("Agent returned no final response.")

    # Strict JSON first, tolerant fallback if model added code fences
    try:
        return json.loads(text)
    except Exception:
        return _parse_loose_json(text)

def generate_facts_sync(place: Dict[str, Any], profile: Dict[str, Any], timeout_s: int = 90) -> Dict[str, Any]:
    """Synchronous convenience wrapper."""
    return asyncio.run(generate_facts(place, profile, timeout_s))

if __name__ == "__main__":
    from gAIde.config import PLACE, USER_PROFILE
    facts = generate_facts_sync(PLACE, USER_PROFILE)
    print(json.dumps(facts, indent=2))