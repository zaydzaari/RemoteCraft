"""Command-line entry point."""

import os

import uvicorn
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    host = os.getenv("REMOTECRAFT_BIND_HOST", "127.0.0.1")
    try:
        port = int(os.getenv("REMOTECRAFT_PORT", "8000"))
    except ValueError as exc:
        raise SystemExit("REMOTECRAFT_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("REMOTECRAFT_PORT must be between 1 and 65535")
    uvicorn.run("remotecraft.api:create_app", factory=True, host=host, port=port)


if __name__ == "__main__":
    main()
