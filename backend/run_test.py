import os, asyncio, json, base64, sys
import websockets

print(os.getcwd())  # should end with .../your_project

# In test_script.ipynb � run from your project root
from gAIde.story_teller.generate_story_func import generate_story_sync
from gAIde.story_teller.config import PLACE, USER_PROFILE


async def speak_via_live_api(text: str, ws_url: str = "ws://localhost:8765") -> None:
    """Connect to the live API WebSocket and ask it to narrate the given text.
    Audio is streamed back as base64 chunks; we write a raw PCM file for quick debugging.
    """
    try:
        async with websockets.connect(ws_url) as ws:
            # Wait for ready
            msg = await ws.recv()
            try:
                data = json.loads(msg)
            except Exception:
                data = {"type": "unknown", "raw": msg}
            print("live-api server says:", data)

            # Ask the server to speak the text
            await ws.send(json.dumps({"type": "speak_text", "data": text}))

            # Collect audio until turn_complete
            raw_path = os.path.join(os.path.dirname(__file__), "story_audio.pcm")
            with open(raw_path, "wb") as f:
                while True:
                    incoming = await ws.recv()
                    evt = json.loads(incoming)
                    if evt.get("type") == "audio":
                        f.write(base64.b64decode(evt["data"]))
                    elif evt.get("type") == "turn_complete":
                        print("live-api: turn complete")
                        break
            print(f"Saved raw PCM audio to {raw_path}. Sample rate is 24000 Hz.")
    except Exception as e:
        print(f"Could not speak via live-api: {e}", file=sys.stderr)


# Generate story text
story = generate_story_sync(
    "/Volumes/Crucial_X6/GCP_hackathon/GAID/backend/image.png",
    USER_PROFILE
)
print(story)

# Send to live-api for narration (requires live server running and reachable)
asyncio.run(speak_via_live_api(story))
