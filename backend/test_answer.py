from answer import generate_answer


question = "show ai employees in bangalore"

database_result = [
    {
        "employee_id": 101,
        "employee_name": "rahul",
        "department": "ai",
        "city": "bangalore",
        "designation": "ai engineer"
    }
]


answer = generate_answer(question, database_result)

print("chatbot answer:")
print(answer)