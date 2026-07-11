import requests

from config import FASTAPI_URL


def chat(query, session_id):

    response = requests.post(
        f"{FASTAPI_URL}/chat",
        json={"query": query, "session_id": session_id, "location": ""}
    )
    response.raise_for_status()
    return response.json()


def upload_report(file_path, session_id):

    with open(file_path, "rb") as f:
        response = requests.post(
            f"{FASTAPI_URL}/upload-report",
            params={"session_id": session_id},
            files={"file": f}
        )
    response.raise_for_status()
    return response.json()


def report_chat(question, session_id):

    response = requests.post(
        f"{FASTAPI_URL}/report-chat",
        params={"session_id": session_id, "question": question}
    )
    response.raise_for_status()
    return response.json()


def transcribe_voice(audio_bytes):

    response = requests.post(
        f"{FASTAPI_URL}/transcribe",
        files={"file": ("recording.wav", audio_bytes, "audio/wav")}
    )
    response.raise_for_status()
    return response.json()["text"]


def speak_text(text, gender="female"):

    response = requests.post(
        f"{FASTAPI_URL}/speak",
        params={"text": text, "gender": gender}
    )
    response.raise_for_status()
    return response.content

def download_report_pdf(session_id):

    response = requests.get(
        f"{FASTAPI_URL}/download-report",
        params={"session_id": session_id}
    )
    response.raise_for_status()
    return response.content