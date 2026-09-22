from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")

db = client["queryable_chatbot"]

print("connected to mongodb")
print("collections:", db.list_collection_names())