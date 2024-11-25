import os
import json
import asyncio
import websockets
from fastapi import WebSocket, Request
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect
from transcription_handler import transcribe_audio_bytes
import re
import openai
from memory_manager import add_memory
import base64

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
SYSTEM_MESSAGE = ("You are a helpful AI voice assistant. Engage in friendly, thoughtful conversations.")
VOICE = "sage"  # OpenAI voice model
LOG_EVENT_TYPES = ["error", "response.done", "input_audio_buffer.committed"]

# Initialize Twilio client
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

###############################################################################################
###############################################################################################


session_store = {
    "streamSid_to_phone": {},  # Map streamSid to phone_number
    "phone_to_streamSid": {}  # Map phone_number to streamSid
}



async def index():
    """Health check endpoint."""
    return {"message": "Twilio Media Stream Server is running!"}



async def extract_caller_phone_number(request: Request):
    """
    Extract the phone number of the incoming caller from the Twilio webhook request.
    """
    try:
        form_data = await request.form()
        phone_number = form_data.get("From", None)  # Twilio sends the caller's phone number in the 'From' field
        return phone_number
    except Exception as e:
        print(f"Failed to extract phone number: {e}")
        return None


async def handle_audio_transcribe(audio_bytes):
    transcription_result = await transcribe_audio_bytes(audio_bytes)
    if "transcription" in transcription_result:
        return transcription_result["transcription"]
    else:
        print(f"Error transcribing audio: {transcription_result['error']}")
        return None


async def handle_audio_transcribe_and_store(phone_number: str, audio_bytes: bytes):
    """
    Transcribe user audio and store it in Mem0.
    :param phone_number: The phone number associated with the user.
    :param audio_bytes: Audio data as bytes.
    """
    try:
        # Get the transcription
        transcription_result = await transcribe_audio_bytes(audio_bytes)
        if not transcription_result:
            raise RuntimeError("No transcription result returned.")

        # Ensure transcription_result is a string before storing
        transcription = transcription_result if isinstance(transcription_result, str) else transcription_result.get("transcription", "")

        if not transcription:
            raise RuntimeError("Transcription is empty or invalid.")

        # Add transcription to memory
        add_memory(phone_number, "user", transcription)
        print(f"Stored transcription for {phone_number}: {transcription}")
        return transcription
    except Exception as e:
        print(f"Error handling audio transcription: {e}")
        return None




