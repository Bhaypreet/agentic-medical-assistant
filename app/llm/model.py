import os
import re
import time

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from groq import RateLimitError

load_dotenv()

model = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0.2,
    api_key=os.getenv("GROQ_API_KEY")
)


def safe_invoke(prompt, max_retries: int = 5):
    """
    Wraps model.invoke() with automatic retry on Groq rate limits.
    Free tier has a tokens-per-minute cap - this waits and retries
    instead of crashing the whole request.
    """

    for attempt in range(max_retries):

        try:
            return model.invoke(prompt)

        except RateLimitError as e:

            wait_time = 5.0

            match = re.search(r"try again in ([\d.]+)s", str(e))
            if match:
                wait_time = float(match.group(1)) + 1

            print(
                f"⏳ Groq rate limit hit - waiting {wait_time:.1f}s "
                f"(attempt {attempt + 1}/{max_retries})"
            )

            time.sleep(wait_time)

    raise Exception(
        "Groq rate limit exceeded repeatedly. Try again in a minute, "
        "or reduce report size / upgrade Groq tier."
    )