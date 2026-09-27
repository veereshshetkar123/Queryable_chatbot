import sys

sys.path.insert(0, "backend")

from langchain_agent import agent


question = "show me the ai employee in bangalore"

result = agent.invoke(
    {
        "messages": [
            {
                "role": "user",
                "content": question
            }
        ]
    }
)

print("agent result:")
print(result["messages"][-1].content)