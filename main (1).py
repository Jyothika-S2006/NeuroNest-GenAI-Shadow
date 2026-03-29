from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import cv2
import numpy as np
import base64
import json
import time
import tempfile
import os
from pipeline import EmotionPipeline

app = FastAPI(title="NeuroNest GenAI Shadow Pipeline")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = EmotionPipeline()

# ─── Health Check ─────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "NeuroNest AI Pipeline Running", "version": "1.0.0"}

@app.get("/health")
def health():
    return {"status": "ok"}


# ─── WebSocket (Live Webcam) ──────────────────────────────────────────────────
@app.websocket("/ws/analyze")
async def websocket_analyze(websocket: WebSocket):
    await websocket.accept()
    print("WebSocket connected — live webcam mode")
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "frame":
                frame_b64 = message["frame"]
                img_bytes = base64.b64decode(
                    frame_b64.split(",")[1] if "," in frame_b64 else frame_b64
                )
                np_arr = np.frombuffer(img_bytes, np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                if frame is not None:
                    result = pipeline.analyze_frame(frame)
                    await websocket.send_text(json.dumps(result))

    except WebSocketDisconnect:
        print("WebSocket disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
        await websocket.close()


# ─── Video File Upload (Testing without webcam) ───────────────────────────────
@app.post("/analyze/video")
async def analyze_video(file: UploadFile = File(...)):
    """
    Upload a video file (.mp4, .avi, .mov, .mkv).
    Returns a stream of JSON results — one per sampled frame.
    """
    suffix = os.path.splitext(file.filename)[-1] or ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        contents = await file.read()
        tmp.write(contents)
        tmp_path = tmp.name

    def generate():
        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            yield json.dumps({"error": "Could not open video file"}) + "\n"
            return

        fps          = cap.get(cv2.CAP_PROP_FPS) or 25
        total        = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        sample_every = max(1, int(fps / 3))  # ~3 results/sec
        frame_idx    = 0

        print(f"Processing video: {fps}fps, {total} frames, sampling every {sample_every}")

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_every == 0:
                result = pipeline.analyze_frame(frame)
                result["frame_number"] = frame_idx
                result["total_frames"] = total
                result["progress_pct"] = round(frame_idx / total * 100, 1) if total else 0
                yield json.dumps(result) + "\n"

            frame_idx += 1

        cap.release()
        os.unlink(tmp_path)
        print("Video analysis complete")

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson"
    )
