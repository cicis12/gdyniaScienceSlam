import os
from uuid import uuid4
from fastapi import UploadFile, HTTPException

UPLOAD_DIR = "uploads/filmikuczestnik"
MAX_FILE_SIZE = 50*1024*1024 #50MB
ALLOWED_MIME_TYPES = {"video/mp4", "video/webm", "video/quicktime", "video/x-matroska"}
ALLOWED_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv"}

async def save_video(video: UploadFile) -> str:
    if video.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Błędny format filmu, dopuszczamy .mp4 .webm .mov i .mkv")

    _, ext = os.path.splitext(video.filename)
    ext = ext.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail= "Błędny format filmu, dopuszczamy .mp4 .webm .mov i .mkv")

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    filename = f"{uuid4()}{ext}"
    file_path = os.path.join(UPLOAD_DIR,filename)

    size = 0

    try:
        with open(file_path, "wb") as buffer:
            while chunk := await video.read(1024*1024):
                size += len(chunk)

                if size > MAX_FILE_SIZE:
                    buffer.close()
                    os.remove(file_path)
                    raise HTTPException(status_code=400, detail="Przesłany plik jest zbyt duży (max 50MB)")

                buffer.write(chunk)
    except Exception:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise
    return filename


    