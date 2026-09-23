from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
db = client["queryable_chatbot"]


def get_schema():

    schema = {}

    for collection_name in db.list_collection_names():

        collection = db[collection_name]

        documents = list(collection.find().limit(5))

        if not documents:
            continue

        fields = {}

        for document in documents:

            for field, value in document.items():

                if field not in fields:

                    fields[field] = {
                        "type": type(value).__name__,
                        "sample_values": []
                    }

                if len(fields[field]["sample_values"]) < 3:

                    if value not in fields[field]["sample_values"]:
                        fields[field]["sample_values"].append(value)

        schema[collection_name] = fields

    return schema


if __name__ == "__main__":

    result = get_schema()

    for collection, fields in result.items():

        print()
        print("collection:", collection)

        for field, details in fields.items():

            print(
                field,
                "->",
                details["type"],
                "| samples:",
                details["sample_values"]
            )