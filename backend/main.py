from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from langchain_agent import run_langchain_agent


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
    answer = run_langchain_agent(request.question)

    return {
        "answer": answer
    }