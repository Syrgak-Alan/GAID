import asyncio
import base64
import contextlib
import json
import logging
import os
import re
import tempfile
import threading
import time

from dotenv import load_dotenv
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

# Google ADK
from google.adk.agents import Agent, LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types

# Ваши модули
from backend.gAIde.story_teller.generate_story_func import generate_story_sync
from backend.gAIde.story_teller.config import USER_PROFILE
from common import (
    BaseWebSocketServer,
    logger,
    MODEL,
    VOICE_NAME,
    SEND_SAMPLE_RATE,
    SYSTEM_INSTRUCTION,  # <-- используйте английский промпт из прошлой части
)

load_dotenv()


class MultimodalADKServer(BaseWebSocketServer):
    """WebSocket server implementation for multimodal input (audio + video) using Google ADK."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        super().__init__(host, port)

        # Состояние последнего кадра + защита потока
        self.latest_frame: bytes | None = None
        self.latest_frame_ts: float = 0.0
        self._frame_lock = threading.Lock()

        # Разрешение на вызов describe_place в текущем ходе
        self._allow_describe_place: bool = False

        # Инициализация агента с привязанным методом-инструментом
        self.agent = Agent(
            name="customer_service_agent",
            model=MODEL,
            instruction=SYSTEM_INSTRUCTION,
            tools=[self.describe_place],  # ВАЖНО: bound-метод
        )

        self.session_service = InMemorySessionService()

    # ---------- SERVER-SIDE INTENT CHECK ----------

    @staticmethod
    def _allow_from_user_text(text: str) -> bool:
        """Определяет, просил ли пользователь запустить/выполнить описание места."""
        t = text.lower()
        patterns = [
            r"\brun\s+describe_place\b",
            r"\bdescribe\s+(this|the)?\s*(place|building|landmark)\b",
            r"\bwhat\s+is\s+this\s+(place|building|landmark)\b",
            # русские варианты (по желанию):
            r"\bзапусти\s+describe_place\b",
            r"\bопиши\s+(это|здание|место|достопримечательность)\b",
        ]
        return any(re.search(p, t) for p in patterns)

    # ---------- TOOL (с жёстким гейтом) ----------

    def describe_place(self) -> str:
        """
        Инструмент доступен ТОЛЬКО если:
        1) Пользователь явно попросил (server-side флаг True)
        2) Есть свежий кадр (например, не старше 3 сек)
        """
        # 1) Проверка намерения (флаг выставляется при обработке текста пользователя)
        if not self._allow_describe_place:
            return (
                "I’m ready to describe a place when you ask. "
                "Say: 'Describe this place' or 'Run describe_place'."
            )

        # 2) Свежесть кадра
        with self._frame_lock:
            frame = self.latest_frame
            ts = self.latest_frame_ts

        if not frame or (time.time() - ts) > 3.0:
            return (
                "I don’t have a fresh camera frame yet. "
                "Please show the place to the camera or send an image."
            )

        # 3) Генерация текста по кадру
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp.write(frame)
                tmp_path = tmp.name

            story = generate_story_sync(tmp_path, USER_PROFILE)
            return story

        except Exception as e:
            logger.exception("describe_place failed")
            return f"Sorry, I couldn't describe the place: {e}"

        finally:
            if tmp_path and os.path.exists(tmp_path):
                with contextlib.suppress(Exception):
                    os.remove(tmp_path)

    # ---------- MAIN WS HANDLER ----------

    async def process_audio(self, websocket, client_id):
        """Process audio and video from the client using ADK."""
        # Store reference to client
        self.active_clients[client_id] = websocket

        # Create session for this client
        session = await self.session_service.create_session(
            app_name="multimodal_assistant",
            user_id=f"user_{client_id}",
            session_id=f"session_{client_id}",
        )

        # Create runner
        runner = Runner(
            app_name="multimodal_assistant",
            agent=self.agent,
            session_service=self.session_service,
        )

        # Create live request queue
        live_request_queue = LiveRequestQueue()

        # Create run config with audio settings
        run_config = RunConfig(
            streaming_mode=StreamingMode.BIDI,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=VOICE_NAME
                    )
                )
            ),
            response_modalities=["AUDIO"],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
        )

        # Bounded queues for audio/video to avoid unbounded growth
        audio_queue = asyncio.Queue(maxsize=50)
        video_queue = asyncio.Queue(maxsize=5)

        client_alive = True  # guard to stop sending after browser disconnects

        async with asyncio.TaskGroup() as tg:

            # -------- Incoming WS messages --------
            async def handle_websocket_messages():
                nonlocal client_alive
                try:
                    async for message in websocket:
                        try:
                            data = json.loads(message)
                        except json.JSONDecodeError:
                            logger.error("Invalid JSON message received")
                            continue

                        msg_type = data.get("type")

                        if msg_type == "audio":
                            # Decode base64 audio data
                            try:
                                audio_bytes = base64.b64decode(data.get("data", ""))
                            except Exception as e:
                                logger.error(f"Audio b64 decode error: {e}")
                                continue
                            # Drop oldest if queue is full (keep realtime)
                            if audio_queue.full():
                                _ = audio_queue.get_nowait()
                                audio_queue.task_done()
                            await audio_queue.put(audio_bytes)

                        elif msg_type == "video":
                            try:
                                video_bytes = base64.b64decode(data.get("data", ""))
                            except Exception as e:
                                logger.error(f"Video b64 decode error: {e}")
                                continue
                            video_mode = data.get("mode", "webcam")
                            if video_queue.full():
                                _ = video_queue.get_nowait()
                                video_queue.task_done()
                            await video_queue.put({"data": video_bytes, "mode": video_mode})

                        elif msg_type == "end":
                            logger.info("Received end signal from client")

                        elif msg_type in ("text", "speak_text"):
                            txt = data.get("data", "") or ""
                            if msg_type == "speak_text":
                                txt = f"Read the following verbatim and do not add anything else: {txt}"
                            # Forward text to ADK
                            live_request_queue.send_realtime(types.Part(text=txt))
                            logger.info("Forwarded text to live_request_queue for narration")

                except (ConnectionClosed, ConnectionClosedError):
                    logger.info("Browser client closed the connection")
                except Exception as e:
                    logger.exception(f"MessageHandler error: {e}")
                finally:
                    client_alive = False
                    # Unblock workers so TaskGroup can exit cleanly
                    with contextlib.suppress(Exception):
                        await audio_queue.put(None)
                        await video_queue.put(None)

            # -------- Audio worker --------
            async def process_and_send_audio():
                while True:
                    data = await audio_queue.get()
                    try:
                        if data is None:  # sentinel
                            return
                        live_request_queue.send_realtime(
                            types.Blob(
                                data=data,
                                mime_type=f"audio/pcm;rate={SEND_SAMPLE_RATE}",
                            )
                        )
                    except Exception as e:
                        logger.exception(f"AudioProcessor error: {e}")
                        return
                    finally:
                        audio_queue.task_done()

            # -------- Video worker --------
            async def process_and_send_video():
                while True:
                    video_data = await video_queue.get()
                    try:
                        if video_data is None:  # sentinel
                            return
                        video_bytes = video_data.get("data")
                        video_mode = video_data.get("mode", "webcam")
                        logger.info(f"Processing video frame from {video_mode}")

                        # Обновляем буфер последнего кадра + таймштамп
                        if video_bytes:
                            with self._frame_lock:
                                self.latest_frame = video_bytes
                                self.latest_frame_ts = time.time()

                        # Отправляем кадр в ADK (для контекста/мультимодальности)
                        live_request_queue.send_realtime(
                            types.Blob(
                                data=video_bytes,
                                mime_type="image/jpeg",
                            )
                        )
                    except Exception as e:
                        logger.exception(f"VideoProcessor error: {e}")
                        return
                    finally:
                        video_queue.task_done()

            # -------- ADK responses --------
            async def receive_and_process_responses():
                input_texts = []
                output_texts = []
                current_session_id = None

                interrupted = False

                try:
                    async for event in runner.run_live(
                        session=session,
                        live_request_queue=live_request_queue,
                        run_config=run_config,
                    ):
                        event_str = str(event)

                        # Session resumption
                        if (
                            hasattr(event, "session_resumption_update")
                            and event.session_resumption_update
                        ):
                            update = event.session_resumption_update
                            if update.resumable and update.new_handle:
                                current_session_id = update.new_handle
                                logger.info(f"New SESSION: {current_session_id}")
                                if client_alive:
                                    with contextlib.suppress(Exception):
                                        await websocket.send(
                                            json.dumps(
                                                {"type": "session_id", "data": current_session_id}
                                            )
                                        )

                        # Content handling
                        if event.content and event.content.parts:
                            for part in event.content.parts:
                                # Audio chunks from model
                                if hasattr(part, "inline_data") and part.inline_data:
                                    b64_audio = base64.b64encode(part.inline_data.data).decode("utf-8")
                                    if client_alive:
                                        with contextlib.suppress(Exception):
                                            await websocket.send(
                                                json.dumps({"type": "audio", "data": b64_audio})
                                            )

                                # Text chunks
                                if hasattr(part, "text") and part.text:
                                    if hasattr(event.content, "role") and event.content.role == "user":
                                        # Не эхоим в клиент; используем для распознавания намерения
                                        input_texts.append(part.text)
                                        # Обновляем разрешение на инструмент на основе текста пользователя
                                        self._allow_describe_place = self._allow_from_user_text(part.text)
                                    else:
                                        # Отправляем только partial, чтобы не дублировать финал
                                        if "partial=True" in event_str:
                                            if client_alive:
                                                with contextlib.suppress(Exception):
                                                    await websocket.send(
                                                        json.dumps({"type": "text", "data": part.text})
                                                    )
                                            output_texts.append(part.text)

                        # Interruption
                        if event.interrupted and not interrupted:
                            logger.info("🤐 INTERRUPTION DETECTED")
                            if client_alive:
                                with contextlib.suppress(Exception):
                                    await websocket.send(
                                        json.dumps(
                                            {"type": "interrupted", "data": "Response interrupted by user input"}
                                        )
                                    )
                            interrupted = True

                        # Turn complete
                        if event.turn_complete:
                            if not interrupted and client_alive:
                                with contextlib.suppress(Exception):
                                    await websocket.send(
                                        json.dumps({"type": "turn_complete", "session_id": current_session_id})
                                    )

                            # Logs (dedup)
                            if input_texts:
                                unique = list(dict.fromkeys(input_texts))
                                logger.info(f"Input transcription: {' '.join(unique)}")
                            if output_texts:
                                unique = list(dict.fromkeys(output_texts))
                                logger.info(f"Output transcription: {' '.join(unique)}")

                            # Reset per turn
                            input_texts = []
                            output_texts = []
                            interrupted = False
                            self._allow_describe_place = False  # сбрасываем разрешение на тул

                except (ConnectionClosedError, ConnectionClosed, TimeoutError) as e:
                    logger.error(f"Gemini live connection closed: {e}")
                    if client_alive:
                        with contextlib.suppress(Exception):
                            await websocket.send(json.dumps({"type": "error", "data": "model_connection_closed"}))
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.exception(f"Unexpected error in ResponseHandler: {e}")
                    if client_alive:
                        with contextlib.suppress(Exception):
                            await websocket.send(json.dumps({"type": "error", "data": "server_error"}))
                finally:
                    # Make sure workers can exit if this task dies first
                    with contextlib.suppress(Exception):
                        await audio_queue.put(None)
                        await video_queue.put(None)

            # Start all tasks
            tg.create_task(handle_websocket_messages(), name="MessageHandler")
            tg.create_task(process_and_send_audio(), name="AudioProcessor")
            tg.create_task(process_and_send_video(), name="VideoProcessor")
            tg.create_task(receive_and_process_responses(), name="ResponseHandler")


async def main():
    """Main function to start the server"""
    server = MultimodalADKServer()
    await server.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Exiting application via KeyboardInterrupt...")
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}")
        import traceback
        traceback.print_exc()
