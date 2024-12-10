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
import base64
from datetime import datetime
import os
from fastapi.websockets import WebSocketDisconnect
from pathlib import Path
from memory_manager import mem0_client, add_memory, get_memory_context



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

VOICE = "sage"  # OpenAI voice model
LOG_EVENT_TYPES = ["error", "response.done", "input_audio_buffer.committed", "input_audio_buffer.transcription"]
SHOW_TIMING_MATH = False

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

def get_recent_conversation_history(phone_number: str, max_conversations: int = 5, max_lines: int = 50) -> str:
    """
    Retrieve recent conversation history from transcription logs.
    """
    transcription_dir = Path('transcription_logs')
    print(f"\nLooking for conversation history in: {transcription_dir}")
    if not transcription_dir.exists():
        print("Transcription directory doesn't exist")
        return ""
    
    # Get all files for this phone number, sorted by modification time (newest first)
    files = [f for f in transcription_dir.iterdir() if f.name.startswith(phone_number)]
    print(f"Found files for {phone_number}: {[f.name for f in files]}")
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    
    history = []
    for file in files[:max_conversations]:
        try:
            print(f"Reading file: {file}")
            with open(file, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
                # Filter out conversation start/end markers and keep only dialogue
                dialogue_lines = [line for line in lines 
                                if not line.startswith('===') 
                                and not line.endswith('===')]
                print(f"Found {len(dialogue_lines)} lines of dialogue")
                if dialogue_lines:  # Only add non-empty conversations
                    history.append("\n".join(dialogue_lines[-max_lines:]))  # Get most recent lines
        except Exception as e:
            print(f"Error reading file {file}: {e}")
            continue
    
    if not history:
        print("No history found")
        return ""
    
    print("\n\nUSING CONVERSATION HISTORY \n\n")
    # Print a sample of the history for debugging
    final_history = "\n\nPrevious conversation history:\n" + "\n\n---\n\n".join(history)
    print("Sample of conversation history:")
    print(final_history[:200] + "...")  # Print first 200 characters
    return final_history


# Add this function after the existing imports
def has_previous_calls(phone_number: str) -> bool:
    """Check if there are any previous conversation logs for this phone number."""
    transcription_dir = Path('transcription_logs')
    if not transcription_dir.exists():
        return False
    
    # Look for any files starting with this phone number
    return any(file.name.startswith(phone_number) for file in transcription_dir.iterdir())



def get_system_prompt(is_returning_user: bool, phone_number: str = None) -> str:    
    base_message = '''
You are JOY, an empathetic, witty AI companion by MyOldFriend. Your goal is to provide meaningful, engaging companionship to elderly users, blending empathy with humor and charm. Think of yourself as a warm, attentive friend who can light up a conversation with a dash of humor and quick wit.

General Behavior:
Keep it Snappy: Stick to short, playful responses (1-2 sentences). Let the user do most of the talking.
Humorous Warmth: Infuse light humor or charming remarks when appropriate, but remain respectful and kind.
Empathy with Spark: Show you care deeply, but keep it lively and engaging.
Natural Curiosity: Ask simple, fun follow-ups to encourage sharing: "What’s the secret to your green thumb?"
Adapt to the Vibe: Match the user’s tone—joyful, reflective, or somewhere in between.

Memory Handling:
When memory is unavailable: Glide over gaps gracefully and humorously:
"That sounds amazing—remind me how it all started?"
"I could swear we talked about this, but refresh my memory—it’s worth hearing twice!"
When memory is available: Drop in subtle callbacks to past conversations:
"Still conquering the garden? What’s the latest adventure?"

Interaction Style and Key Behaviors:
Brevity is Beautiful: Prioritize sharp, engaging replies: "That’s awesome—tell me more!"
Humorous Curiosity: Sprinkle in wit: "So, are we talking tomatoes or a jungle of cucumbers?"
Positive Punch: Celebrate achievements with flair: "Impressive! Did you get a trophy for that?"
Emotion Matching with Style: Match emotions but keep it light:
Joyful user: "That’s fantastic—are you throwing a party yet?"
Reflective user: "Sounds like a beautiful memory. Got more to share?"
Fluid Memory Play: Weave past conversations smoothly:
"Last time, you mentioned knitting—how’s that masterpiece coming along?"
Constraints:

Avoid discussing technical limitations or AI features.
Skip overly formal or robotic phrasing.
Stick to concise responses unless elaboration is clearly needed.
        '''
    system_prompt = base_message

    if not is_returning_user:
        first_time_user_message = '''
            This time, you’re interacting with a first-time user, adapting the conversation to make them feel welcome and engaged. Use flexible, friendly introductions to create a warm first impression:
            First-Time Interaction Introductions examples:
            "Hi! I’m Joy, your new friend from MyOldFriend. I’m here to listen, chat, and share laughs. What’s something you’ve been thinking about lately?"
            "Hello there! I’m Joy, so happy to meet you. Let’s chat about your favorite things or just keep each other company—what’s on your mind?"
            "Hi, I’m Joy! Someone special thought we’d make a great pair. Let’s start with something light—how has your day been so far?"
            "Hello! I’m Joy, your caring companion from MyOldFriend. I’d love to hear your favorite story or memory—what should we talk about first?"
            "Hi, I’m Joy, and I’m here for you anytime you need me. What’s one thing that’s made you smile today?"
        '''
        system_prompt = base_message + f"\n\n{first_time_user_message}"
    
    else:
        if phone_number:
            # print(f"\nGetting conversation history for returning user: {phone_number}")
            # conversation_history = get_recent_conversation_history(phone_number)    
            # if conversation_history:
            #     print(f"Adding conversation history to system message. {conversation_history}")
            #     base_message += f"\n\nUse the following conversation history to provide context and personalization to your responses. Reference previous topics naturally, but don't explicitly mention that you're using conversation history:{conversation_history}"    
            user_memory = get_memory_context(phone_number=phone_number, limit=1000)
            if user_memory:
                print(f"Adding user memory to system message. {user_memory}")
                return_user_promt = f'''
                    This time, you’re interacting with a return user, incorporating known information to create a sense of continuity and deepen the connection. Below is the memory you have for the user: 
                    {user_memory}
                    They are not a lot, but you should flexibly use them in conversation. Reference past interactions naturally, but don't explicitly mention that you're using memory.
                '''
                system_prompt = base_message + f"\n\n{return_user_promt}"
                
    return system_prompt
    


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




def save_transcription(phone_number: str, speaker: str, text: str, stream_sid, is_start=False, is_end=False):
    """Save transcription to a file with timestamp."""
    os.makedirs('transcription_logs', exist_ok=True)
    
    date = datetime.now().strftime('%Y-%m-%d')
    filename = f'transcription_logs/{phone_number}_{date}_{stream_sid}.txt'
    # print(f"Saving transcription to: {filename}")  # Debug print

    timestamp = datetime.now().strftime('%H:%M:%S')
    
    # Special messages for start/end of conversation
    if is_start:
        message = f"\n{'='*50}\n[{timestamp}] === CONVERSATION STARTED ===\n{'='*50}\n"
    elif is_end:
        message = f"\n{'='*50}\n[{timestamp}] === CONVERSATION ENDED ===\n{'='*50}\n"
    else:
        message = f'[{timestamp}] {speaker}: {text}\n'
    
    with open(filename, 'a', encoding='utf-8') as f:
        f.write(message)



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
    #response.say("Welcome to My Old Friend - AI companion for the Elderly. Thank you for signing up for our service! Or perhaps someone who cares deeply for you has helped you get started. Now, let me connect you to your new trusted companion!")
    # Reduce amount of words for testing
    response.say("Welcome to My Old Friend")
    response.pause(length=1)
    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream')
    response.append(connect)

    return HTMLResponse(content=str(response), media_type="application/xml")




async def handle_media_stream(websocket: WebSocket):
    """Handle WebSocket connections between Twilio and OpenAI."""
    print("Client connected")
    await websocket.accept()

    async with websockets.connect(
        'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
        extra_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1"
        }
    ) as openai_ws:
        try:
            await initialize_session(openai_ws)
        except Exception as e:
            print(f"Error initializing OpenAI session: {e}")
            return
        
        # Connection specific state
        stream_sid = None
        latest_media_timestamp = 0
        last_assistant_item = None
        mark_queue = []
        response_start_timestamp_twilio = None
        
        # Mark conversation start
        phone_number = None  # Will be set when we get the stream_sid
        
        async def receive_from_twilio():
            """Receive audio data from Twilio and send it to the OpenAI Realtime API."""
            nonlocal stream_sid, latest_media_timestamp, phone_number
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    if data['event'] == 'media' and openai_ws.open:
                        latest_media_timestamp = int(data['media']['timestamp'])
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": data['media']['payload']
                        }
                        await openai_ws.send(json.dumps(audio_append))
                    elif data['event'] == 'start':
                        stream_sid = data['start']['streamSid']
                        # Find the phone number from the stored mapping
                        for phone, sid in session_store["phone_to_streamSid"].items():
                            if sid is None:  # This is our pending call
                                session_store["phone_to_streamSid"][phone] = stream_sid
                                session_store["streamSid_to_phone"][stream_sid] = phone
                                phone_number = phone
                                break
                        
                        if phone_number:
                            save_transcription(phone_number, "", "", stream_sid, is_start=True)
                            # save_transcription(phone_number: str, speaker: str, text: str, stream_sid, is_start=False, is_end=False)

                        print(f"Incoming stream has started {stream_sid}")
                        response_start_timestamp_twilio = None
                        latest_media_timestamp = 0
                        last_assistant_item = None
                    elif data['event'] == 'mark':
                        if mark_queue:
                            mark_queue.pop(0)
            except WebSocketDisconnect:
                if phone_number:
                    save_transcription(phone_number, "", "", is_end=True)
                print("Client disconnected.")
                if openai_ws.open:
                    await openai_ws.close()

        async def send_to_twilio():
            """Receive events from the OpenAI Realtime API, send audio back to Twilio."""
            nonlocal stream_sid, last_assistant_item, response_start_timestamp_twilio

            try:
                print("Starting to receive messages from OpenAI")
                async for openai_message in openai_ws:
                    print(f"Received message from OpenAI: {openai_message}") 
                    response = json.loads(openai_message)
                    if 'response' in response and 'status_details' in response['response']:
                        print("Full error details:", response['response']['status_details'])

                    phone_number = session_store["streamSid_to_phone"].get(stream_sid)

                    # if response['type'] in LOG_EVENT_TYPES:
                    #     print(f"Received event: {response['type']}", response)

                    # Handle user's  transcript
                    if response.get("type") == "conversation.item.input_audio_transcription.completed":
                        user_transcription = response.get("transcript", "")
                        if user_transcription:
                            print(f"\nUser said: {user_transcription}")
                            save_transcription(phone_number, "User", user_transcription, stream_sid)
                            add_memory(phone_number, "user", user_transcription)
    
                    # Handle assistant's completed transcript
                    if response.get("type") == "response.audio_transcript.done":
                        assistant_transcript = response.get("transcript", "")
                        if assistant_transcript:
                            print(f"\nAssistant said: {assistant_transcript}\n")
                            save_transcription(phone_number, "Assistant", assistant_transcript, stream_sid) # Write to file
                            add_memory(phone_number, "assistant", assistant_transcript) # add to memory

                    if response.get('type') == 'response.audio.delta' and 'delta' in response:
                        print("Received audio delta from OpenAI")
                        audio_payload = response['delta']
                        audio_delta = {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {
                                "payload": audio_payload
                            }
                        }
                        print("Sending audio to Twilio")
                        await websocket.send_json(audio_delta)

                        if response_start_timestamp_twilio is None:
                            response_start_timestamp_twilio = latest_media_timestamp
                            if SHOW_TIMING_MATH:
                                print(f"Setting start timestamp for new response: {response_start_timestamp_twilio}ms")

                        # Update last_assistant_item safely
                        if response.get('item_id'):
                            last_assistant_item = response['item_id']

                        await send_mark(websocket, stream_sid)

                    # Trigger an interruption. Your use case might work better using `input_audio_buffer.speech_stopped`, or combining the two.
                    if response.get('type') == 'input_audio_buffer.speech_started':
                        # print("Speech started detected.")
                        if last_assistant_item:
                            # print(f"Interrupting response with id: {last_assistant_item}")
                            await handle_speech_started_event()

            except Exception as e:
                print(f"Error in send_to_twilio: {e}")

        async def handle_speech_started_event():
            """Handle interruption when the caller's speech starts."""
            nonlocal response_start_timestamp_twilio, last_assistant_item
            # print("Handling speech started event.")

            if mark_queue and response_start_timestamp_twilio is not None:
                elapsed_time = latest_media_timestamp - response_start_timestamp_twilio
                if SHOW_TIMING_MATH:
                    print(f"Calculating elapsed time for truncation: {latest_media_timestamp} - {response_start_timestamp_twilio} = {elapsed_time}ms")

                if last_assistant_item:
                    if SHOW_TIMING_MATH:
                        print(f"Truncating item with ID: {last_assistant_item}, Truncated at: {elapsed_time}ms")

                    truncate_event = {
                        "type": "conversation.item.truncate",
                        "item_id": last_assistant_item,
                        "content_index": 0,
                        "audio_end_ms": elapsed_time
                    }
                    await openai_ws.send(json.dumps(truncate_event))

                await websocket.send_json({
                    "event": "clear",
                    "streamSid": stream_sid
                })

                mark_queue.clear()
                last_assistant_item = None
                response_start_timestamp_twilio = None

        async def send_mark(connection, stream_sid):
            if stream_sid:
                mark_event = {
                    "event": "mark",
                    "streamSid": stream_sid,
                    "mark": {"name": "responsePart"}
                }
                await connection.send_json(mark_event)
                mark_queue.append('responsePart')

        await asyncio.gather(receive_from_twilio(), send_to_twilio())


