import os
from dotenv import load_dotenv
from sqlalchemy.engine import make_url

load_dotenv()
base_url = os.getenv("TEST_DATABASE_URL") or os.getenv(
    "DATABASE_URL", "postgresql+psycopg://inferenceflow:localdev@localhost:55432/inferenceflow"
)
parsed = make_url(base_url)
if not parsed.database.endswith("_test"):
    parsed = parsed.set(database=parsed.database + "_test")
os.environ["DATABASE_URL"] = parsed.render_as_string(hide_password=False)
