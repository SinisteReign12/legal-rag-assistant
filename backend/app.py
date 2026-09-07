import os

from pathlib import Path
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt
from rag_engine import (
    query_uploaded_pdf,
    process_uploaded_pdf,
    rag_sessions,
    remove_pdf_session,
)
from database import (
    create_conversation,
    save_message,
    get_conversations,
    get_messages,
    delete_conversation,
    save_document,
    get_document,
    delete_document,
    create_user,
    get_user_by_email,
    verify_password,
    conversation_belongs_to_user,
    update_conversation_title,
)
from dotenv import load_dotenv
from storage import upload_pdf as storage_upload_pdf
from storage import delete_pdf as storage_delete_pdf

load_dotenv()

MAX_PDF_SIZE = 25 * 1024 * 1024
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"

UPLOAD_DIR.mkdir(exist_ok=True)

class AskRequest(BaseModel):
    conversation_id: str
    query: str

app = FastAPI()

JWT_SECRET = os.getenv("JWT_SECRET")

if not JWT_SECRET:
    raise ValueError("JWT_SECRET is not set in .env")


security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"]
        )

        return payload

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token."
        )

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConversationRequest(BaseModel):
    title: str = "New Legal Conversation"
    
class UpdateConversationRequest(BaseModel):
    title: str
    
class RegisterRequest(BaseModel):
    email: str
    password: str
    
class LoginRequest(BaseModel):
    email: str
    password: str
    
@app.post("/register")
def register(request: RegisterRequest):

    email = request.email.strip().lower()
    password = request.password

    if not email:
        raise HTTPException(
            status_code=400,
            detail="Email is required."
        )

    if len(password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 6 characters."
        )

    user_id = create_user(
        email,
        password
    )

    if user_id is None:
        raise HTTPException(
            status_code=400,
            detail="A user with this email already exists."
        )

    return {
        "message": "User registered successfully.",
        "user_id": user_id,
        "email": email
    }    
    

@app.post("/login")
def login(request: LoginRequest):

    email = request.email.strip().lower()
    password = request.password

    user = get_user_by_email(email)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password."
        )

    if not verify_password(
        password,
        user["password"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password."
        )

    token_data = {
        "user_id": str(user["_id"]),
        "email": user["email"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=24)
    }

    token = jwt.encode(
        token_data,
        os.getenv("JWT_SECRET"),
        algorithm="HS256"
    )

    return {
        "message": "Login successful.",
        "token": token,
        "user_id": str(user["_id"]),
        "email": user["email"]
    }

@app.post("/conversations")
def new_conversation(
    request: ConversationRequest,
    current_user: dict = Depends(get_current_user)
):

    conversation_id = create_conversation(
        current_user["user_id"],
        request.title
    )

    return {
        "id": conversation_id,
        "title": request.title,
    }
    

@app.patch("/conversations/{conversation_id}")
def update_conversation(
    conversation_id: str,
    request: UpdateConversationRequest,
    current_user: dict = Depends(get_current_user)
):

    title = request.title.strip()

    if not title:
        raise HTTPException(
            status_code=400,
            detail="Conversation title cannot be empty."
        )

    if len(title) > 100:
        raise HTTPException(
            status_code=400,
            detail="Conversation title cannot exceed 100 characters."
        )

    if not conversation_belongs_to_user(
        conversation_id,
        current_user["user_id"]
    ):
        raise HTTPException(
            status_code=404,
            detail="Conversation not found."
        )

    updated = update_conversation_title(
        conversation_id,
        current_user["user_id"],
        title
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found."
        )

    return {
        "message": "Conversation renamed successfully.",
        "id": conversation_id,
        "title": title
    }


@app.get("/conversations")
def conversations(
    current_user: dict = Depends(get_current_user)
):

    return {
        "conversations": get_conversations(
            current_user["user_id"]
        )
    }


@app.get("/conversations/{conversation_id}/messages")
def conversation_messages(
    conversation_id: str,
    current_user: dict = Depends(get_current_user)
):

    messages = get_messages(
        conversation_id,
        current_user["user_id"]
    )

    if messages is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found."
        )

    return {
        "messages": messages
    }
  
    
@app.delete("/conversations/{conversation_id}")
def delete_conversation_endpoint(
    conversation_id: str,
    current_user: dict = Depends(get_current_user)
):

    try:

        if not conversation_belongs_to_user(
            conversation_id,
            current_user["user_id"]
        ):
            raise HTTPException(
                status_code=404,
                detail="Conversation not found."
            )

        document = get_document(
            conversation_id
        )


        deleted = delete_conversation(
            conversation_id,
            current_user["user_id"]
        )

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found."
            )

        remove_pdf_session(conversation_id)

        if document:

            storage_path = document.get("filepath")

            if storage_path:

                try:
                    storage_delete_pdf(storage_path)

                    print(
                        "Deleted PDF from Supabase:",
                        storage_path
                    )

                except Exception as e:
                    print(
                        "Supabase PDF deletion error:",
                        e
                    )

        return {
            "message": "Conversation deleted successfully."
        }

    except HTTPException:
        raise

    except Exception as e:

        print(
            "Delete conversation error:",
            e
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to delete conversation."
        )
        

