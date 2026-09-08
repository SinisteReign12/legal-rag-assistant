import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "legal-pdfs")

if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL is not set.")

if not SUPABASE_SECRET_KEY:
    raise ValueError("SUPABASE_SECRET_KEY is not set.")

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


def upload_pdf(file_path: str, storage_path: str):
    with open(file_path, "rb") as file:
        return supabase.storage.from_(SUPABASE_BUCKET).upload(
            file=file,
            path=storage_path,
            file_options={
                "content-type": "application/pdf",
                "upsert": "true"
            }
        )


def download_pdf(storage_path: str, destination_path: str):
    """
    Download a PDF from Supabase Storage to a local temporary file.
    """

    data = supabase.storage.from_(SUPABASE_BUCKET).download(
        storage_path
    )

    with open(destination_path, "wb") as file:
        file.write(data)


def delete_pdf(storage_path: str):
    """
    Delete a PDF from Supabase Storage.
    """

    supabase.storage.from_(SUPABASE_BUCKET).remove(
        [storage_path]
    )