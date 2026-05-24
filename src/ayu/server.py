from fastapi import FastAPI

server = FastAPI(title="ayu")


@server.get("/health")
async def health() -> dict:
    return {"status": "ok"}


def run_server(host: str = "127.0.0.1", port: int = 8000, workers: int = 1) -> None:
    import uvicorn
    uvicorn.run("ayu.server:server", host=host, port=port, workers=workers)
