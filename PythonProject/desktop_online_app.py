"""Entry point for the server-connected PyPondo desktop client."""

import os

os.environ["PYPONDO_REMOTE_ONLY"] = "1"

import desktop_app


if __name__ == "__main__":
    raise SystemExit(desktop_app.main())
