import os
import json
import base64
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect, Say, Stream
import uvicorn
import re

# Load environment variables
load_dotenv()

# Configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
PHONE_NUMBER_FROM = os.getenv("PHONE_NUMBER_FROM")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
raw_domain = os.getenv("DOMAIN", "")
DOMAIN = re.sub(r"(^\w+:|^)\/\/|\/+$", "", raw_domain)  # Strip protocols and trailing slashes
PORT = int(os.getenv("PORT", 6060))

# OpenAI and Twilio settings
SYSTEM_MESSAGE = (
    "You are a helpful AI voice assistant. Engage in friendly, thoughtful conversations."
)
VOICE = "shimmer"  # OpenAI voice model
LOG_EVENT_TYPES = ["error", "response.done", "input_audio_buffer.committed"]

# Initialize FastAPI and Twilio client
app = FastAPI()
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and PHONE_NUMBER_FROM and OPENAI_API_KEY):
    raise ValueError("Missing required environment variables. Please check your .env file.")

@app.get("/", response_class=JSONResponse)
async def index():
    """Health check endpoint."""
    return {"message": "Twilio Media Stream Server is running!"}

@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    response = VoiceResponse()
    response.say(
        "Welcome to the AI assistant powered by Twilio and OpenAI. Please wait while we connect you."
    )
    response.pause(length=1)
    response.say("You can start talking now.")
    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream')
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")

@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    """WebSocket for Twilio Media Streams and OpenAI Realtime API."""
    print("WebSocket connection initiated.")
    await websocket.accept()

    # Connect to OpenAI WebSocket API
    async with websockets.connect(
        "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01",
        extra_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1",
        },
    ) as openai_ws:
        print("Connected to OpenAI WebSocket.")
        await initialize_session(openai_ws)

        stream_sid = None

        async def receive_from_twilio():
            """Forward Twilio audio to OpenAI."""
            nonlocal stream_sid
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    if data["event"] == "media" and "payload" in data["media"]:
                        payload = data["media"]["payload"]
                        await openai_ws.send(
                            json.dumps({"type": "input_audio_buffer.append", "audio": payload})
                        )
                        print("Forwarded audio to OpenAI.")
                    elif data["event"] == "start":
                        stream_sid = data["start"]["streamSid"]
                        print(f"Stream started with streamSid: {stream_sid}")
            except Exception as e:
                print(f"Error in Twilio WebSocket: {e}")

        async def receive_from_openai():
            """Forward OpenAI audio back to Twilio."""
            nonlocal stream_sid
            try:
                async for response in openai_ws:
                    data = json.loads(response)
                    if data["type"] == "response.audio.delta" and "delta" in data:
                        await websocket.send_json(
                            {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": data["delta"]},
                            }
                        )
                        print("Forwarded audio to Twilio.")
            except Exception as e:
                print(f"Error in OpenAI WebSocket: {e}")

        await asyncio.gather(receive_from_twilio(), receive_from_openai())

async def initialize_session(openai_ws):
    """Initialize OpenAI session."""
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["text", "audio"],
            "temperature": 0.8,
        },
    }
    await openai_ws.send(json.dumps(session_update))
    print("OpenAI session initialized.")

    # Send initial conversation starter
    initial_message = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Hi! How can I assist you today?"}],
        },
    }
    await openai_ws.send(json.dumps(initial_message))
    await openai_ws.send(json.dumps({"type": "response.create"}))
    print("Sent initial conversation starter.")

@app.post("/make-call")
async def make_call(phone_number: str):
    """Make an outbound call and connect to the media stream."""
    outbound_twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Connect>
            <Stream url="wss://{DOMAIN}/media-stream" />
        </Connect>
    </Response>"""
    call = client.calls.create(
        from_=PHONE_NUMBER_FROM,
        to=phone_number,
        twiml=outbound_twiml,
    )
    print(f"Call started with SID: {call.sid}")
    return {"message": f"Call initiated to {phone_number}", "callSid": call.sid}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the Twilio AI voice assistant.")
    parser.add_argument('--call', required=False, help="The phone number to call, e.g., '--call=+18005551212'")
    args = parser.parse_args()

    if args.call:
        # Make a call and exit
        asyncio.run(make_call(args.call))
    else:
        # Start the server
        uvicorn.run(app, host="0.0.0.0", port=PORT)
