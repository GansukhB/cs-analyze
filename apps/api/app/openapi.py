"""Write the OpenAPI schema shared with apps/public. No running server needed.

python -m app.openapi [output-path]
"""

import json
import sys
from pathlib import Path

from app.main import app

DEFAULT_OUTPUT = Path(__file__).resolve().parents[3] / "packages" / "openapi" / "openapi.json"


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    output.write_text(json.dumps(app.openapi(), indent=2) + "\n")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
