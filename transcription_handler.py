from fastapi import APIRouter, File, UploadFile
import openai
import os
from io import BytesIO

# Load API Key from environment variable
openai.api_key = os.getenv("OPENAI_API_KEY")

router = APIRouter()

@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Transcribe audio using OpenAI's Whisper API.
    """
    try:
        # Read the uploaded audio file
        audio_bytes = await file.read()

        # Wrap the bytes in a BytesIO object and assign a name
        audio_file = BytesIO(audio_bytes)
        audio_file.name = file.filename  # Use the original filename or assign one manually if needed

        # Call the Whisper API
        response = openai.Audio.transcribe(
            model="whisper-1",
            file=audio_file,
        )

        return {"transcription": response["text"]}
    except Exception as e:
        return {"error": str(e)}
