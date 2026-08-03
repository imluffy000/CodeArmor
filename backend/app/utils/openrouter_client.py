from langchain_openai import ChatOpenAI

from app.core.config import OPENROUTER_API_KEY
from app.core.constants import DEFAULT_TEMPERATURE, OPENROUTER_MODEL

llm = ChatOpenAI(
    model=OPENROUTER_MODEL,
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    temperature=DEFAULT_TEMPERATURE,
    max_tokens=4096,
)
