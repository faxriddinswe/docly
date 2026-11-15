"""Write the OpenAPI schema to a file: uv run python scripts/dump_openapi.py ../frontend/openapi.json"""

import json
import sys

from app.main import create_app

with open(sys.argv[1], "w") as f:
    json.dump(create_app().openapi(), f, indent=2, sort_keys=True)
    f.write("\n")
