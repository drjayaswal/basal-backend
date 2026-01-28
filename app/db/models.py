import uuid, enum
from sqlalchemy import Column, String, DateTime, func, ForeignKey, Float, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .connect import Base

class AnalysisStatus(enum.Enum):
    FAILED = "failed"
    PENDING = "pending"
    COMPLETED = "completed"
    PROCESSING = "processing"

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
    analyses = relationship("ResumeAnalysis", back_populates="owner", cascade="all, delete-orphan")

class ResumeAnalysis(Base):
    __tablename__ = "resume_analyses"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String, nullable=False)
    s3_key = Column(String, nullable=True)
    status = Column(Enum(AnalysisStatus), default=AnalysisStatus.PENDING)
    match_score = Column(Float, default=0.0)
    details = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    owner = relationship("User", back_populates="analyses")