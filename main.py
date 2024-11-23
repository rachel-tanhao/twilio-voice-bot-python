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
DOMAIN = os.getenv('DOMAIN', '')

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
    response.pause(length=1)
    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream')
    response.append(connect)

    # Add a pause to avoid immediate call termination
    response.pause(length=30)  # Keep the connection open for 30 seconds
    return HTMLResponse(content=str(response), media_type="application/xml")

class CallRequest(BaseModel):
    phone_number_to_call: str

@app.post("/make-call")
async def make_call(call_request: CallRequest):
    phone_number_to_call = call_request.phone_number_to_call
    if not phone_number_to_call:
        raise ValueError("Please provide a phone number to call.")
    is_allowed = await is_number_allowed(phone_number_to_call)
    if not is_allowed:
        raise HTTPException(status_code=400, detail=f"The number {phone_number_to_call} is not allowed.")

    # TwiML for outbound call
    outbound_twiml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response><Connect><Stream url="wss://{DOMAIN}/media-stream" /></Connect></Response>'
    )
    print(f"Generated TwiML: {outbound_twiml}")  # Log TwiML

    call = client.calls.create(
        from_=PHONE_NUMBER_FROM,
        to=phone_number_to_call,
        twiml=outbound_twiml
    )

    await log_call_sid(call.sid)

    return {"message": f"Call started with SID: {call.sid}"}

async def log_call_sid(call_sid):
    """Log the call SID."""
    print(f"Call started with SID: {call_sid}")

async def is_number_allowed(to: str) -> bool:
    """Validate allowed phone numbers."""
    allowed_numbers = ["+14452607227", "+0987654321"]  # Example allowed numbers
    return to in allowed_numbers

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

            # State management for Twilio and OpenAI interaction
            stream_sid = None

            async def receive_from_twilio():
                """Process messages from Twilio and forward to OpenAI."""
                nonlocal stream_sid
                try:
                    async for message in websocket.iter_text():
                        data = json.loads(message)
                        print(f"Received from Twilio: {data}")

                        # Ignore messages sent from OpenAI
                        if data.get("from_openai"):
                            continue

                        if data.get("event") == "start":
                            stream_sid = data["streamSid"]
                            print(f"Stream started: {stream_sid}")
                        elif data.get("event") == "media" and "payload" in data["media"]:
                            # Ensure audio payload is base64 encoded
                            try:
                                base64.b64decode(data["media"]["payload"])
                            except Exception as decode_error:
                                print(f"Error decoding Twilio audio payload: {decode_error}")
                                continue

                            # Forward audio payload to OpenAI
                            audio_append = {
                                "type": "input_audio_buffer.append",
                                "audio": data["media"]["payload"]
                            }
                            await openai_ws.send(json.dumps(audio_append))
                            print("Sent audio data to OpenAI.")
                        else:
                            print(f"Unknown Twilio event or missing fields: {data.get('event')}")
                except WebSocketDisconnect:
                    print("Twilio WebSocket disconnected.")
                except Exception as e:
                    print(f"Error receiving from Twilio: {e}")

            async def receive_from_openai():
                """Process responses from OpenAI and forward to Twilio."""
                nonlocal stream_sid
                try:
                    async for openai_message in openai_ws:
                        response = json.loads(openai_message)
                        print(f"Received from OpenAI: {response}")

                        if response.get("type") == "response.audio.delta" and "delta" in response:
                            # Verify OpenAI's response
                            try:
                                base64.b64decode(response["delta"])
                            except Exception as decode_error:
                                print(f"Error decoding OpenAI audio delta: {decode_error}")
                                continue

                            audio_delta = {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": response["delta"]},
                                "from_openai": True
                            }
                            await websocket.send_json(audio_delta)
                            print(f"Sent audio response to Twilio: {audio_delta}")
                        else:
                            print(f"Ignored non-audio response from OpenAI: {response}")
                except Exception as e:
                    print(f"Error receiving from OpenAI: {e}")

            # Run both Twilio and OpenAI tasks concurrently
            await asyncio.gather(receive_from_twilio(), receive_from_openai())

    except Exception as e:
        print(f"Error in /media-stream: {e}")
    finally:
        await websocket.close()
        print("WebSocket closed.")

async def send_initial_conversation_item(openai_ws):
    """Send initial conversation item if AI talks first."""
    initial_conversation_item = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Greet the user with 'Hi, my name is Alice, it's nice to meet you! "
                        "I am a voice assistant friend for the elderly. Can I ask what your name is?'"
                    )
                }
            ]
        }
    }
    await openai_ws.send(json.dumps(initial_conversation_item))
    await openai_ws.send(json.dumps({"type": "response.create"}))

async def initialize_session(openai_ws):
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
    print("Initializing OpenAI session...")
    await openai_ws.send(json.dumps(session_update))
    await send_initial_conversation_item(openai_ws)
    print("Session initialized.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
