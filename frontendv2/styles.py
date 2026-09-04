"""Application styling.

Everything here is theme-aware. The previous stylesheet hardcoded light
surfaces (a #f8fafc sidebar, pale button fills), so the app rendered
unreadably for anyone using Streamlit in dark mode. Colours now come from
tokens that flip under prefers-color-scheme, and Streamlit's own theme
handles the rest via .streamlit/config.toml.
"""

CSS = """
<style>

@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

:root {
    --brand:        #0d9488;
    --brand-deep:   #0f766e;
    --brand-tint:   #ecfdf9;
    --brand-line:   #99f6e4;
    --brand-text:   #0f766e;
    --surface:      #ffffff;
    --surface-2:    #f8fafc;
    --line:         #e2e8f0;
    --muted:        #64748b;
    --shadow:       rgba(15, 118, 110, 0.18);
    --shadow-soft:  rgba(15, 23, 42, 0.08);
}

@media (prefers-color-scheme: dark) {
    :root {
        --brand:        #2dd4bf;
        --brand-deep:   #0f766e;
        --brand-tint:   #0f2e2b;
        --brand-line:   #1f5f57;
        --brand-text:   #5eead4;
        --surface:      #0e1117;
        --surface-2:    #161b25;
        --line:         #2a3341;
        --muted:        #94a3b8;
        --shadow:       rgba(0, 0, 0, 0.45);
        --shadow-soft:  rgba(0, 0, 0, 0.35);
    }
}

html, body, [class*="css"], .stMarkdown, .stChatMessage {
    font-family: 'Plus Jakarta Sans', -apple-system, "Segoe UI", Roboto, sans-serif;
}

.block-container {
    padding-top: 1.25rem;
    padding-bottom: 6rem;
    max-width: 1080px;
}

/* ---------------------------------------------------------- header -- */

.app-header {
    background: linear-gradient(135deg, var(--brand-deep) 0%, var(--brand) 100%);
    padding: 1.35rem 1.75rem;
    border-radius: 14px;
    color: #ffffff;
    margin-bottom: 1.1rem;
    box-shadow: 0 10px 28px var(--shadow);
}

.app-header h1 {
    margin: 0;
    font-size: 1.55rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #ffffff;
}

.app-header p {
    margin: 0.25rem 0 0 0;
    opacity: 0.92;
    font-size: 0.9rem;
    color: #ffffff;
}

/* --------------------------------------------------------- sidebar -- */

section[data-testid="stSidebar"] {
    background: var(--surface-2);
    border-right: 1px solid var(--line);
}

section[data-testid="stSidebar"] .stButton button {
    text-align: left;
    justify-content: flex-start;
    font-weight: 500;
}

/* ------------------------------------------------------------ chat -- */

[data-testid="stChatMessage"] {
    background: var(--surface-2);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 0.85rem 1.05rem;
    margin-bottom: 0.6rem;
}

/* The assistant's turn is the one being read, so give it the accent. */
[data-testid="stChatMessage"]:has(img[alt="assistant avatar"]),
[data-testid="stChatMessage"]:nth-child(even) {
    border-left: 3px solid var(--brand);
}

[data-testid="stChatMessage"] table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.88rem;
}

[data-testid="stChatMessage"] th,
[data-testid="stChatMessage"] td {
    border: 1px solid var(--line);
    padding: 0.35rem 0.55rem;
    text-align: left;
}

[data-testid="stChatMessage"] th {
    background: var(--brand-tint);
    color: var(--brand-text);
    font-weight: 600;
}

/* --------------------------------------------------------- buttons -- */

.stButton button {
    border-radius: 10px;
    font-weight: 500;
    transition: transform 0.12s ease, box-shadow 0.12s ease;
}

.stButton button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px var(--shadow-soft);
}

/* Follow-up suggestion chips. Scoped to the container the app wraps them
   in - the old rule targeted every button inside any column, so it also
   restyled the sidebar's delete buttons. */
.suggestion-row .stButton button {
    background: var(--brand-tint);
    border: 1px solid var(--brand-line);
    color: var(--brand-text);
    font-size: 0.82rem;
    font-weight: 500;
    white-space: normal;
    line-height: 1.3;
    min-height: 2.6rem;
}

/* Round icon buttons for attach and microphone. These are popovers now,
   not plain buttons, so the old .icon-btn rule no longer matched
   anything and both controls lost their styling. */
.composer-row [data-testid="stPopover"] > button,
.composer-row [data-testid="stPopoverButton"] {
    border-radius: 50% !important;
    width: 44px;
    height: 44px;
    min-height: 44px;
    padding: 0 !important;
    font-size: 1.1rem;
    border: 1px solid var(--line);
    background: var(--surface);
}

.composer-row [data-testid="stPopover"] > button:hover {
    border-color: var(--brand);
    color: var(--brand-text);
}

/* ---------------------------------------------------------- status -- */

[data-testid="stStatusWidget"], [data-testid="stExpander"] {
    border-radius: 12px;
}

[data-testid="stExpander"] details {
    border: 1px solid var(--line);
    border-radius: 12px;
    background: var(--surface);
}

[data-testid="stMetric"] {
    background: var(--surface-2);
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 0.7rem 0.9rem;
}

/* Keep the disclaimer quiet but present. */
.stCaption, [data-testid="stCaptionContainer"] {
    color: var(--muted);
}

/* Wide content must scroll inside itself, never widen the page. */
[data-testid="stChatMessage"] pre,
[data-testid="stDataFrame"] {
    overflow-x: auto;
    max-width: 100%;
}

</style>
"""
