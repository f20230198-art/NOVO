"""Test setup: a throwaway SQLite file, no API keys, no background monitor, no network."""
import os
import tempfile

_db = os.path.join(tempfile.mkdtemp(prefix="seasafe-test-"), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db}"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["TWILIO_SID"] = ""
os.environ["TWILIO_TOKEN"] = ""
os.environ["TWILIO_FROM"] = ""
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["ADMIN_KEY"] = "test-admin"
os.environ["SEASAFE_DISABLE_MONITOR"] = "1"
