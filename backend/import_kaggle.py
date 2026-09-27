import csv
import os

from pymongo import MongoClient


client = MongoClient("mongodb://localhost:27017")
db = client["queryable_chatbot"]

data_folder = "data/kaggle_ecommerce"


def convert_value(value):
    value = value.strip()

    if value == "":
        return None

    try:
        return int(value)
    except ValueError:
        pass

    try:
        return float(value)
    except ValueError:
        pass

    return value


for filename in os.listdir(data_folder):

    if not filename.endswith(".csv"):
        continue

    file_path = os.path.join(data_folder, filename)

    collection_name = filename.replace(".csv", "")

    print()
    print("importing:", filename)

    collection = db[collection_name]

    collection.delete_many({})

    documents = []

    with open(file_path, "r", encoding="utf-8-sig", newline="") as file:

        reader = csv.DictReader(file)

        for row in reader:

            document = {}

            for field, value in row.items():
                document[field] = convert_value(value)

            documents.append(document)

    if documents:
        collection.insert_many(documents)

    print("collection:", collection_name)
    print("documents inserted:", len(documents))


print()
print("kaggle data import completed")
print("collections:", db.list_collection_names())