@app.post("/conversations/{conversation_id}/upload")
def upload_pdf(
    conversation_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    file_path = None

    try:
        if not conversation_belongs_to_user(
            conversation_id,
            current_user["user_id"]
        ):
            raise HTTPException(
                status_code=404,
                detail="Conversation not found."
            )

        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="No file selected."
            )

        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail="Only PDF files are allowed."
            )

        old_document = get_document(conversation_id)

        safe_filename = Path(file.filename).name

        # Temporary local file used only for PDF processing
        file_path = UPLOAD_DIR / (
            f"{conversation_id}_{safe_filename}"
        )

        # Save locally while enforcing the 25 MB limit
        file_size = 0

        with open(file_path, "wb") as buffer:
            while True:
                chunk = file.file.read(1024 * 1024)

                if not chunk:
                    break

                file_size += len(chunk)

                if file_size > MAX_PDF_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="PDF file is too large. Maximum allowed size is 25 MB."
                    )

                buffer.write(chunk)

        print("PDF temporarily saved:", file_path)

        # Process PDF and build RAG index
        try:
            result = process_uploaded_pdf(
                conversation_id,
                str(file_path)
            )

        except ValueError as e:
            file_path.unlink(missing_ok=True)

            raise HTTPException(
                status_code=400,
                detail=str(e)
            )

        except Exception as e:
            print("PDF processing error:", e)

            file_path.unlink(missing_ok=True)

            raise HTTPException(
                status_code=500,
                detail="The PDF could not be processed. Please try another PDF."
            )

        # Upload PDF to Supabase Storage
        storage_path = (
            f"{current_user['user_id']}/{conversation_id}/{safe_filename}"
        )

        try:
            storage_upload_pdf(
                str(file_path),
                storage_path
            )

            print(
                "PDF uploaded to Supabase:",
                storage_path
            )

        except Exception as e:
            print("Supabase upload error:", e)

            file_path.unlink(missing_ok=True)

            raise HTTPException(
                status_code=500,
                detail="PDF could not be uploaded to storage."
            )

        # Save Supabase path in MongoDB
        try:
            save_document(
                conversation_id,
                safe_filename,
                storage_path
            )

        except Exception as e:
            print("Document database save error:", e)

            # Remove the cloud copy because MongoDB save failed
            try:
                storage_delete_pdf(storage_path)
            except Exception as delete_error:
                print(
                    "Supabase cleanup error:",
                    delete_error
                )

            file_path.unlink(missing_ok=True)

            raise HTTPException(
                status_code=500,
                detail="PDF was uploaded but could not be saved. Please try again."
            )

                # Delete the old PDF from Supabase after the new document
        # has been successfully saved to MongoDB.
        if old_document:
            old_storage_path = old_document.get("filepath")

            if old_storage_path and old_storage_path != storage_path:
                try:
                    storage_delete_pdf(old_storage_path)

                    print(
                        "Deleted old PDF from Supabase:",
                        old_storage_path
                    )

                except Exception as e:
                    print(
                        "Old Supabase PDF cleanup error:",
                        e
                    )

        # Remove temporary local PDF
        file_path.unlink(missing_ok=True)

        return {
            "message": "PDF processed successfully.",
            "filename": safe_filename,
            "chunks": result["chunks"]
        }

    except HTTPException:
        if file_path is not None and file_path.exists():
            file_path.unlink(missing_ok=True)

        raise

    except Exception as e:
        print("PDF upload error:", e)

        if file_path is not None and file_path.exists():
            file_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=500,
            detail="PDF upload failed."
        )
        

@app.get("/conversations/{conversation_id}/document")
def get_document_endpoint(
    conversation_id: str,
    current_user: dict = Depends(get_current_user)
):

    if not conversation_belongs_to_user(
        conversation_id,
        current_user["user_id"]
    ):
        raise HTTPException(
            status_code=404,
            detail="Conversation not found."
        )

    document = get_document(conversation_id)

    if not document:
        return {"document": None}

    return {
        "document": {
            "filename": document["filename"],
        }
    }


@app.delete("/conversations/{conversation_id}/document")
def remove_document(
    conversation_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        if not conversation_belongs_to_user(
            conversation_id,
            current_user["user_id"]
        ):
            raise HTTPException(
                status_code=404,
                detail="Conversation not found."
            )

        document = get_document(
            conversation_id
        )

        if not document:
            raise HTTPException(
                status_code=404,
                detail="No document found for this conversation."
            )

        storage_path = document.get("filepath")

        if storage_path:

            try:
                storage_delete_pdf(storage_path)

                print(
                    "Deleted PDF from Supabase:",
                    storage_path
                )

            except Exception as e:
                print(
                    "Supabase PDF deletion error:",
                    e
                )

        remove_pdf_session(conversation_id)

        delete_document(conversation_id)

        return {
            "message": "Document removed successfully."
        }

    except HTTPException:
        raise

    except Exception as e:

        print(
            "Remove document error:",
            e
        )

        raise HTTPException(
            status_code=500,
            detail="Failed to remove document."
        )


@app.post("/ask")
def ask(
    request: AskRequest,
    current_user: dict = Depends(get_current_user)
):

    if not conversation_belongs_to_user(
        request.conversation_id,
        current_user["user_id"]
    ):
        raise HTTPException(
            status_code=404,
            detail="Conversation not found."
        )

    result = query_uploaded_pdf(
        request.conversation_id,
        request.query
    )

    save_message(
        request.conversation_id,
        "user",
        request.query
    )

    save_message(
        request.conversation_id,
        "assistant",
        result
    )

    return {
        "response": result
    }