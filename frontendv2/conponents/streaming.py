import re
import time
import streamlit as st


def stream_text(text):

    placeholder = st.empty()
    current = ""

    # split on whitespace but KEEP the whitespace tokens (including \n) -
    # this preserves markdown structure (tables, bullets, headers) while
    # still giving a typewriter effect
    tokens = re.split(r"(\s+)", text)

    for token in tokens:

        current += token
        placeholder.markdown(current)

        if token.strip():
            time.sleep(0.02)

    return current