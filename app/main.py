"""FastAPI app."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import router

app = FastAPI(title="tplus", description="Settlement reconciliation engine")

origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
