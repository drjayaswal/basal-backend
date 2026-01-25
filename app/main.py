import re
import httpx
from typing import List, Optional
from fastapi import Form, FastAPI, UploadFile, File, HTTPException, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
from sqlalchemy.orm.attributes import flag_modified

# Internal Imports
from app.config import settings
from app.services.extract import extract_text
from app.db.model import User
from app.db.connect import init_db, get_db
from app.services.auth import (
    hash_password, 
    verify_password, 
    create_access_token, 
    decode_token
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting backend: Creating database tables...")
    init_db()
    yield
    print("Shutting down backend...")

app = FastAPI(lifespan=lifespan)
get_settings = settings()
security = HTTPBearer()

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Schemas ---
class ConnectData(BaseModel):
    email: str
    password: str

class FolderData(BaseModel):
    folderId: str
    description: str
    userId: str
    googleToken: str
    email: Optional[str] = None

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
    return {"email": current_user.email, "id": str(current_user.id), "authenticated": True}



# --- Core Logic Routes ---
@app.get("/history")
async def get_history(current_user: User = Depends(get_current_user)):
    """
    Returns the persistent analysis history for the logged-in user.
    """
    return current_user.analysis_history or []

@app.post("/get-folder")
async def get_folder(
    request_data: FolderData, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    results = []
    # Set a high timeout (60s) for Drive downloads and ML processing
    async with httpx.AsyncClient(timeout=60.0) as client:
        # 1. Fetch files list from Google Drive
        drive_url = f"https://www.googleapis.com/drive/v3/files?q='{request_data.folderId}'+in+parents+and+trashed=false"
        drive_resp = await client.get(
            drive_url, 
            headers={"Authorization": f"Bearer {request_data.googleToken}"}
        )
        
        if drive_resp.status_code != 200:
            raise HTTPException(status_code=drive_resp.status_code, detail="Failed to fetch Drive folder")
            
        files = drive_resp.json().get("files", [])

        for f in files:
            # 2. Download file content
            download_url = f"https://www.googleapis.com/drive/v3/files/{f['id']}?alt=media"
            file_content = await client.get(
                download_url, 
                headers={"Authorization": f"Bearer {request_data.googleToken}"}
            )
            
            if file_content.status_code == 200:
                # 3. Extract text and clean
                raw_text = extract_text(file_content.content, f.get("mimeType", "text/plain"))
                words = re.findall(r'\b\w+\b', raw_text.lower())
                
                # 4. Forward to ML Analysis Server
                ml_resp = await client.post(
                    f"{get_settings.ML_SERVER_URL}/analyze", 
                    json={
                        "filename": f["name"], 
                        "words": words, 
                        "description": request_data.description
                    }
                )
                
                if ml_resp.status_code == 200:
                    results.append({"filename": f["name"], "ml_analysis": ml_resp.json()})

    # Save everything found in this interaction to permanent DB
    save_to_history(db, current_user, results)
    return results

@app.post("/get-description")
async def get_description(file: UploadFile = File(...)):

    content = await file.read()

    text = extract_text(content, file.content_type)
    
    return {"description": text}

@app.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(...), 
    description: str = Form(""), 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    results = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        for file in files:
            content = await file.read()
            # 1. Extract text
            raw_text = extract_text(content, file.content_type)
            words = re.findall(r'\b\w+\b', raw_text.lower())
            
            # 2. Forward to ML Analysis Server
            ml_resp = await client.post(
                f"{get_settings.ML_SERVER_URL}/analyze", 
                json={
                    "filename": file.filename, 
                    "words": words, 
                    "description": description
                }
            )
            
            if ml_resp.status_code == 200:
                results.append({"filename": file.filename, "ml_analysis": ml_resp.json()})

    # Save these uploads to permanent DB
    save_to_history(db, current_user, results)
    return results