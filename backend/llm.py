import os
import time

from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY not found")

client = genai.Client(api_key=api_key)


def ask_gemini(question, response_schema=None):

    for attempt in range(3):

        try:
            if response_schema:
                config = {
                    "response_mime_type": "application/json",
                    "response_schema": response_schema
                }
            else:
                config = None

            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=question,
                config=config
            )

            return response.text

        except Exception as error:

            error_message = str(error).lower()

            if "quota" in error_message or "resource_exhausted" in error_message:
                print("gemini quota has been exhausted.")
                print("please wait for the quota to reset or use an approved available quota.")
                raise

            print("gemini request failed:", error)

            if attempt < 2:
                print("retrying...")
                time.sleep(2)
            else:
                raise