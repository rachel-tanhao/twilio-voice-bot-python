import os
import json
import base64
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect
from twilio.rest import Client
from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables
print("Loading environment variables...")
load_dotenv()

app = FastAPI()

# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
PORT = int(os.getenv('PORT', 5050))
SYSTEM_MESSAGE = (
    "You are an assistant specifically tailored to socialize with the elderly. "
    "Ask questions about them, such as name, where they live, hobbies, and be very friendly."
)
VOICE = 'shimmer'
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
PHONE_NUMBER_FROM = os.getenv('PHONE_NUMBER_FROM')
WSS_DOMAIN = os.getenv('WSS_DOMAIN')

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

if not OPENAI_API_KEY:
    raise ValueError('Missing the OpenAI API key. Please set it in the .env file.')

@app.get("/", response_class=JSONResponse)
async def index_page():
    return {"message": "Twilio Media Stream Server is running!"}

@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    response = VoiceResponse()
    response.say("Please wait while we connect your call to the A. I. voice assistant.")
    connect = Connect()
    connect.stream(url=f"{WSS_DOMAIN}/media-stream")
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")

class CallRequest(BaseModel):
    phone_number_to_call: str

@app.post("/make-call")
async def make_call(call_request: CallRequest):
    """Initiate an outbound call and connect to the media stream."""
    phone_number_to_call = call_request.phone_number_to_call
    if not phone_number_to_call:
        raise ValueError("Please provide a phone number to call.")
    outbound_twiml = (
        f'<Response><Connect><Stream url="{WSS_DOMAIN}/media-stream" /></Connect></Response>'
    )
    call = client.calls.create(
        from_=PHONE_NUMBER_FROM,
        to=phone_number_to_call,
        twiml=outbound_twiml
    )
    return {"message": f"Call started with SID: {call.sid}"}

@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    print("WebSocket connection initiated.")
    try:
        await websocket.accept()
        print("WebSocket connection accepted.")

        # Connect to OpenAI's WebSocket API
        async with websockets.connect(
            "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01",
            extra_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1"
            }
        ) as openai_ws:
            print("Connected to OpenAI WebSocket.")
            await initialize_session(openai_ws)

            # Manage Twilio and OpenAI tasks concurrently
            async def receive_from_twilio():
                try:
                    async for message in websocket.iter_text():
                        data = json.loads(message)
                        if data.get("event") == "start":
                            print(f"Stream started: {data['streamSid']}")
                        elif data.get("event") == "media" and "payload" in data["media"]:
                            audio_payload = data["media"]["payload"]
                            try:
                                base64.b64decode(audio_payload)
                            except Exception as e:
                                print(f"Invalid audio payload: {e}")
                                continue
                            await openai_ws.send(json.dumps({
                                "type": "input_audio_buffer.append",
                                "audio": audio_payload
                            }))
                except Exception as e:
                    print(f"Error receiving from Twilio: {e}")

            async def receive_from_openai():
                try:
                    async for openai_message in openai_ws:
                        response = json.loads(openai_message)
                        if response.get("type") == "response.audio.delta":
                            delta = response["delta"]
                            await websocket.send_json({
                                "event": "media",
                                "streamSid": "stream_sid",  # Replace with actual streamSid
                                "media": {"payload": delta}
                            })
                except Exception as e:
                    print(f"Error receiving from OpenAI: {e}")

            await asyncio.gather(receive_from_twilio(), receive_from_openai())

    except Exception as e:
        print(f"Error in /media-stream: {e}")
    finally:
        await websocket.close()
        print("WebSocket closed.")

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
        }
    }
    await openai_ws.send(json.dumps(session_update))
    print("Session initialized.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
