import asyncio

from transcription_handler import transcribe_audio_bytes
from voice_handler import handle_audio_transcribe

async def test_handle_audio_processing():
    """
    Test the handle_audio_processing function with a sample audio file.
    """
    audio_file_path = "test_audio.mp3"  # Replace with your test audio file

    # Read the audio file as bytes
    with open(audio_file_path, "rb") as audio_file:
        audio_bytes = audio_file.read()

    # Test the transcription function
    transcription = await handle_audio_transcribe(audio_bytes)

    if transcription:
        print(f"Transcription Result:\n{transcription}")
    else:
        print("Failed to transcribe audio.")

# Run the test
if __name__ == "__main__":
    asyncio.run(test_handle_audio_processing())
