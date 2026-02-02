from sqlalchemy import func
from sqlalchemy.orm import Session
from .models import ResumeAnalysis, AnalysisStatus, User
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
    if isinstance(file_id, str):
        file_uuid = uuid.UUID(file_id)
    else:
        file_uuid = file_id
    db_record = db.query(ResumeAnalysis).filter(ResumeAnalysis.id == file_uuid).first()
    if not db_record:
        print(f"CRITICAL ERROR: Record {file_id} not found in database!")
        return None

    db_record.status = status
    if score is not None: db_record.match_score = score
    if details is not None: db_record.details = details
    if candidate_info is not None: db_record.candidate_info = candidate_info
    
    # Deduct credit
    user = db.query(User).filter(User.id == db_record.user_id).first()
    if user and user.credits > 0:
        user.credits -= 1
        print(f"Credit deducted. Remaining: {user.credits}")

    db.commit()
    db.refresh(db_record)
    print(f"SUCCESS: Record {file_id} updated to {status}")
    return db_record