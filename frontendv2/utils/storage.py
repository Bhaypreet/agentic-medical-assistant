import json
import os
import uuid

SESSION_FOLDER = "frontendv2/sessions"

os.makedirs(
    SESSION_FOLDER,
    exist_ok=True
)


def create_chat():

    chat = {
        "id": str(uuid.uuid4()),
        "chat_name": "New Chat",
        "messages": [],
        "report": None,
        "report_id": None,
        "summary": "",
        "uploaded_file": ""
    }

    save_chat(chat)

    return chat


def save_chat(chat):

    path = os.path.join(
        SESSION_FOLDER,
        f"{chat['id']}.json"
    )

    with open(path, "w", encoding="utf-8") as f:

        json.dump(
            chat,
            f,
            indent=4,
            ensure_ascii=False
        )


def load_chat(chat_id):

    path = os.path.join(
        SESSION_FOLDER,
        f"{chat_id}.json"
    )

    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as f:

        return json.load(f)


def load_all_chats():

    chats = []

    for file in os.listdir(SESSION_FOLDER):

        if file.endswith(".json"):

            with open(
                os.path.join(
                    SESSION_FOLDER,
                    file
                ),
                "r",
                encoding="utf-8"
            ) as f:

                chats.append(
                    json.load(f)
                )

    chats.sort(
        key=lambda x: x["chat_name"]
    )

    return chats


def delete_chat(chat_id):

    path = os.path.join(
        SESSION_FOLDER,
        f"{chat_id}.json"
    )

    if os.path.exists(path):

        os.remove(path)