import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def transcribe_audio(audio_path: str) -> str:
    """Converts recorded speech to text using Groq's Whisper model."""

    with open(audio_path, "rb") as f:
        transcription = groq_client.audio.transcriptions.create(
            file=(audio_path, f.read()),
            model="whisper-large-v3-turbo"
        )

    return transcription.text