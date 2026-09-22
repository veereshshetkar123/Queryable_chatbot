from pymongo import MongoClient


client = MongoClient("mongodb://localhost:27017")
db = client["queryable_chatbot"]


def run_database_query(query):
    collection_name = query["collection"]
    filters = query["filters"]
    fields = query["fields"]

    collection = db[collection_name]

    projection = {}

    for field in fields:
        projection[field] = 1

    results = collection.find(filters, projection)

    data = []

    for document in results:
        document.pop("_id", None)
        data.append(document)

    return data