import openai
import os
from io import BytesIO

# Load API Key from environment variable
openai.api_key = os.getenv("OPENAI_API_KEY")

async def transcribe_audio_bytes(audio_bytes: bytes, filename: str = "audio.wav"):
    """
    Transcribe audio bytes using OpenAI's Whisper API.
    :param audio_bytes: The audio file data as bytes.
    :param filename: Optional filename for the audio file.
    :return: Transcription text or error message.
    """
    try:
        # Wrap the bytes in a BytesIO object and assign a name
        audio_file = BytesIO(audio_bytes)
        audio_file.name = filename  # Use the provided or default filename

        # Call the Whisper API
        response = openai.Audio.transcribe(
            model="whisper-1",
            file=audio_file,
        )

        return {"transcription": response["text"]}
    except Exception as e:
        return {"error": str(e)}
