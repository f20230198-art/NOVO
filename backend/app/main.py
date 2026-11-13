import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import init_db
from .routers import (advisor, alerts, assistant, buddies, community, dashboard, demo, family, reports, schedule, sms,
                      trips, users, warnings)
from .services import advisor as advisor_service
from .services import forecast, llm, monitor, notify

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per weather request is too noisy
log = logging.getLogger("seasafe")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    tasks = []
    if os.environ.get("SEASAFE_DISABLE_MONITOR") != "1":
        tasks.append(asyncio.create_task(monitor.run_loop()))
        if settings.telegram_bot_token:
            tasks.append(asyncio.create_task(notify.telegram_poll_loop()))
    log.info(
        "Sea Safe up. AI explanations: %s. SMS: %s. Telegram: %s.",
        advisor_service.provider_label() or "templates (no ANTHROPIC_API_KEY, GEMINI_API_KEY(S) or GROQ_API_KEY(S))",
        "Twilio" if notify.twilio_configured() else "simulated",
        "on" if settings.telegram_bot_token else "off",
    )
    yield
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="Sea Safe API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

for module in (users, advisor, assistant, schedule, trips, reports, warnings, alerts, community, family, buddies, sms, demo, dashboard):
    app.include_router(module.router)


@app.get("/health")
def health():
    return {
        "ok": True,
        "ai": bool(advisor_service.llm_provider()),
        "ai_provider": advisor_service.llm_provider() or None,
        "ai_keys": len(llm.pool()),
        "sms": notify.twilio_configured(),
        "telegram": bool(settings.telegram_bot_token),
        "scenario": forecast.get_scenario(),
    }


@app.get("/", include_in_schema=False)
def root():
    return {"name": "Sea Safe API", "docs": "/docs", "dashboard": "/dashboard", "health": "/health"}
