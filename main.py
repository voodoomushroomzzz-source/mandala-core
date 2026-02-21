import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tectosphaera.api.router_engineer import router as engineer_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mandala-core")

app = FastAPI(title="Mandala Core")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(engineer_router, tags=["engineer"])


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)