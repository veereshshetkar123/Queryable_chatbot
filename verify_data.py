import os
import glob
import pandas as pd
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
db = client["queryable_chatbot"]

print()
print("DATA LOAD VERIFICATION")
print("======================")

files = glob.glob("data/kaggle_ecommerce/*.csv")

for file in files:
    collection_name = os.path.splitext(os.path.basename(file))[0]

    csv_count = len(pd.read_csv(file))
    mongo_count = db[collection_name].count_documents({})

    if csv_count == mongo_count:
        status = "MATCH"
    else:
        status = "MISMATCH"

    print(
        collection_name,
        "-> CSV:", csv_count,
        "| MongoDB:", mongo_count,
        "|", status
    )