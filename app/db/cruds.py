from sqlalchemy.orm import Session
from .models import ResumeAnalysis, AnalysisStatus
import uuid

def create_initial_record(db: Session, user_id: str, filename: str, s3_key: str = None, file_id=None, candidate_info: dict = None):
    db_record = ResumeAnalysis(
        id=file_id or uuid.uuid4(),
        user_id=user_id,
        filename=filename,
        s3_key=s3_key,
        status=AnalysisStatus.PROCESSING,
        match_score=0.0,
        details={},
        candidate_info=candidate_info or {}
    )
    db.add(db_record)
    try:
        db.commit()
        db.refresh(db_record)
    except Exception as e:
        db.rollback()
        raise e
    return db_record

def update_file_record(db: Session, file_id: str, status: AnalysisStatus, score: float = None, details: dict = None, candidate_info: dict = None):
    db_record = db.query(ResumeAnalysis).filter(ResumeAnalysis.id == file_id).first()
    if db_record:
        db_record.status = status
        if score is not None:
            db_record.match_score = score
        if details is not None:
            db_record.details = details
        if candidate_info is not None:
            db_record.candidate_info = candidate_info
        db.commit()
        db.refresh(db_record)
    return db_record