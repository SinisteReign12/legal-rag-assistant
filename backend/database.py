import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId
import bcrypt

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")

if not MONGODB_URI:
    raise ValueError("MONGODB_URI is not set in .env")

client = MongoClient(MONGODB_URI)

db = client["legal_rag"]

conversations_collection = db["conversations"]
messages_collection = db["messages"]
users_collection = db["users"]


def create_user(email, password):

    existing_user = users_collection.find_one({
        "email": email
    })

    if existing_user:
        return None

    password_hash = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    )

    user = {
        "email": email,
        "password": password_hash.decode("utf-8"),
        "createdAt": datetime.now(timezone.utc),
    }

    result = users_collection.insert_one(user)

    return str(result.inserted_id)


def get_user_by_email(email):

    return users_collection.find_one({
        "email": email
    })
    

def verify_password(password, password_hash):

    return bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8")
    )


def create_conversation(user_id, title="New Legal Conversation"):

    conversation = {
        "userId": user_id,
        "title": title,
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc),
    }

    result = conversations_collection.insert_one(
        conversation
    )

    return str(result.inserted_id)


def update_conversation_title(conversation_id, user_id, title):

    result = conversations_collection.update_one(
        {
            "_id": ObjectId(conversation_id),
            "userId": user_id
        },
        {
            "$set": {
                "title": title,
                "updatedAt": datetime.now(timezone.utc)
            }
        }
    )

    return result.modified_count > 0


def save_message(conversation_id, role, content):

    message = {
        "conversationId": conversation_id,
        "role": role,
        "content": content,
        "createdAt": datetime.now(timezone.utc),
    }

    messages_collection.insert_one(message)

    conversations_collection.update_one(
        {"_id": ObjectId(conversation_id)},
        {
            "$set": {
                "updatedAt": datetime.now(timezone.utc)
            }
        }
    )


def get_conversations(user_id):

    conversations = conversations_collection.find(
        {
            "userId": user_id
        }
    ).sort(
        "updatedAt",
        -1
    )

    result = []

    for conversation in conversations:

        result.append({
            "id": str(conversation["_id"]),
            "title": conversation["title"],
            "createdAt": conversation["createdAt"],
            "updatedAt": conversation["updatedAt"],
        })

    return result


def get_messages(conversation_id, user_id):

    conversation = conversations_collection.find_one({
        "_id": ObjectId(conversation_id),
        "userId": user_id
    })

    if not conversation:
        return None

    messages = messages_collection.find(
        {
            "conversationId": conversation_id
        }
    ).sort(
        "createdAt",
        1
    )

    result = []

    for message in messages:

        result.append({
            "role": message["role"],
            "content": message["content"],
            "createdAt": message["createdAt"],
        })

    return result


def conversation_belongs_to_user(conversation_id, user_id):

    conversation = conversations_collection.find_one({
        "_id": ObjectId(conversation_id),
        "userId": user_id
    })

    return conversation is not None


def save_document(conversation_id, filename, filepath):

    document = {
        "conversationId": conversation_id,
        "filename": filename,
        "filepath": filepath,
        "createdAt": datetime.now(timezone.utc),
    }

    db["documents"].delete_many({
        "conversationId": conversation_id
    })

    result = db["documents"].insert_one(
        document
    )

    return str(result.inserted_id)


def get_document(conversation_id):
    document = db["documents"].find_one(
        {
            "conversationId": conversation_id
        }
    )

    if not document:
        return None

    return {
        "id": str(document["_id"]),
        "conversationId": document["conversationId"],
        "filename": document["filename"],
        "filepath": document["filepath"],
        "createdAt": document["createdAt"],
    }


def delete_document(conversation_id):
    db["documents"].delete_many(
        {
            "conversationId": conversation_id
        }
    )


def delete_conversation(conversation_id, user_id):

    conversation = conversations_collection.find_one({
        "_id": ObjectId(conversation_id),
        "userId": user_id
    })

    if not conversation:
        return False

    conversations_collection.delete_one({
        "_id": ObjectId(conversation_id),
        "userId": user_id
    })

    messages_collection.delete_many({
        "conversationId": conversation_id
    })

    db["documents"].delete_many({
        "conversationId": conversation_id
    })

    return True