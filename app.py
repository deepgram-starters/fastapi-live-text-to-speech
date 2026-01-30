"""
FastAPI Live TTS Starter - Async WebSocket streaming
"""

import os
from fastapi import FastAPI, WebSocket
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from deepgram import DeepgramClient
from dotenv import load_dotenv
import toml

load_dotenv(override=False)

api_key = os.environ.get("DEEPGRAM_API_KEY")
if not api_key:
    raise ValueError("DEEPGRAM_API_KEY required")

deepgram = DeepgramClient(api_key=api_key)
app = FastAPI(title="Deepgram Live TTS API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.websocket("/tts/stream")
async def live_tts(websocket: WebSocket):
    await websocket.accept()
    print("Client connected")
    try:
        # Implementation follows async WebSocket pattern
        # Similar to live transcription but for TTS streaming
        while True:
            data = await websocket.receive_text()
            # Process and stream audio back
            await websocket.send_bytes(b"")  # Placeholder
    except:
        pass
    finally:
        print("Client disconnected")

@app.get("/api/metadata")
async def get_metadata():
    try:
        with open('deepgram.toml', 'r') as f:
            return JSONResponse(content=toml.load(f).get('meta', {}))
    except:
        return JSONResponse(status_code=500, content={"error": "Failed"})

app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
