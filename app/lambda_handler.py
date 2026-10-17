"""AWS Lambda entrypoint adapter using Mangum.

Wraps the FastAPI application created via the application factory
into a Lambda handler compatible with Amazon API Gateway (HTTP API v2 and REST API).
"""
import logging
from mangum import Mangum
from app.main import app

logger = logging.getLogger("datapulse.lambda")

# Mangum adapter wrapping the FastAPI application.
# Lifespan verification:
# The application lifespan in app/main.py executes non-blocking startup/shutdown logging
# and does not spawn background daemons or blocking event loops.
# Setting lifespan="auto" allows Mangum to safely run lifespan startup during
# Lambda initialization and gracefully clean up.
handler = Mangum(app, lifespan="auto")
