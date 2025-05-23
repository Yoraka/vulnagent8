from typing import Any
import os # Import os to access environment variables

DEFAULT_MODEL_ID = "openrouter/google/gemini-2.5-flash-preview-05-20"

from agno.models.xai import xAI
from agno.models.openai import OpenAIChat
from agno.models.openai.like import OpenAILike # Import OpenAILike
# Add other necessary model imports here if expanding
# from agno.models.google import Gemini # Example if re-added
# from agno.models.openrouter import OpenRouter # Example - Agno might not have a dedicated OpenRouter class

def get_model_instance(model_id_str: str) -> Any:
    """
    Returns an initialized Agno model instance based on the model_id string.
    Handles OpenRouter models by using OpenAILike with custom base_url and api_key.
    """
    if model_id_str.startswith("openrouter/"):
        openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        # Extract the actual model ID for OpenRouter, e.g., "google/gemini-2.5-flash-preview-05-20"
        actual_model_id = model_id_str.split("openrouter/", 1)[1]
        
        if not openrouter_api_key:
            print("Warning: OPENROUTER_API_KEY environment variable not set. OpenRouter models may not work.")
            # Attempt to initialize without api_key, though this is unlikely to work for paid models
            # and OpenAILike might require api_key.
            return OpenAILike(
                id=actual_model_id,
                base_url="https://openrouter.ai/api/v1"
                # api_key will be None, which might cause issues depending on OpenAILike implementation
            )
        
        return OpenAILike(
            id=actual_model_id, 
            base_url="https://openrouter.ai/api/v1",
            api_key=openrouter_api_key
        )
    elif model_id_str == "grok-3-beta" or "grok" in model_id_str.lower():
        return xAI(id=model_id_str if model_id_str else "grok-3-beta")
    elif model_id_str == "gpt-4o" or "gpt-4" in model_id_str.lower(): 
        return OpenAIChat(id=model_id_str if model_id_str else "gpt-4o")
    # TODO: Add mappings for other models like "o3-mini", "qwen/qwen3-235b-a22b"
    # Example for direct Gemini integration (if ever needed):
    # elif "gemini" in model_id_str.lower() and not model_id_str.startswith("openrouter/"):
    #     from agno.models.google import Gemini # Import here if used conditionally
    #     google_api_key = os.getenv("GOOGLE_API_KEY") # Assuming GOOGLE_API_KEY for direct use
    #     if not google_api_key:
    #         print("Warning: GOOGLE_API_KEY environment variable not set for direct Gemini usage.")
    #     return Gemini(id=actual_model_id, api_key=google_api_key) # actual_model_id would need to be just the gemini part
    else:
        # Default fallback if no specific model is matched
        print(f"Warning: Model ID '{model_id_str}' not explicitly recognized. Falling back to Grok.")
        return xAI(id="grok-3-beta") 