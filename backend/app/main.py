from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import Base, engine
from .routers import editorial, editorial_state, health, oauth_tiktok, publishing, sourceguard, sources, stories, story_packs

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Source-first backend foundation for Headline Avenue.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


app.include_router(health.router)
app.include_router(sources.router, prefix=settings.api_v1_prefix)
app.include_router(stories.router, prefix=settings.api_v1_prefix)
app.include_router(editorial.router, prefix=settings.api_v1_prefix)
app.include_router(editorial_state.router, prefix=settings.api_v1_prefix)
app.include_router(story_packs.router, prefix=settings.api_v1_prefix)
app.include_router(publishing.router, prefix=settings.api_v1_prefix)
app.include_router(oauth_tiktok.router, prefix=settings.api_v1_prefix)
app.include_router(sourceguard.router, prefix=settings.api_v1_prefix)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "Headline Avenue API",
        "status": "foundation-ready",
        "docs": "/docs",
    }
