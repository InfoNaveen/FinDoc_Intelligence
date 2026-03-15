import os
from decimal import Decimal
from dotenv import load_dotenv
load_dotenv()

# ONE KEY FOR HYPER API
HYPER_API_KEY = os.getenv("HYPER_API_KEY", "")  # Set in .env — never hardcode
# NOTE: The server requires /api/v1, so we must provide it to the SDK.
# Hardcoded to bypass any outdated .env files.
HYPER_API_BASE_URL = "https://apis.hyperbots.com/api/v1"

# BEDROCK — Bearer token from environment
BEDROCK_BEARER_TOKEN = os.getenv("AWS_BEARER_TOKEN_BEDROCK", "")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-20250514-v1:0")
BEDROCK_REGION = "us-east-1"

# PIPELINE TOGGLE
USE_MOCK_HYPER_API = os.getenv("USE_MOCK_HYPER_API", "false").lower() == "true"

# DATABASE
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./findoc.db")

# VALIDATION
MATH_TOLERANCE = Decimal("0.02")
PERCENTAGE_TOLERANCE = Decimal("0.001")
CONFIDENCE_THRESHOLD = 0.75

# SCORING WEIGHTS
WEIGHTS = {
    "extraction_completeness": 0.30,
    "math_validation": 0.35,
    "hallucination_score": 0.20,
    "confidence_score": 0.15,
}

# UPLOAD
UPLOAD_DIR = "uploads"
MAX_FILE_SIZE_MB = 50
ALLOWED_EXTENSIONS = [".pdf"]
