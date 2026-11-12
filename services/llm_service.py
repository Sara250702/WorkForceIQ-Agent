
import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()


def get_groq_client():
    """Create and return a Groq client."""
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise ValueError("GROQ_API_KEY is missing from .env")

    return Groq(api_key=api_key)


def generate_response(prompt):
    """Send a prompt to Groq and return its response."""
    model = os.getenv("GROQ_MODEL")

    if not model:
        raise ValueError("GROQ_MODEL is missing from .env")

    client = get_groq_client()

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content