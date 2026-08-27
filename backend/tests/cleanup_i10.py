"""Cleanup of test artifacts created during iteration 10 testing."""
import os
from dotenv import dotenv_values
from pymongo import MongoClient

env = dotenv_values("/app/backend/.env")
db = MongoClient(env["MONGO_URL"])[env["DB_NAME"]]

r1 = db.uploads.delete_many({"filename": {"$regex": "^TEST_"}})
r2 = db.chats.delete_many({"user_id": "TEST_poor_user_001"})
r3 = db.chats.delete_many({"chat_id": "chat_80bef597fb"})
r4 = db.messages.delete_many({"chat_id": "chat_80bef597fb"})
db.users.delete_one({"user_id": "TEST_poor_user_001"})
db.user_sessions.delete_one({"session_token": "TEST_poor_session_token"})
db.users.update_one({"user_id": "user_grelligram_seed"}, {"$set": {"wallet_balance": 500.0}})
db.users.update_one({"user_id": "test-user-seed-001"}, {"$set": {"wallet_balance": 150.0}})
print("uploads", r1.deleted_count, "poor chats", r2.deleted_count,
      "stray chat", r3.deleted_count, "msgs", r4.deleted_count)
print("orphan autofill usage_events:", db.usage_events.count_documents({"mode": "autofill"}))
print("admin balance:", db.users.find_one({"user_id": "user_grelligram_seed"})["wallet_balance"])
