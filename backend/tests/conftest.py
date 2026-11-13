"""Test setup: a throwaway SQLite file, no API keys, no background monitor, no network."""
import os
import tempfile

_db = os.path.join(tempfile.mkdtemp(prefix="seasafe-test-"), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
for _name in (
    "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GEMINI_API_KEYS",
    "GROQ_API_KEY", "GROQ_API_KEY_2", "GROQ_API_KEY_3", "GROQ_API_KEY_4", "GROQ_API_KEYS", "LLM_MODEL",
    "TWILIO_SID", "TWILIO_TOKEN", "TWILIO_FROM", "TELEGRAM_BOT_TOKEN",
):
    os.environ[_name] = ""
os.environ["ADMIN_KEY"] = "test-admin"
os.environ["SEASAFE_DISABLE_MONITOR"] = "1"
os.environ["DEMO_MODE"] = "true"
