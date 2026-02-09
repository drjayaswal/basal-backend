from uuid import UUID
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, ConfigDict
from app.db.models import Category

class UserBaseSchema(BaseModel):
    email: EmailStr

class FolderDataSchema(BaseModel):
    folderId: str
    googleToken: str
    description: str

class UserCreateSchema(UserBaseSchema):
    password: str

class FolderLinkRequestSchema(BaseModel):
    userId: UUID
    folderId: str
    email: Optional[EmailStr] = None

class AnalysisResponseSchema(BaseModel):
    id: UUID
    status: str
    filename: str
    created_at: datetime
    details: Optional[dict] = None
    candidate_info: Optional[dict] = None
    match_score: Optional[float] = None
    model_config = ConfigDict(from_attributes=True)

class UserResponseSchema(UserBaseSchema):
    id: UUID
    updated_at: datetime
    linked_folder_ids: List[str] = []
    processed_filenames: List[str] = []
    analyses: List[AnalysisResponseSchema] = [] 
    model_config = ConfigDict(from_attributes=True)

class LatestFolderResponseSchema(BaseModel):
    latest_folder_id: Optional[str] = None

class VideoIngestRequestSchema(BaseModel):
    url: str
    user_id: str

class StatusUpdateSchema(BaseModel):
    source_id: str
    status: str

class ChatRequestSchema(BaseModel):
    question: str
    source_id: str
    conversation_id: Optional[str] = None

class ChunkDataSchema(BaseModel):
    content: str
    embedding: List[float]

class SyncRequestSchema(BaseModel):
    source_id: str
    chunks: List[ChunkDataSchema]

class ConnectDataSchema(BaseModel):
    email: str
    password: str

class SourceSchema(BaseModel):
    id: UUID
    source_name: str
    source_type: str
    status: str
    created_at: datetime

class FeedbackSchema(BaseModel):
    email: EmailStr
    category: Category
    content: str