async def handle_incoming_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    phone_number = await extract_caller_phone_number(request)
    if phone_number:
        print(f"Incoming call from {phone_number}")
        # Temporarily store the phone number with a placeholder for future streamSid
        session_store["phone_to_streamSid"][phone_number] = None

    else:
        print("Failed to extract phone number.")
    

    response = VoiceResponse()
    response.say("Welcome to My Old Friend - AI voice bot for the elderly. Let me connect you to your old friend!")
    response.pause(length=1)
    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream')
    response.append(connect)

    return HTMLResponse(content=str(response), media_type="application/xml")




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
        stream_sid, phone_number = None, None

        async def forward_twilio_to_openai():
            nonlocal stream_sid, phone_number
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    
                    # Start Event: Capture streamSid and associate with phone number
                    if data["event"] == "start":
                        stream_sid = data["start"]["streamSid"]
                        print(f"Stream started with SID: {stream_sid}")

                        # Map streamSid to phone_number
                        for phone_number, sid in session_store["phone_to_streamSid"].items():
                            if sid is None:
                                session_store["streamSid_to_phone"][stream_sid] = phone_number
                                session_store["phone_to_streamSid"][phone_number] = stream_sid
                                print(f"Mapped streamSid {stream_sid} to phone number {phone_number}")
                                break

                    # Media Event: Append audio payload to OpenAI input buffer
                    elif data["event"] == "media":
                        audio_payload_base64 = data["media"]["payload"]  # Base64 string
                        # print(f"Received Twilio audio payload: {audio_payload_base64[:30]}...")  # Log a snippet
                        await openai_ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": audio_payload_base64}))

            except Exception as e:
                print(f"Error forwarding Twilio to OpenAI: {e}")

        async def handle_openai_events():
            """Process OpenAI Realtime events for assistant responses and turn-based transcription."""
            nonlocal stream_sid, phone_number
            try:
                async for response in openai_ws:
                    data = json.loads(response)

                    # Print the full data object for debugging
                    print(f"OpenAI response data: {json.dumps(data, indent=2)}")

                    # Input Audio Buffer Committed: Indicates the end of user speech
                    if data["type"] == "input_audio_buffer.committed":
                        print("Audio buffer committed; end of user's speech turn detected.")
                        phone_number = session_store["streamSid_to_phone"].get(stream_sid)

                        if phone_number:
                            print(f"Processing user audio for phone number: {phone_number}")

                            # Fetch the latest committed audio buffer for transcription
                            audio_payload = data.get("audio")
                            if audio_payload:
                                try:
                                    audio_bytes = base64.b64decode(audio_payload)  # Convert Base64 to bytes and transcribe
                                    await handle_audio_transcribe_and_store(phone_number, audio_bytes)
                                except Exception as e:
                                    print(f"Error decoding or transcribing user audio: {e}")
                            else:
                                print("No audio payload available for transcription.")

                    # Conversation Item Created: Process assistant messages
                    elif data["type"] == "conversation.item.created":
                        
                        role = data["item"]["role"]
                        content = data["item"]["content"]

                        if role == "assistant":
                            phone_number = session_store["streamSid_to_phone"].get(stream_sid)
                            if content:  # Check if content is not empty
                                text = content[0].get("text", "")
                                if phone_number:
                                    print(f"Assistant response for {phone_number}: {text}")
                                    add_memory(phone_number, "assistant", text)
                            else:
                                print("Assistant response content is empty.")


                    # Assistant Audio Delta: Forward audio to Twilio
                    if data["type"] == "response.audio.delta" and "delta" in data:
                        assistant_audio = data["delta"]
                        if assistant_audio:
                            await websocket.send_json({
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": assistant_audio},
                            })
                            print(f"Forwarded assistant audio to Twilio for streamSid: {stream_sid}")
                        else:
                            print("Received empty assistant audio delta.")


            except Exception as e:
                print(f"Error processing OpenAI events: {e}")

                
                
        # Run all three tasks concurrently
        await asyncio.gather(
            forward_twilio_to_openai(),
            handle_openai_events()
        )

        # Cleanup session_store entry after connection closes
        if stream_sid in session_store["streamSid_to_phone"]:
            phone_number = session_store["streamSid_to_phone"].pop(stream_sid, None)
            if phone_number:
                session_store["phone_to_streamSid"].pop(phone_number, None)
                print(f"Cleaned up session for phone number: {phone_number}")



async def initialize_session(openai_ws):
    """Initialize OpenAI session with VAD-based turn detection."""
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {
                "type": "server_vad",  # Enable server VAD
                "threshold": 0.8,
                "prefix_padding_ms": 500,
                "silence_duration_ms": 700,
            },
            "input_audio_format": "g711_ulaw",  # Ensure this matches Twilio's format
            "output_audio_format": "g711_ulaw",
            "voice": "sage",  # Set the voice model
            "instructions": (
                "You are a helpful AI voice assistant. Always respond to user input thoughtfully."
            ),
            "modalities": ["text", "audio"],  # Both text and audio modalities
            "input_audio_transcription": True,  # Enable user audio transcription
            "temperature": 0.8,  # Adjust for conversational variability
        },
    }
    await openai_ws.send(json.dumps(session_update))
    print("Session update sent to OpenAI.")

    # Send a response.create message to trigger assistant speaks first
    await openai_ws.send(json.dumps({
        "type": "response.create",
        "response": {
            "modalities": ["audio", "text"],
            "instructions": "Please greet the user."
        }
    }))
    print("Requested initial assistant response.")




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




