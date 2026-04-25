"""Export OpenAPI JSON schema from FastAPI app."""

import json
from pathlib import Path

from app.main import app


def export_openapi():
    schema = app.openapi()
    output_path = Path("openapi.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)
    print(f"OpenAPI specification written to {output_path.resolve()}")

if __name__ == "__main__":
    export_openapi()