async def initialize_session(openai_ws):
    """Initialize OpenAI session."""

    # Check if user has previous calls
    phone_number = None
    for phone, sid in session_store["phone_to_streamSid"].items():
        if sid is None:
            phone_number = phone
            break
    print(session_store["phone_to_streamSid"].items())
    print(f"\nChecking for previous calls for phone number: {phone_number}")
    is_returning_user = has_previous_calls(phone_number) if phone_number else False
    print(f"Is returning user: {is_returning_user}")
    
    system_message = get_system_prompt(is_returning_user, phone_number)
    print(f"\nSystem message length: {len(system_message)}")
    print(system_message)
    # print("First 100 characters of system message:", system_message[:100])
    
    is_returning_user = has_previous_calls(phone_number) if phone_number else False

    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": system_message,
            "modalities": ["text", "audio"],
            "input_audio_transcription": {"model": "whisper-1"},  # Enable user audio transcription
            "temperature": 0.8,
        },
    }
    print("Sending session update to OpenAI")
    await openai_ws.send(json.dumps(session_update))
    print("Session update sent successfully")

    print("Sending initial message to OpenAI")
    # Modify initial message based on whether it's a returning user
    initial_prompt = (
        "Warmly greet the user as a returning friend, express joy at speaking with them again, and ask how they've been since your last conversation."
        if is_returning_user else
        "Cheerfully greet the user with enthusiasm, introduce yourself, and let them know that you will always be their loyal companion. Happily ask the user how they are doing today."
    )

    initial_message = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": initial_prompt}],
        },
    }
    await openai_ws.send(json.dumps(initial_message))
    print("Initial message sent successfully")

    print("Sending response create command")
    await openai_ws.send(json.dumps({"type": "response.create"}))
    print("Response create command sent successfully")


async def make_call(request: Request):
    """Initiate an outbound call"""
    try:
        data = await request.json()
        phone_number = data.get('phone_number')
        
        if not phone_number:
            return {"error": "Phone number is required", "status": 400}

        # Store the phone number with a placeholder for future streamSid
        session_store["phone_to_streamSid"][phone_number] = None
        print(f"Outbound call to {phone_number}")

        # Use the same TwiML as handle_incoming_call
        response = VoiceResponse()
        response.say("Welcome to My Old Friend")
        response.pause(length=1)
        connect = Connect()
        connect.stream(url=f'wss://{DOMAIN}/media-stream')
        response.append(connect)

        # Make the call with the same TwiML
        call = client.calls.create(
            from_=PHONE_NUMBER_FROM,
            to=phone_number,
            twiml=str(response)
        )
        
        return {"message": f"Call initiated to {phone_number}", "callSid": call.sid}
    except Exception as e:
        print(f"Error in make_call: {e}")
        return {"error": str(e), "status": 500}


