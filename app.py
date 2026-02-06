"""
FastAPI Live TTS Starter - Raw WebSocket proxy to Deepgram
"""

import os
import json
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import websockets
import toml

load_dotenv(override=False)

CONFIG = {
    "port": int(os.environ.get("PORT", 8081)),
    "host": os.environ.get("HOST", "0.0.0.0"),
    "frontend_port": int(os.environ.get("FRONTEND_PORT", 8080)),
}

def load_api_key():
    api_key = os.environ.get("DEEPGRAM_API_KEY")
    if not api_key:
        raise ValueError("DEEPGRAM_API_KEY required")
    return api_key

API_KEY = load_api_key()
DEEPGRAM_TTS_URL = "wss://api.deepgram.com/v1/speak"

app = FastAPI(title="Deepgram Live TTS API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{CONFIG['frontend_port']}",
        f"http://127.0.0.1:{CONFIG['frontend_port']}",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/tts/stream")
async def live_tts(websocket: WebSocket):
    """Raw WebSocket proxy endpoint for live TTS"""
    await websocket.accept()
    print("Client connected to /tts/stream")

    deepgram_ws = None
    forward_task = None
    stop_event = asyncio.Event()

    try:
        # Get query parameters
        model = websocket.query_params.get("model", "aura-asteria-en")
        encoding = websocket.query_params.get("encoding", "linear16")
        sample_rate = websocket.query_params.get("sample_rate", "48000")
        container = websocket.query_params.get("container", "none")

        # Build Deepgram WebSocket URL with parameters
        deepgram_url = f"{DEEPGRAM_TTS_URL}?model={model}&encoding={encoding}&sample_rate={sample_rate}&container={container}"

        print(f"Connecting to Deepgram TTS: model={model}, encoding={encoding}, sample_rate={sample_rate}")

        # Connect to Deepgram
        deepgram_ws = await websockets.connect(
            deepgram_url,
            additional_headers={"Authorization": f"Token {API_KEY}"}
        )
        print("✓ Connected to Deepgram TTS API")

        # Notify client that connection is ready
        print("DEBUG: Sending Open event to client")
        await websocket.send_text(json.dumps({'type': 'Open'}))
        print("DEBUG: Open event sent")

        # Task to forward messages from Deepgram to client
        async def forward_from_deepgram():
            try:
                async for message in deepgram_ws:
                    if stop_event.is_set():
                        break

                    # Forward message to client
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)

            except websockets.exceptions.ConnectionClosed as e:
                print(f"Deepgram connection closed: {e.code} {e.reason}")
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"Error forwarding from Deepgram: {e}")
                try:
                    await websocket.send_text(json.dumps({
                        "type": "Error",
                        "description": str(e),
                        "code": "PROVIDER_ERROR"
                    }))
                except:
                    pass  # WebSocket already closed

        # Start forwarding task
        forward_task = asyncio.create_task(forward_from_deepgram())

        # Forward messages from client to Deepgram
        try:
            while True:
                message = await websocket.receive()

                if "text" in message:
                    await deepgram_ws.send(message["text"])
                elif "bytes" in message:
                    await deepgram_ws.send(message["bytes"])

        except WebSocketDisconnect:
            print("Client disconnected")
        except Exception as e:
            print(f"Error forwarding to Deepgram: {e}")

    except Exception as e:
        print(f"WebSocket error: {e}")
        try:
            await websocket.send_text(json.dumps({
                "type": "Error",
                "description": str(e),
                "code": "CONNECTION_FAILED"
            }))
        except:
            pass  # WebSocket already closed

    finally:
        # Cleanup
        stop_event.set()

        if forward_task:
            forward_task.cancel()
            try:
                await forward_task
            except asyncio.CancelledError:
                pass

        if deepgram_ws:
            try:
                await deepgram_ws.close()
            except Exception as e:
                print(f"Error closing Deepgram connection: {e}")

        print("Connection cleanup complete")

@app.get("/api/metadata")
async def get_metadata():
    try:
        with open('deepgram.toml', 'r') as f:
            config = toml.load(f)
        return JSONResponse(content=config.get('meta', {}))
    except:
        return JSONResponse(status_code=500, content={"error": "Metadata read failed"})

if __name__ == "__main__":
    import uvicorn
    print(f"\n🚀 FastAPI Live TTS Server: http://localhost:{CONFIG['port']}\n")
    uvicorn.run(app, host=CONFIG["host"], port=CONFIG["port"])
