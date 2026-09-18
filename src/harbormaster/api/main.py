from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes import autonomy, chaos, ledger, metrics, review, runs

app = FastAPI(title="Harbormaster")
app.mount("/web", StaticFiles(directory="web"), name="web")

app.include_router(runs.router)
app.include_router(review.router)
app.include_router(ledger.router)
app.include_router(chaos.router)
app.include_router(autonomy.router)
app.include_router(metrics.router)
