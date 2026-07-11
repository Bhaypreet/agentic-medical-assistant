import json
import os

SESSIONS_FILE = "sessions_store.json"


class SessionManager:

    def __init__(self):
        self.sessions = self._load()

    def _load(self):
        if os.path.exists(SESSIONS_FILE):
            try:
                with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _persist(self):
        with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.sessions, f, indent=2)

    def create_session(self, session_id):

        if session_id not in self.sessions:

            self.sessions[session_id] = {
                "report_id": None,
                "messages": [],
                "chat_name": "New Chat",
                "pending_specialist": None,
                "pending_clarification": None
            }
            self._persist()

    def save_report(self, session_id, report_id):
        self.create_session(session_id)
        self.sessions[session_id]["report_id"] = report_id
        self._persist()

    def get_report(self, session_id):
        self.create_session(session_id)
        return self.sessions[session_id]["report_id"]

    def save_report_data(self, session_id, analysis, summary):
        self.create_session(session_id)
        self.sessions[session_id]["report_analysis"] = analysis
        self.sessions[session_id]["report_summary"] = summary
        self._persist()

    def get_report_data(self, session_id):
        self.create_session(session_id)
        return {
            "analysis": self.sessions[session_id].get("report_analysis", []),
            "summary": self.sessions[session_id].get("report_summary", "")
        }

    def add_message(self, session_id, role, content):
        self.create_session(session_id)
        self.sessions[session_id]["messages"].append({"role": role, "content": content})
        self.sessions[session_id]["messages"] = self.sessions[session_id]["messages"][-20:]
        self._persist()

    def get_messages(self, session_id):
        self.create_session(session_id)
        return self.sessions[session_id]["messages"]

    def set_chat_name(self, session_id, name):
        self.create_session(session_id)
        self.sessions[session_id]["chat_name"] = name
        self._persist()

    def get_chat_name(self, session_id):
        self.create_session(session_id)
        return self.sessions[session_id]["chat_name"]

    def get_all_sessions(self):
        return self.sessions

    def clear_chat(self, session_id):
        if session_id in self.sessions:
            del self.sessions[session_id]
            self._persist()

    def set_pending_specialist(self, session_id, specialist):
        self.create_session(session_id)
        self.sessions[session_id]["pending_specialist"] = specialist
        self._persist()

    def get_pending_specialist(self, session_id):
        self.create_session(session_id)
        return self.sessions[session_id].get("pending_specialist")

    def clear_pending_specialist(self, session_id):
        self.create_session(session_id)
        self.sessions[session_id]["pending_specialist"] = None
        self._persist()

    # -------------------------------------------------
    # Pending Clarification (agent asks ONE follow-up
    # question before finalizing symptom severity)
    # -------------------------------------------------

    def set_pending_clarification(self, session_id, original_query):
        self.create_session(session_id)
        self.sessions[session_id]["pending_clarification"] = original_query
        self._persist()

    def get_pending_clarification(self, session_id):
        self.create_session(session_id)
        return self.sessions[session_id].get("pending_clarification")

    def clear_pending_clarification(self, session_id):
        self.create_session(session_id)
        self.sessions[session_id]["pending_clarification"] = None
        self._persist()


session_manager = SessionManager()