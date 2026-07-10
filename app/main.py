import asyncio
import shutil
import tempfile
from pathlib import Path

import ollama
from fastapi import FastAPI, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import settings
from app.llm.client import answer
from app.logging_utils import new_request_id, stage_timer
from app.pipeline.sequential import run_sequential
from app.pipeline.streaming import run_streaming
from app.rag.retriever import retrieve

app = FastAPI(title="Voice-RAG Customer Service Bot")


@app.on_event("startup")
async def warm_up_models() -> None:
    """Pre-loads the Ollama chat + embedding models in the background so the
    first real user turn doesn't pay several seconds of model cold-start
    (whisper and piper already load at import time). Runs in a thread to
    avoid blocking server startup.
    """

    def _warm() -> None:
        try:
            retrieve("warm up")  # loads the embedding model
            # Force-load the chat model with a minimal direct call — answer()
            # can't be used here because an ungrounded warm-up query would
            # short-circuit into the refusal branch without touching the LLM.
            # num_ctx must match app/llm/client.py's _GENERATION_OPTIONS —
            # loading here with a different context size would make Ollama
            # reload the model on the first real request, defeating the warmup.
            ollama.Client(host=settings.ollama_host).chat(
                model=settings.llm_model,
                messages=[{"role": "user", "content": "hi"}],
                options={"num_predict": 1, "num_ctx": 2048},
                keep_alive="30m",
            )
            print("[warmup] Ollama chat + embedding models loaded", flush=True)
        except Exception as exc:  # Ollama down: degrade to lazy loading, don't crash startup
            print(f"[warmup] skipped ({exc})", flush=True)

    asyncio.get_running_loop().run_in_executor(None, _warm)


class ChatTextRequest(BaseModel):
    query: str


class ChatTextResponse(BaseModel):
    answer: str
    grounded: bool
    top_score: float


@app.post("/chat/text", response_model=ChatTextResponse)
def chat_text(payload: ChatTextRequest) -> ChatTextResponse:
    request_id = new_request_id()

    with stage_timer(request_id, "retrieval", pipeline="text"):
        retrieval_result = retrieve(payload.query)

    with stage_timer(request_id, "llm", pipeline="text"):
        result = answer(payload.query, retrieval_result)

    return ChatTextResponse(
        answer=result.text,
        grounded=result.grounded,
        top_score=retrieval_result.top_score,
    )


class ChatAudioResponse(BaseModel):
    transcript: str
    answer: str
    grounded: bool
    top_score: float
    audio_url: str


@app.post("/chat/audio", response_model=ChatAudioResponse)
async def chat_audio(file: UploadFile) -> ChatAudioResponse:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        result = run_sequential(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    return ChatAudioResponse(
        transcript=result.transcript,
        answer=result.answer_text,
        grounded=result.grounded,
        top_score=result.top_score,
        audio_url=f"/audio/{result.output_audio_path.name}",
    )


@app.get("/audio/{filename}")
def get_audio(filename: str) -> FileResponse:
    path = Path("data/audio_out") / filename
    return FileResponse(path, media_type="audio/wav")


@app.websocket("/ws/voice")
async def ws_voice(websocket: WebSocket) -> None:
    """Streaming voice endpoint (FR-005). Client sends binary PCM16 16kHz
    mono frames (20ms each); server streams back JSON StreamEvents as the
    turn progresses. One `run_streaming` call per turn; the loop lets the
    same connection carry a multi-turn conversation.
    """
    await websocket.accept()

    # specs/006: explicit language mode per connection; whitelist to the two
    # supported values so an arbitrary query param can't reach model code.
    language = websocket.query_params.get("lang", "en")
    if language not in ("en", "es"):
        language = "en"

    async def audio_frames():
        received_any = False
        while True:
            try:
                if received_any:
                    # Mid-turn: if the client stops sending frames without a
                    # clean disconnect (e.g. the demo page's release-grace-
                    # period ends and it tears down the mic before VAD ever
                    # saw a clean trailing silence), don't wait forever —
                    # treat prolonged inactivity the same as the frame source
                    # ending, which app/pipeline/streaming.py already handles
                    # as an implicit end-of-turn.
                    data = await asyncio.wait_for(websocket.receive_bytes(), timeout=2.0)
                else:
                    # Before the first frame of a turn, the user simply may
                    # not have pressed the record button yet — wait
                    # indefinitely rather than spinning up empty turns.
                    data = await websocket.receive_bytes()
            except (WebSocketDisconnect, asyncio.TimeoutError):
                return
            if not data:
                return
            received_any = True
            yield data

    try:
        while True:
            async for event in run_streaming(audio_frames(), language=language):
                await websocket.send_json(event)
    except (WebSocketDisconnect, RuntimeError):
        # RuntimeError: uvicorn raises "Unexpected ASGI message ... after
        # sending 'websocket.close'" if the client disconnects mid-turn while
        # the pipeline still has events to emit (observed when a browser tab
        # closes during generation). The turn is already lost either way.
        pass


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    # Avoids a noisy, unrelated 404 in the browser console on every page
    # load — browsers request this automatically regardless of whether the
    # page references one.
    return Response(status_code=204)


# Serves the demo page (frontend/index.html at "/"). Mounted last so it only
# catches paths not already matched by the API routes above.
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
