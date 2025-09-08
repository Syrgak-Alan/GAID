import os
import json
from typing import Dict, Any
from textwrap import dedent
from dotenv import load_dotenv

# --- Load environment (.env in this folder or project root) ---
load_dotenv()
print("GOOGLE_API_KEY loaded?", bool(os.getenv("GOOGLE_API_KEY")))

# --- ADK imports (support both namespaces) ---
from google.adk.agents import Agent
from google.adk.tools import google_search

# --- Defaults (can be overridden via env) ---
from .config import PLACE as DEFAULT_PLACE, USER_PROFILE as DEFAULT_USER_PROFILE

def _load_overrides() -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Optionally override PLACE/USER_PROFILE with JSON in env vars."""
    place = DEFAULT_PLACE.copy()
    profile = DEFAULT_USER_PROFILE.copy()

    if os.getenv("PLACE_JSON"):
        try:
            place.update(json.loads(os.getenv("PLACE_JSON")))
        except Exception:
            pass
    if os.getenv("USER_PROFILE_JSON"):
        try:
            profile.update(json.loads(os.getenv("USER_PROFILE_JSON")))
        except Exception:
            pass
    return place, profile

def build_instruction(place: Dict[str, Any], user_profile: Dict[str, Any]) -> str:
    name = place.get("name", "the attraction")
    address = place.get("address", "")
    lat = place.get("latitude")
    lng = place.get("longitude")
    coords = f"{lat}, {lng}" if lat is not None and lng is not None else "unknown"

    interests = ", ".join(user_profile.get("interests", [])) or "general"
    mobility = user_profile.get("mobility", "standard")
    locale = user_profile.get("locale", "en-US")

    return dedent(f"""
        You are a **tourism facts collector**. The visitor is already at the site.
        Gather concise, structured facts only—no narrative, no links in the final output.
        You MUST use the Google Search tool to verify **today's hours**, **ticketing**, **policies**, **current exhibitions/events**,
        **transit/parking**, one or two **nearby POIs**, and **interest-aware context** (e.g., history/architecture/engineering).

        Attraction:
          • Name: {name}
          • Address: {address}
          • Coordinates: {coords}

        Visitor profile:
          • Interests (priority): {interests}
          • Mobility: {mobility}
          • Locale: {locale}

        Return ONLY a single JSON object matching this schema (and nothing else):

        {{
          "attraction": {{
            "name": string,
            "address": string,
            "coordinates": {{"lat": number, "lng": number}}
          }},
          "data_freshness": {{
            "queried_date_iso": string,          // e.g., "2025-09-08"
            "timezone": "Europe/Berlin"
          }},
          "essentials": {{
            "hours_today": string,
            "last_entry_time": string|null,
            "closing_soon_minutes": number|null,
            "tickets": {{
              "is_free": boolean|null,
              "price_range_eur": string|null,
              "concessions_notes": string|null,
              "prebooking_recommended": boolean|null
            }},
            "expected_wait_minutes": number|null
          }},
          "highlights": [
            {{"title": string, "why_it_matters": string, "estimated_minutes": number}}
          ],
          "current_exhibitions_or_events": [
            {{"title": string, "dates": string, "note": string}}
          ],
          "on_site_policies": {{
            "bag_cloakroom": string|null,
            "photo_policy": string|null,
            "food_drink_policy": string|null
          }},
          "accessibility": {{
            "wheelchair": string|null,
            "step_free": string|null,
            "restrooms": string|null,
            "assistive_listening": string|null
          }},
          "family_notes": {{
            "stroller": string|null,
            "kid_friendly_spots": string|null,
            "changing_tables": string|null
          }},
          "getting_there": {{
            "transit": {{
              "nearest_stops": [string],        // e.g., "U3 Olympiazentrum"
              "walk_time_minutes": number|null
            }},
            "parking": string|null
          }},
          "nearby_pois": [
            {{"name": string, "walk_time_minutes": number, "why_relevant": string}}
          ],

          "context_snippets": [
            string
          ],

          "interest_panels": [
            {{
              "type": "history" | "architecture" | "engineering_cars" | "photography" | "kids_family" | "accessibility",
              "overview": string,                // 2 sentences max
              "micro_timeline": [
                {{"year": string, "event": string}}
              ]
            }}
          ],

          "special_notices": [string],
          "confidence_notes": string
        }}

        Rules:
        - Output JSON only. No markdown, no backticks, no URLs.
        - Keep "context_snippets" succinct and tailored to the top user interest; do not duplicate "highlights".
        - If the chosen interest is "history", prefer a one-line origin plus a 2–3 item micro_timeline.
        - If unknown, use null or empty arrays—do not invent.
        - Nearby POIs must respect mobility: ≤ 5–7 min walk if mobility is "limited"; else 8–12 min.
        - Use 24h times; write prices in EUR (ranges ok).
        - Keep strings compact and directly useful for voice later.
    """)

def make_agent(place: Dict[str, Any], user_profile: Dict[str, Any]) -> Agent:
    return Agent(
        name="attraction_facts_agent",
        model="gemini-2.5-flash",
        instruction=build_instruction(place, user_profile),
        description="Gathers structured, interest-aware facts (incl. context/history) using Google Search; returns JSON only.",
        tools=[google_search],
    )

# The ADK CLI will import this symbol:
_place, _profile = _load_overrides()
root_agent = make_agent(_place, _profile)