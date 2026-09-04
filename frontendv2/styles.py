CSS = """
<style>

@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Poppins', sans-serif;
}

.main {
    padding-top: 0.5rem;
}

/* Left-align content instead of centering it in the wide layout */
.block-container {
    padding-top: 1.5rem;
    max-width: 1100px;
    margin-left: 1rem !important;
    margin-right: auto !important;
}

.app-header {
    background: linear-gradient(135deg, #0f766e 0%, #14b8a6 100%);
    padding: 1.4rem 1.8rem;
    border-radius: 16px;
    color: white;
    margin-bottom: 1.2rem;
    box-shadow: 0 8px 24px rgba(15, 118, 110, 0.25);
}

.app-header h1 {
    margin: 0;
    font-size: 1.6rem;
    font-weight: 700;
}

.app-header p {
    margin: 0.2rem 0 0 0;
    opacity: 0.9;
    font-size: 0.9rem;
}

.stChatMessage {
    border-radius: 16px;
    padding: 0.4rem 0.2rem;
}

section[data-testid="stSidebar"] {
    background: #f8fafc;
    border-right: 1px solid #e2e8f0;
}

.stButton button {
    border-radius: 10px;
    transition: all 0.15s ease-in-out;
}

.stButton button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 10px rgba(0,0,0,0.08);
}

div[data-testid="column"] .stButton button {
    background: #f0fdfa;
    border: 1px solid #99f6e4;
    color: #0f766e;
    font-size: 0.82rem;
}

/* WhatsApp-style small round icon buttons for attach/mic */
.icon-btn button {
    border-radius: 50% !important;
    width: 42px;
    height: 42px;
    padding: 0 !important;
    font-size: 1.1rem;
}

</style>
"""
