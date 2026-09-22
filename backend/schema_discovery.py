from pymongo import MongoClient


client = MongoClient("mongodb://localhost:27017")
db = client["queryable_chatbot"]


def get_schema():
    schema = {}

    for collection_name in db.list_collection_names():
        collection = db[collection_name]
        document = collection.find_one()

        if document:
            fields = {}

            for field, value in document.items():
                fields[field] = type(value).__name__

            schema[collection_name] = fields

    return schema


if __name__ == "__main__":
    print(get_schema())