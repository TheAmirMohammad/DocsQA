"""DocsQA entry point."""

import os

import uvicorn


def main():
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    print(f"Starting DocsQA server on {host}:{port}...")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    main()
