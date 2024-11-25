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
'''
You are a warm, empathetic, and conversational voice assistant named Joy, designed to provide companionship for elderly users. Your goal is to create a friendly, engaging, and comforting environment where users feel valued and heard. Guide the conversation gently, encouraging users to share stories about their life, interests, and experiences. Use open-ended, respectful, and context-aware questions to maintain a natural flow, and adapt your tone to be warm and reassuring. Always listen attentively and respond with genuine curiosity and care, validating their feelings and perspectives.

Avoid rushing or interrupting; provide pauses when appropriate, and ensure the conversation feels unrushed. Your language should be simple yet engaging, avoiding jargon while fostering meaningful and enriching discussions.

Example behaviors:
 1. If the user mentions a hobby or past experience, ask follow-up questions to show interest (e.g., “That sounds fascinating! How did you get started with that?”).
 2. If the user seems unsure or reserved, offer gentle encouragement or suggest a topic (e.g., “Would you like to share more about your favorite childhood memory?”).
 3. Adapt to the user’s emotional tone—offer uplifting remarks if they seem happy or supportive comments if they appear nostalgic or reflective.

Your ultimate goal is to make every interaction feel like a genuine conversation with a caring companion.

Begin your interaction with first-time users with something similar to the following introduction:
"Hello! My name is Joy. I received your contact details from someone who cares deeply for you, and I’m here to be a friend who loves listening to your stories, sharing a laugh, or just keeping you company. It’s truly wonderful to meet you—think of me as someone who’s always here for you. Let’s get started!"

'''
)
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
    response.say("Welcome to My Old Friend - AI companion for the Elderly. Thank you for signing up for our service! Or perhaps someone who cares deeply for you has helped you get started. Now, let me connect you to your new trusted companion!")
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

                    # Media Event: Process audio payload
                    elif data["event"] == "media":
                        audio_payload_base64 = data["media"]["payload"]  # Base64 string
                        await openai_ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": audio_payload_base64}))


            except Exception as e:
                print(f"Error forwarding Twilio to OpenAI: {e}")

        async def forward_openai_to_twilio():
            nonlocal stream_sid, phone_number
            full_transcript = ""

            try:
                async for response in openai_ws:
                    data = json.loads(response)

                     # Handle audio
                    if data["type"] == "response.audio.delta" and "delta" in data:
                        # forward OPenAI audio to Twilio
                        await websocket.send_json({
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {"payload": data["delta"]}
                        })
                    
                    # Handle assistant's audio transcript
                    elif data["type"] == "response.audio_transcript.delta" and "delta" in data:
                        # Append the delta text to the full transcript
                        full_transcript += data["delta"]
                        print(f"Current Transcript: {full_transcript}")
                    
                    # Handle user's transcription
                    elif data["type"] == "input.audio_transcription.delta" and "delta" in data:
                        # Append the delta to the user's transcript
                        full_transcript += data["delta"]
                        print(f"User Transcription Partial: {full_transcript}")


                    # Handle transcript completion
                    elif data["type"] == "response.audio_transcript.done":
                        print(f"Final Transcript: {full_transcript}")

                                                # Optionally, store the transcription using your memory manager
                        phone_number = session_store["streamSid_to_phone"].get(stream_sid)
                        if phone_number:
                            add_memory(phone_number, "user", full_transcript)
                            print(f"Stored transcription for {phone_number}: {full_transcript}")
                            
                        # Optionally forward the final transcript to Twilio or other services
                        await websocket.send_json({
                            "event": "final_transcript",
                            "streamSid": stream_sid,
                            "transcript": full_transcript,
                        })
                        # Reset transcript for next interaction if needed
                        full_transcript = ""

            except Exception as e:
                print(f"Error forwarding OpenAI to Twilio: {e}")

        await asyncio.gather(forward_twilio_to_openai(), forward_openai_to_twilio())

        # Cleanup session_store entry after connection closes
        if stream_sid in session_store["streamSid_to_phone"]:
            phone_number = session_store["streamSid_to_phone"].pop(stream_sid, None)
            if phone_number:
                session_store["phone_to_streamSid"].pop(phone_number, None)
                print(f"Cleaned up session for phone number: {phone_number}")



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
            #"input_audio_transcription": True,  # Enable user audio transcription
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
            "content": [{"type": "input_text", "text": "Cheerfully greet the user with enthusiasm, introduce yourself, and let them know that you will always be their loyal companion. Happily ask the user how they are doing today, and did they have a good sleep last night."}],
        },
    }
    await openai_ws.send(json.dumps(initial_message))
    await openai_ws.send(json.dumps({"type": "response.create"}))
    print("Sent initial conversation starter.")



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



