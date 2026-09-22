from llm import ask_gemini


def generate_answer(question, database_result):
    prompt = f"""
You are a helpful database assistant.

User question:
{question}

Database result:
{database_result}

Answer the user's question using only the information
present in the database result.

Rules:
- Do not invent information.
- Do not add information that is not present in the result.
- Give a clear and simple answer.
- If multiple records are returned, mention the relevant records.
"""

    return ask_gemini(prompt)