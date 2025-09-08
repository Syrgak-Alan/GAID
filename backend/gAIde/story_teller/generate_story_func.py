# agent_function.py
import asyncio, json, re, uuid, threading
from typing import Any, Dict, Optional

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Import your orchestrator Storyteller agent factory.
# Prefer relative import if this file sits in the same package as storyteller_agent/.
from .story_teller_agent import make_orchestrator  # __init__.py should `from .agent import make_orchestrator`

def _strip_code_fences(text: str) -> str:
    """
    Remove leading/trailing Markdown code fences if the model accidentally wraps output.
    Returns trimmed plain text.
    """
    s = text.strip()
    if s.startswith("```"):
        # remove opening fence with optional language
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s)
        # remove trailing fence
        s = re.sub(r"\s*```$", "", s)
    return s.strip()


async def generate_story(
    image: str,
    profile: Dict[str, Any],
    timeout_s: int = 90,
) -> str:
    """
    Run the Storyteller orchestrator once and return the STORY_SCRIPT as plain text.
    No human prompt is used. The agent will call the research tool internally.
    """
    # Build agent (locale usually lives in profile)
    locale = profile.get("locale", "en-US")
    agent = make_orchestrator(locale=locale)

    # Create an in-memory session and runner
    app_name, user_id, session_id = "story_app", "svc", f"task-{uuid.uuid4()}"
    session = InMemorySessionService()
    await session.create_session(app_name=app_name, user_id=user_id, session_id=session_id)
    runner = Runner(agent=agent, app_name=app_name, session_service=session)

    # Send ONLY structured inputs; the agent decides to call the tool.
    payload = json.dumps({"image": image, "profile": profile}, ensure_ascii=False)
    content = types.Content(role="user", parts=[types.Part(text=payload)])

    async def _run_once() -> Optional[str]:
        final_text = None
        async for ev in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
            if ev.is_final_response() and ev.content.parts:
                print("Final response received.")
                final_text = ev.content.parts[0].text
        return final_text

    # Run with a timeout for safety
    text = await asyncio.wait_for(_run_once(), timeout=timeout_s)
    if not text:
        raise RuntimeError("Storyteller returned no final response.")

    assert isinstance(text, str)
    return _strip_code_fences(text)


def generate_story_sync(
    image: str,
    profile: Dict[str, Any],
    timeout_s: int = 90,
) -> str:
    """
    Blocking wrapper that works both in scripts and notebooks.
    (Avoids `asyncio.run()` inside an already-running event loop by using a background thread.)
    """
    result: Dict[str, str] = {}
    err: Dict[str, BaseException] = {}

    def _runner():
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            result["value"] = loop.run_until_complete(generate_story(image, profile, timeout_s))
        except BaseException as e:
            err["e"] = e
        finally:
            loop.close()

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join()

    if "e" in err:
        raise err["e"]
    return result.get("value", "")
