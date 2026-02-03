import uuid
import logging
import httpx

from typing import List
import app.services.extract as extract
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import BackgroundTasks, UploadFile, File, Form, Depends, HTTPException
from fastapi import Form, FastAPI, UploadFile, File, HTTPException, Depends, Security
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
import app.services.extract as extract
from contextlib import asynccontextmanager
from app.db.models import User
from app.config import settings
from app.db.models import ResumeAnalysis
from app.db.schemas import FolderData, AnalysisResponse
from app.db.connect import init_db, get_db
from app.services.ml_process import ml_analysis_s3,ml_analysis_drive,ml_health_check
from app.lib.aws_client import s3_client
from app.db.cruds import create_initial_record
from app.lib.aws_client import upload_to_s3
from app.lib.auth_client import (
    hash_password, 
    verify_password, 
    create_access_token, 
    decode_token
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan)
get_settings = settings()
security = HTTPBearer()
logger = logging.getLogger(__name__)


# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        get_settings.FRONTEND_URL,
        get_settings.NEXT_PUBLIC_FRONTEND_URL
        ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Schemas ---
class ConnectData(BaseModel):
    email: str
    password: str

# --- Auth Dependency ---
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security), 
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    
    user = db.query(User).filter(User.email == payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User account not found")
    return user

# --- Helper Logic: Persistence ---
def save_to_history(db: Session, user: User, new_results: List[dict]):
    """
    Standardized function to save results from any source into the User history.
    """
    if not new_results:
        return
    
    # Get current history (JSON list)
    current_history = list(user.analysis_history or [])
    
    # Combine lists (New results at the top)
    updated_history = (new_results + current_history)[:100]
    
    # Update the model
    user.analysis_history = updated_history
    
    # Update legacy list for backward compatibility
    new_filenames = [r["filename"] for r in new_results]
    user.processed_filenames = (list(user.processed_filenames or []) + new_filenames)[-100:]
    
    # Tell SQLAlchemy the JSON column has changed
    flag_modified(user, "analysis_history")
    flag_modified(user, "processed_filenames")
    
    db.commit()
    db.refresh(user)

@app.get("/")
async def read_root():
    return {"status": "BiasBreaker Backend is running..."}

@app.get("/health")
async def health_check():
    return {"service":"Backend","status": "healthy", "active":True}

@app.get("/ml-server/health")
async def health_check():
    is_awake = await ml_health_check()
    return {"service":"ML Server", "status": "healthy" if is_awake else "unhealthy", "active":is_awake}

# --- Authentication Routes ---
@app.post("/connect")
async def connect(data: ConnectData, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if user:
        if verify_password(data.password, user.hashed_password):
            token = create_access_token(data={"sub": user.email})
            return {
                "success": True, 
                "token": token,
                "email": user.email,
                "id": str(user.id)
            }
        raise HTTPException(status_code=401, detail="Incorrect password")
    
    # Create new user if not exists
    new_user = User(
        email=data.email, 
        hashed_password=hash_password(data.password),
        linked_folder_ids=[],
        processed_filenames=[]
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    token = create_access_token(data={"sub": new_user.email})
    return {
        "success": True,
        "token": token,
        "email": new_user.email,
        "id": str(new_user.id)
    }

@app.get("/auth/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "email": current_user.email,
        "id": str(current_user.id),
        "updated_at": str(current_user.updated_at),
        "authenticated": True,
        "credits": current_user.credits
        }



# --- Service Routes ---
@app.post("/get-description")
async def get_description(file: UploadFile = File(...)):
    content = await file.read()
    return {"description": extract.text(content, file.content_type)}

@app.delete("/reset-history")
async def reset_history(
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    analyses = db.query(ResumeAnalysis).filter(ResumeAnalysis.user_id == current_user.id).all()
    
    for item in analyses:
        try:
            s3_client.delete_object(Bucket=get_settings.AWS_BUCKET_NAME, Key=item.s3_key)
        except:
            pass
        db.delete(item)
    
    db.commit()
    return {"status": "success"}

@app.get("/history", response_model=List[AnalysisResponse])
async def get_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    history = db.query(ResumeAnalysis).filter(
        ResumeAnalysis.user_id == current_user.id
    ).order_by(ResumeAnalysis.created_at.desc()).all()
    
    return history
@app.post("/get-folder")
async def get_folder(
    request_data: FolderData, 
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    background_tasks.add_task(ml_health_check)
    if current_user.credits == 0:
        return {"message": "You have 0 Credits left"}
    async with httpx.AsyncClient() as client:
        drive_url = (
            f"https://www.googleapis.com/drive/v3/files?"
            f"q='{request_data.folderId}'+in+parents+and+trashed=false"
            f"&fields=files(id, name, mimeType)"
        )
        headers = {"Authorization": f"Bearer {request_data.googleToken}"}
        response = await client.get(drive_url, headers=headers)
        
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Drive access failed")
            
        files = response.json().get("files", [])
        file_list = [f for f in files if f['mimeType'] != 'application/vnd.google-apps.folder']

    if not file_list:
        return {"message": "No files found."}
    
    background_tasks.add_task(
        ml_analysis_drive,
        str(current_user.id),
        file_list,
        request_data.googleToken,
        request_data.description
    )

    return {"message": f"Queued {len(file_list)} files for background processing.","files":file_list}

@app.post("/upload")
async def upload_files(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    description: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    background_tasks.add_task(ml_health_check)
    if current_user.credits == 0:
        return {"message": "You have 0 Credits left"}
    for file in files:
        file_id = uuid.uuid4()
        s3_url, s3_key = await upload_to_s3(file, file.filename)
        create_initial_record(db, current_user.id, file.filename, s3_key, file_id)
        background_tasks.add_task(ml_analysis_s3, str(file_id), s3_url, file.filename, description)
    
    return {"message": "Processing started"}