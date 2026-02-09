import uuid
import httpx
import logging
import asyncio
import app.services.extract as extract

from typing import List
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm.attributes import flag_modified
from fastapi_mail import FastMail, MessageSchema, MessageType
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Form, FastAPI, UploadFile, File, HTTPException, Depends, Security, BackgroundTasks

import app.services.extract as extract

from app.config import settings
from app.db.models import User, Source
from app.lib.aws_client import s3_client
from contextlib import asynccontextmanager
from app.db.connect import init_db, get_db
from app.lib.aws_client import upload_to_s3
from app.lib.mail_client import conf, create_html_body
from app.db.cruds import create_file_record, get_or_create_source
from app.lib.auth_client import hash_password, verify_password, create_access_token, decode_token
from app.db.models import ResumeAnalysis, AnalysisStatus, SourceChunk, ChatMessage, Conversation,Feedback
from app.services.ml_process import ml_analysis_s3,ml_analysis_drive,ml_health_check,ml_analysis_video, ml_analysis_document
from app.db.schemas import FolderDataSchema, AnalysisResponseSchema,StatusUpdateSchema, VideoIngestRequestSchema, SyncRequestSchema, ConnectDataSchema, SourceSchema, ChatRequestSchema, FeedbackSchema

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

security = HTTPBearer()
get_settings = settings()
app = FastAPI(lifespan=lifespan)
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

# --- Startup Route ---
@app.on_event("startup")
async def startup_event():
    # Fire and forget: send a ping to ML server when Backend starts
    # This begins the ML wake-up process immediately
    asyncio.create_task(ml_health_check(max_retries=1, delay=0))

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
def save_to_history(background_tasks: BackgroundTasks,db: Session, user: User, new_results: List[dict]):
    background_tasks.add_task(ml_health_check)
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

# --- Root Routes ---
@app.get("/")
async def read_root():
    return {"status": "Basal Backend is running..."}
@app.get("/health")
async def health_check():
    return {"service":"Backend","status": "healthy", "active":True}
@app.get("/ml-server/health")
async def health_check():
    is_awake = await ml_health_check()
    return {"service":"ML Server", "status": "healthy" if is_awake else "unhealthy", "active":is_awake}

# --- Authentication Routes ---
@app.post("/connect")
async def connect(background_tasks: BackgroundTasks,data: ConnectDataSchema, db: Session = Depends(get_db)):
    background_tasks.add_task(ml_health_check)
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
async def get_me(background_tasks: BackgroundTasks,current_user: User = Depends(get_current_user)):
    background_tasks.add_task(ml_health_check)
    return {
        "email": current_user.email,
        "id": str(current_user.id),
        "updated_at": str(current_user.updated_at),
        "authenticated": True,
        "credits": current_user.credits,
        "total_conversations": len(current_user.conversations)
        }

# --- Updation Routes ---
@app.patch("/update-source-status")
async def update_source_status(data: StatusUpdateSchema, db: Session = Depends(get_db)):
    src = db.query(Source).filter(Source.id == data.source_id).first()
    if src:
        src.status = AnalysisStatus(data.status)
        db.commit()
        return {"message": "updated"}
    return {"error": "source not found"}, 404
@app.post("/update-source-chunks")
async def update_source_chunks(data: SyncRequestSchema, db: Session = Depends(get_db)):
    try:
        source_uuid = uuid.UUID(str(data.source_id))
        
        existing_source = db.query(Source).filter(Source.id == source_uuid).first()
        if not existing_source:
            raise HTTPException(status_code=404, detail="Source record not found")

        db.query(SourceChunk).filter(SourceChunk.source_id == source_uuid).delete()

        new_chunks = []
        for item in data.chunks:
            chunk_obj = SourceChunk(
                source_id=source_uuid,
                content=item.content,
                embedding=item.embedding,
                status=AnalysisStatus.COMPLETED 
            )
            new_chunks.append(chunk_obj)
        
        db.add_all(new_chunks)

        existing_source.status = AnalysisStatus.COMPLETED
        
        db.commit()
        return {
            "status": "success",
            "count": len(new_chunks),
            "source_id": str(source_uuid)
        }

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database Sync Failed")
@app.get("/get-sources", response_model=List[SourceSchema])
async def get_user_sources(
    db: Session = Depends(get_db),
):
    try:
        sources = db.query(Source).order_by(Source.created_at.desc()).all()
        return sources
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not fetch sources from database")

