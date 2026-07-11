import os
import sys

# make sure the project root (parent of tests/) is importable as "app.xxx"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ChatGroq needs an api_key to even construct - dummy value is fine since
# our tests mock every actual network/LLM call
os.environ.setdefault("GROQ_API_KEY", "test-dummy-key-for-ci")