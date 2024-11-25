from io import BytesIO
import openai
import os

# Load API Key from environment variable
openai.api_key = os.getenv("OPENAI_API_KEY")

async def transcribe_audio_bytes(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """
    Transcribe audio bytes using OpenAI's Whisper API.
    :param audio_bytes: The audio file data as bytes.
    :param filename: Optional filename for the audio file.
    :return: Transcription text or error message.
    """
    try:
        # Ensure audio_bytes is bytes
        if not isinstance(audio_bytes, bytes):
            raise ValueError(f"Expected bytes, got {type(audio_bytes)}")

        # Wrap the bytes in a BytesIO object and assign a name
        audio_file = BytesIO(audio_bytes)
        audio_file.name = filename  # Use the provided or default filename

        # Log input details
        print(f"Transcribing file: {filename}, size: {len(audio_bytes)} bytes")

        # Call the Whisper API
        response = openai.Audio.transcribe(
            model="whisper-1",
            file=audio_file,
        )

        # Validate response
        transcription = response.get("text", "")
        if not isinstance(transcription, str):
            raise ValueError(f"Expected transcription to be a string, got {type(transcription)}")

        return transcription  # Return the transcription as a plain string
    except Exception as e:
        raise RuntimeError(f"Transcription failed: {str(e)}")
