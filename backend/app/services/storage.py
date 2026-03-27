import os
import shutil
from fastapi import UploadFile, HTTPException
import uuid

# Configuration
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
# Define buckets or sub-directories
BUCKETS = {
    "grounds": os.path.join(UPLOAD_DIR, "images", "grounds"),
    "profiles": os.path.join(UPLOAD_DIR, "images", "profiles"),
}

# Ensure directories exist
for bucket_path in BUCKETS.values():
    os.makedirs(bucket_path, exist_ok=True)

class StorageService:
    @staticmethod
    async def save_upload_file(upload_file: UploadFile, bucket: str = "grounds") -> str:
        """
        Saves an uploaded file locally.
        In production with S3, this would be replaced with boto3 code.
        """
        if bucket not in BUCKETS:
            raise HTTPException(status_code=400, detail="Invalid storage bucket")

        # Validate file format
        ext = os.path.splitext(upload_file.filename)[1].lower() if upload_file.filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid file type. Allowed formats: {', '.join(ALLOWED_EXTENSIONS)}"
            )

        # Generate unique filename
        filename = f"{uuid.uuid4().hex}{ext}"
        destination_path = os.path.join(BUCKETS[bucket], filename)

        try:
            with open(destination_path, "wb") as buffer:
                shutil.copyfileobj(upload_file.file, buffer)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
        finally:
            upload_file.file.close()

        # Return the public URL path
        return f"/uploads/images/{bucket}/{filename}"
