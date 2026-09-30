from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from langchain_agent import run_langchain_agent
from jev_router import route_question


app = FastAPI()


app.mount(
    "/static",
    StaticFiles(directory="backend/static"),
    name="static"
)


class QuestionRequest(BaseModel):
    question: str


@app.get("/")
def home():
    return FileResponse("backend/static/index.html")


@app.post("/ask")
def ask_question(request: QuestionRequest):

    # Send the same user question to Jev
    # Jev works as a backend router/verifier layer
    try:
        jev_result = route_question(request.question)

        print("\n" + "=" * 60)
        print("JEV BACKEND")
        print("=" * 60)
        print("Question:", request.question)
        print("Jev result:", jev_result)
        print("=" * 60)

    except Exception as e:
        # If Jev fails, don't break the original chatbot
        print("\n[JEV ERROR]", str(e))
        jev_result = None

    # Original Queryable Chatbot remains responsible for the answer
    answer = run_langchain_agent(request.question)

    return {
        "answer": answer
    }