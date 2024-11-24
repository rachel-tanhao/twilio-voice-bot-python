import os
import json
import asyncio
import websockets
from fastapi import WebSocket, Request
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect
import re
import openai

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
VOICE = "sage"  # OpenAI voice model
LOG_EVENT_TYPES = ["error", "response.done", "input_audio_buffer.committed"]

# Initialize Twilio client
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)



async def index():
    """Health check endpoint."""
    return {"message": "Twilio Media Stream Server is running!"}



async def transcribe_audio(audio_chunk):
    """Use OpenAI Whisper API to transcribe audio."""
    response = openai.Audio.transcribe(
        model="whisper-1",
        file=audio_chunk,
    )
    return response["text"]



async def handle_media_stream(websocket: WebSocket):
    """WebSocket for Twilio Media Streams and OpenAI Realtime API."""
    await websocket.accept()

    async with websockets.connect(
        "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01",
        extra_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1",
        },
    ) as openai_ws:
        await initialize_session(openai_ws)

        stream_sid = None
        async def forward_twilio_to_openai():
            nonlocal stream_sid
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    if data["event"] == "media":
                        await openai_ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": data["media"]["payload"]}))
                    elif data["event"] == "start":
                        stream_sid = data["start"]["streamSid"]
            except Exception as e:
                print(f"Error forwarding Twilio to OpenAI: {e}")

        async def forward_openai_to_twilio():
            nonlocal stream_sid
            try:
                async for response in openai_ws:
                    data = json.loads(response)
                    if data["type"] == "response.audio.delta" and "delta" in data:
                        await websocket.send_json({
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {"payload": data["delta"]}
                        })
            except Exception as e:
                print(f"Error forwarding OpenAI to Twilio: {e}")

        await asyncio.gather(forward_twilio_to_openai(), forward_openai_to_twilio())



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



async def handle_incoming_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    response = VoiceResponse()
    response.say(
        "Welcome to My Old Friend - AI voice bot for the elderly. Let me connect you to your old friend!"
    )
    response.pause(length=1)
    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream')
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")



async def make_call(phone_number: str):
    """发起外呼"""
    outbound_twiml = f"""
    <Response>
        <Connect>
            <Stream url="wss://{DOMAIN}/media-stream" />
        </Connect>
    </Response>
    """
    call = client.calls.create(
        from_=PHONE_NUMBER_FROM,
        to=phone_number,
        twiml=outbound_twiml,
    )
    return {"message": f"Call initiated to {phone_number}", "callSid": call.sid}




