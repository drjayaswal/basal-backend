import uuid, enum
from .connect import Base
from sqlalchemy import Text
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Column, String, DateTime, func, ForeignKey, Float, Enum, Integer


class AnalysisStatus(enum.Enum):
    FAILED = "failed"
    PENDING = "pending"
    COMPLETED = "completed"
    PROCESSING = "processing"

class Category(enum.Enum):
    GENERAL = "GENERAL"
    BUG = "BUG"
    FEATURE = "FEATURE"
    UIUX = "UIUX"
    OTHER = "OTHER"    

class User(Base):
    __tablename__ = "users"
    credits = Column(Integer, default=1)
    hashed_password = Column(String, nullable=False)
    linked_folder_ids = Column(JSONB, nullable=True)
    processed_filenames = Column(JSONB, nullable=True)
    email = Column(String, unique=True, nullable=False)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
    sources = relationship("Source", back_populates="owner", cascade="all, delete-orphan")
    analyses = relationship("ResumeAnalysis", back_populates="owner", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")

class ResumeAnalysis(Base):
    __tablename__ = "resume_analyses"
    details = Column(JSONB, nullable=True)
    s3_key = Column(String, nullable=True)
    match_score = Column(Float, default=0.0)
    filename = Column(String, nullable=False)
    candidate_info = Column(JSONB, nullable=True)
    owner = relationship("User", back_populates="analyses")
    status = Column(Enum(AnalysisStatus), default=AnalysisStatus.PENDING)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

class Source(Base):
    __tablename__ = "sources"
    source_name = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    owner = relationship("User", back_populates="sources")
    unique_key = Column(String, unique=True, nullable=False)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(Enum(AnalysisStatus), default=AnalysisStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    chunks = relationship("SourceChunk", back_populates="source", cascade="all, delete-orphan")
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

class SourceChunk(Base):
    __tablename__ = "source_chunks"
    embedding = Column(Vector(768)) 
    content = Column(Text, nullable=False)
    status = Column(Enum(AnalysisStatus), default=AnalysisStatus.PENDING)
    source = relationship("Source", back_populates="chunks")
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)

class Conversation(Base):
    __tablename__ = "conversations"
    title = Column(String, nullable=True)
    user = relationship("User", back_populates="conversations")
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    messages = relationship("ChatMessage", back_populates="conversation", cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation = relationship("Conversation", back_populates="messages")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)

class Feedback(Base):
    __tablename__ = "feedbacks"
    content = Column(Text, nullable=False)
    email = Column(String, nullable=False)
    category = Column(Enum(Category), default=Category.GENERAL)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    