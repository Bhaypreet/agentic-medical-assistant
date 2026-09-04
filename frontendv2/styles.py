"""Application styling.

Two rules govern everything here.

Scope by Streamlit's own test ids, not by wrapper divs. A
`st.markdown('<div class="x">')` does NOT wrap the elements that follow -
Streamlit sanitises the unclosed tag and renders it as a sibling - so
class-wrapper scoping is silently inert. [data-testid="stMain"] and
[data-testid="stSidebar"] are stable and do work.

Every colour is a token that flips under prefers-color-scheme. The
previous stylesheet hardcoded light surfaces, so the app rendered dark
text on dark backgrounds for anyone using dark mode.
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
    --shadow:       rgba(15, 118, 110, 0.20);
    --shadow-soft:  rgba(15, 23, 42, 0.08);
}

@media (prefers-color-scheme: dark) {
    :root {
        --brand:        #2dd4bf;
        --brand-deep:   #0f766e;
        --brand-tint:   #12312d;
        --brand-line:   #245f57;
        --brand-text:   #5eead4;
        --surface:      #0e1117;
        --surface-2:    #161b25;
        --line:         #2a3341;
        --muted:        #94a3b8;
        --shadow:       rgba(0, 0, 0, 0.45);
        --shadow-soft:  rgba(0, 0, 0, 0.35);
    }
}

html, body, [class*="css"], .stMarkdown {
    font-family: 'Plus Jakarta Sans', -apple-system, "Segoe UI", Roboto, sans-serif;
}

.block-container {
    padding-top: 1.25rem;
    padding-bottom: 5rem;
    max-width: 1060px;
}

/* ---------------------------------------------------------- header -- */

.app-header {
    background: linear-gradient(120deg, var(--brand-deep) 0%, var(--brand) 100%);
    padding: 1.3rem 1.7rem;
    border-radius: 14px;
    color: #ffffff;
    margin-bottom: 1rem;
    box-shadow: 0 10px 26px var(--shadow);
}

.app-header h1 {
    margin: 0;
    font-size: 1.5rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #ffffff;
}

.app-header p {
    margin: 0.25rem 0 0 0;
    opacity: 0.9;
    font-size: 0.88rem;
    color: #ffffff;
}

/* --------------------------------------------------------- sidebar -- */

[data-testid="stSidebar"] {
    background: var(--surface-2);
    border-right: 1px solid var(--line);
}

[data-testid="stSidebar"] .stButton button {
    text-align: left;
    justify-content: flex-start;
    font-weight: 500;
}

/* ------------------------------------------------------------ chat -- */

[data-testid="stChatMessage"] {
    background: var(--surface-2);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 0.8rem 1rem;
    margin-bottom: 0.55rem;
}

/* Answers are markdown from a language model, which routinely opens with
   a top-level heading. Streamlit shifts markdown headings down one level
   (# renders as <h2>), wraps them in stHeadingWithActionElements, and
   puts the font-size on an inner <span> - so rules written against h1,
   or against the heading element alone, never take effect. At Streamlit's
   defaults a "#" heading lands at 36px inside a chat bubble and dwarfs
   the conversation around it. */
[data-testid="stChatMessage"] h1, [data-testid="stChatMessage"] h1 span,
[data-testid="stChatMessage"] h2, [data-testid="stChatMessage"] h2 span {
    font-size: 1.3rem !important;
    line-height: 1.35 !important;
}

[data-testid="stChatMessage"] h3, [data-testid="stChatMessage"] h3 span {
    font-size: 1.1rem !important;
    line-height: 1.4 !important;
}

[data-testid="stChatMessage"] h4, [data-testid="stChatMessage"] h4 span,
[data-testid="stChatMessage"] h5, [data-testid="stChatMessage"] h5 span,
[data-testid="stChatMessage"] h6, [data-testid="stChatMessage"] h6 span {
    font-size: 0.98rem !important;
    line-height: 1.4 !important;
}

[data-testid="stChatMessage"] :is(h1, h2, h3, h4, h5, h6) {
    font-weight: 600 !important;
    letter-spacing: -0.01em;
    padding: 0 !important;
    margin: 0.85rem 0 0.35rem !important;
}

/* The first heading in a message should not push it away from the top. */
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"]
    > div:first-child :is(h1, h2, h3) {
    margin-top: 0.1rem !important;
}

/* Streamlit adds a hover anchor link to every heading; inside a chat
   bubble it is only clutter. */
[data-testid="stChatMessage"] [data-testid="stHeaderActionElements"] {
    display: none !important;
}

[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] li { font-size: 0.94rem; line-height: 1.6; }

[data-testid="stChatMessage"] hr { margin: 0.8rem 0; opacity: 0.35; }

[data-testid="stChatMessage"] table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.87rem;
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

/* Wide content scrolls inside itself rather than widening the page. */
[data-testid="stChatMessage"] pre,
[data-testid="stDataFrame"] { overflow-x: auto; max-width: 100%; }

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

/* Follow-up suggestion chips: the only buttons laid out in columns in
   the main area. Scoping to stMain keeps the sidebar's chat and delete
   buttons out of it - the previous rule matched every button in any
   column and restyled those too. */
[data-testid="stMain"] [data-testid="stHorizontalBlock"] .stButton button {
    background: var(--brand-tint);
    border: 1px solid var(--brand-line);
    color: var(--brand-text);
    font-size: 0.8rem;
    font-weight: 500;
    white-space: normal;
    line-height: 1.3;
    min-height: 2.6rem;
}

/* Attach and microphone. Both are popovers, so the old .icon-btn rule
   for buttons never matched them and they rendered as default pills
   with a dropdown chevron. */
[data-testid="stMain"] [data-testid="stPopover"] button {
    border-radius: 999px !important;
    width: 44px;
    min-width: 44px;
    height: 44px;
    padding: 0 !important;
    font-size: 1.05rem;
    border: 1px solid var(--line);
    background: var(--surface);
    justify-content: center;
}

/* Streamlit appends a dropdown chevron inside the popover trigger. It is
   a Material icon <span>, not an <svg>, and on a 44px circle it crowds
   out the icon itself. */
[data-testid="stMain"] [data-testid="stPopover"] button [data-testid="stIconMaterial"] {
    display: none !important;
}

[data-testid="stMain"] [data-testid="stPopover"] button:hover {
    border-color: var(--brand);
}

/* Primary actions carry the brand colour. This is set here rather than
   left to .streamlit/config.toml's primaryColor because that file is
   only found when Streamlit is launched from the directory holding it -
   running the app from frontendv2/ would otherwise fall back to
   Streamlit's default red, which reads as an error state on a sign-in
   button. */
button[kind="primary"],
button[data-testid="stBaseButton-primary"],
button[data-testid="stBaseButton-primaryFormSubmit"] {
    background: var(--brand-deep) !important;
    border-color: var(--brand-deep) !important;
    color: #ffffff !important;
}

button[kind="primary"]:hover,
button[data-testid="stBaseButton-primary"]:hover,
button[data-testid="stBaseButton-primaryFormSubmit"]:hover {
    background: var(--brand) !important;
    border-color: var(--brand) !important;
}

/* The sign-in card. */
[data-testid="stForm"] {
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 1.25rem 1.4rem;
    background: var(--surface-2);
}

/* ------------------------------------------------------ containers -- */

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

[data-testid="stCaptionContainer"] { color: var(--muted); }

</style>
"""
