from langfuse import Langfuse
from config import settings

# Single shared Langfuse client — imported wherever we need to create traces.
# If keys are empty (local dev without Langfuse), SDK silently no-ops.
langfuse = Langfuse(
    public_key=settings.LANGFUSE_PUBLIC_KEY,
    secret_key=settings.LANGFUSE_SECRET_KEY,
    host=settings.LANGFUSE_HOST,
)


def create_trace(**kwargs):
    """Create a Langfuse trace with the current environment tag auto-injected."""
    tags = list(set(kwargs.pop("tags", []) + [settings.ENVIRONMENT]))
    return langfuse.trace(tags=tags, **kwargs)
