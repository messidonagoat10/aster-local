"""Run the app on the IPv4 loopback interface only."""

import uvicorn

from assistant_core.app import app
from assistant_core.config import Settings


if __name__ == "__main__":
    settings = Settings.from_environment()
    uvicorn.run(app, host="127.0.0.1", port=settings.port, access_log=False)

