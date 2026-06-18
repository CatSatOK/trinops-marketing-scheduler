"""FastAPI app: campaign scheduling + lead capture API + static dashboard."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from marketing.config import get_settings
from marketing.database import init_db, session_scope
from marketing.logging_conf import setup_logging
from marketing.scheduler import start_scheduler, stop_scheduler
from marketing.seed_loader import load_seed_campaigns, load_seed_leads
from api.routes.campaigns import router as campaigns_router
from api.routes.leads import router as leads_router
from api.auth import require_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    with session_scope() as session:
        load_seed_campaigns(session, get_settings())
        load_seed_leads(session, get_settings())
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Trinops Marketing Scheduler", lifespan=lifespan)
app.include_router(campaigns_router, dependencies=[Depends(require_admin)])
app.include_router(leads_router)
app.mount("/", StaticFiles(directory="frontend", html=True), name="dashboard")
