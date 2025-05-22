from typing import Any

from agno.models.xai import xAI
from agno.models.openai import OpenAIChat
# Add other necessary model imports here if expanding
# from agno.models.google import Gemini # Example if re-added
# from agno.models.openrouter import OpenRouter # Example

def get_model_instance(model_id_str: str) -> Any:
    """
    Returns an initialized Agno model instance based on the model_id string.
    """
    if model_id_str == "grok-3-beta" or "grok" in model_id_str.lower():
        return xAI(id=model_id_str if model_id_str else "grok-3-beta")
    elif model_id_str == "gpt-4o" or "gpt-4" in model_id_str.lower(): 
        return OpenAIChat(id=model_id_str if model_id_str else "gpt-4o")
    # TODO: Add mappings for other models like "o3-mini", "qwen/qwen3-235b-a22b"
    # Example if o3-mini is via OpenRouter:
    # elif model_id_str == "o3-mini":
    #     return OpenRouter(id="<actual_o3_mini_id_on_openrouter>") 
    # Example for Gemini (if re-added):
    # elif "gemini" in model_id_str.lower():
    #     return Gemini(id=model_id_str if model_id_str else "gemini-1.5-pro-latest")
    else:
        return xAI(id="grok-3-beta") 