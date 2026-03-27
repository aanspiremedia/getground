from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from typing import Optional
from app.services.storage import StorageService
import logging

router = APIRouter(prefix="/upload", tags=["Uploads"])

@router.post("")
async def upload_image(file: UploadFile = File(...), bucket: str = Form("grounds")):
    """
    General internal upload endpoint.
    Bucket defines the storage subfolder (e.g. 'grounds', 'profiles')
    """
    try:
        url = await StorageService.save_upload_file(file, bucket)
        return {"url": url}
    except Exception as e:
        logging.error(f"Image upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Upload failed")
