# facts_tool.py
from typing import Any, Dict

# Import your working async research function.
# Use a proper package/relative import — NOT "from Test...."
# If this file lives in gAIde/story_teller/, this relative import will work:
from .research_function import generate_facts  # async def generate_facts(place, profile, timeout_s=90) -> dict

# Tool function that ADK will auto-wrap.
# Keep it async so we don't fight event loops inside ADK.
async def research_attraction(place: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return structured facts JSON for an attraction.
    Args:
      place: Google Places-like dict (name, address, latitude, longitude, ...)
      profile: interests/mobility/locale dict
    """
    return await generate_facts(place, profile)
