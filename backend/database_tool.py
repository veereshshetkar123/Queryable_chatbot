from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
db = client["queryable_chatbot"]


def run_database_query(query):

    collection_name = query["collection"]
    operation = query.get("operation", "find")
    filters = query.get("filters", {})
    fields = query.get("fields", [])
    pipeline = query.get("pipeline", [])

    collection = db[collection_name]

    # find operation
    if operation == "find":

        projection = {}

        for field in fields:
            projection[field] = 1

        results = collection.find(filters, projection)

        data = []

        for document in results:
            document.pop("_id", None)
            data.append(document)

        return data

    # count operation
    if operation == "count":

        count = collection.count_documents(filters)

        return [{"count": count}]

    # aggregate operation
    if operation == "aggregate":

        results = collection.aggregate(pipeline)

        data = []

        for document in results:
            document.pop("_id", None)
            data.append(document)

        return data

    return {"error": "unsupported operation"}