# --- Ingestion Routes ---
@app.post("/ingest-video")
async def ingest_video(
    request: VideoIngestRequestSchema, 
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.credits <= 0:
        return {"message": "You have 0 Credits left"}
    
    user_prefix = current_user.email.split("@")[0]
    filename = request.url.split("/")[-1] 
    unique_key = f"{user_prefix}_{filename}"

    source_id, exists = get_or_create_source(
        db, 
        unique_key=unique_key,
        source_type="video", 
        source_name=request.url, 
        user_id=current_user.id
    )
    
    if exists:
        return {"source_id": source_id, "status": "ready", "message": "Already exists"}

    current_user.credits -= 1
    db.add(current_user)
    db.commit()

    background_tasks.add_task(ml_analysis_video, request.url, str(source_id))

    return {
        "source_id": source_id, 
        "status": "processing", 
        "message": "You can start chatting in a minute..!"
    }
@app.post("/ingest-document")
async def ingest_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.credits <= 0:
        return {"message": "You have 0 Credits left"}

    user_prefix = current_user.email.split("@")[0]
    unique_key = f"{user_prefix}_{file.filename}"

    source_id, exists = get_or_create_source(
        db, 
        unique_key=unique_key,
        source_type="document", 
        source_name=file.filename, 
        user_id=current_user.id
    )
    
    if exists:
        return {"source_id": source_id, "status": "ready", "message": "Already exists"}

    current_user.credits -= 1
    db.add(current_user)
    db.commit()
    file_bytes = await file.read()

    background_tasks.add_task(ml_analysis_document, file_bytes, file.filename, str(source_id))

    return {
        "source_id": source_id, 
        "status": "processing", 
        "message": "You can start chatting in a minute..!"
    }

# --- History Routes ---
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
@app.get("/history", response_model=List[AnalysisResponseSchema])
async def get_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    history = db.query(ResumeAnalysis).filter(
        ResumeAnalysis.user_id == current_user.id
    ).order_by(ResumeAnalysis.created_at.desc()).all()
    
    return history

# --- Chat & Conversation Routes ---
@app.post("/chat")
async def chat(
    data: ChatRequestSchema, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    settings = get_settings 
    
    try:
        conversation = None
        
        if data.conversation_id:
            try:
                conv_id = uuid.UUID(str(data.conversation_id))
                conversation = db.query(Conversation).filter(
                    Conversation.id == conv_id,
                    Conversation.user_id == current_user.id
                ).first()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid conversation ID format")

        if not conversation:
            title = (data.question[:27] + "...") if len(data.question) > 30 else data.question
            conversation = Conversation(title=title, user_id=current_user.id)
            db.add(conversation)
            db.flush() 
        
        db.add(ChatMessage(conversation_id=conversation.id, role="user", content=data.question))

        source_exists = db.query(SourceChunk).filter(SourceChunk.source_id == data.source_id).first()
        if not source_exists:
            print(f"DEBUG: No chunks found for source_id: {data.source_id}")
            raise HTTPException(status_code=404, detail="Source ID not found or has no content.")

        async with httpx.AsyncClient() as client:
            v_resp = await client.post(
                f"{settings.ML_SERVER_URL}/get-vector", 
                json={"text": data.question},
                timeout=20.0 
            )
            v_resp.raise_for_status()
            query_vector = v_resp.json()["vector"]

            chunks = db.query(SourceChunk).filter(
                SourceChunk.source_id == data.source_id
            ).order_by(
                SourceChunk.embedding.cosine_distance(query_vector)
            ).limit(5).all()

            context_text = "\n\n".join([c.content for c in chunks])
            print(f"DEBUG: Found {len(chunks)} chunks for context.")

            try:
                ai_resp = await client.post(
                    f"{settings.ML_SERVER_URL}/generate-answer", 
                    json={
                        "question": data.question,
                        "context": context_text
                    },
                    timeout=90.0
                )
                ai_resp.raise_for_status()
                answer_text = ai_resp.json()["answer"]
            except httpx.HTTPStatusError as e:
                print(f"ML Generation Error: {e.response.text}")
                raise HTTPException(status_code=502, detail="ML Model failed to generate answer")

        db.add(ChatMessage(conversation_id=conversation.id, role="assistant", content=answer_text))
        
        db.commit() 

        return {
            "answer": answer_text,
            "conversation_id": str(conversation.id),
            "context_used": len(chunks) > 0 
        }
            
    except httpx.HTTPStatusError as e:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"ML Service Error: {e.response.text}")
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print(f"Chat Route Error: {type(e).__name__} - {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
@app.get("/conversations")
async def get_conversations(db: Session = Depends(get_db)):
    return db.query(Conversation).order_by(Conversation.created_at.desc()).all()
@app.get("/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str, db: Session = Depends(get_db)):
    return db.query(ChatMessage).filter(
        ChatMessage.conversation_id == conversation_id
    ).order_by(ChatMessage.created_at.asc()).all()

# --- Service Routes ---
@app.post("/get-folder")
async def get_folder(
    request_data: FolderDataSchema, 
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
        create_file_record(db, current_user.id, file.filename, s3_key, file_id)
        background_tasks.add_task(ml_analysis_s3, str(file_id), s3_url, file.filename, description)
    
    return {"message": "Processing started"}

# --- Misc Routes ---
@app.post("/get-description")
async def get_description(file: UploadFile = File(...)):
    content = await file.read()
    return {"description": extract.text(content, file.content_type)}
@app.post("/feedback")
async def create_feedback(
    data: FeedbackSchema, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    try:
        new_feedback = Feedback(
            email=data.email,
            category=data.category.value,
            content=data.content,
        )
        db.add(new_feedback)
        db.commit()
        db.refresh(new_feedback)

        html_content = create_html_body(data.category.value, data.content)

        message = MessageSchema(
            subject="Feedback Received • Bridge the Gap",
            recipients=[data.email],
            body=html_content,
            subtype=MessageType.html
        )
        fm = FastMail(conf)

        background_tasks.add_task(fm.send_message, message)

        return {"status": "success", "id": str(new_feedback.id)}
        
    except Exception as e:
        db.rollback()
        print(f"DEBUG: {e}")
        raise HTTPException(status_code=400, detail="Transmission error.")
