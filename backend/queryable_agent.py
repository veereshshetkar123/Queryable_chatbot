import json

from agent import understand_question
from query_executor import execute_query
from answer import generate_answer


def run_agent(question):
    print("understanding question...")

    query_text = understand_question(question)

    print("generated query:")
    print(query_text)

    query = json.loads(query_text)

    print("executing query...")

    database_result = execute_query(query)

    if isinstance(database_result, dict) and "error" in database_result:
        return database_result["error"]

    print("generating answer...")

    answer = generate_answer(
        question,
        database_result
    )

    return answer