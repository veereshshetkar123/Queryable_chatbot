import os
import requests
from dotenv import load_dotenv

load_dotenv()


def route_question(question):
    url = "https://openrouter.ai/api/alpha/decisions"

    headers = {
        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "typesafe/jev-1.13",
        "state": question,
        "questions": {
            "route": {
                "type": "choice",
                "instructions": "Which path should handle this request?",
                "criteria": {
                    "database_query": "The user is asking for information that should be retrieved from the MongoDB database.",
                    "browser_task": "The user needs information or an action through a web browser.",
                    "general_chat": "The user is asking a general conversational question that does not require the database or browser."
                }
            }
        }
    }

    response = requests.post(
        url,
        headers=headers,
        json=data
    )

    response.raise_for_status()

    return response.json()