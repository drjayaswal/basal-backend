import httpx
import logging
from app.db.connect import SessionLocal
from app.db.models import AnalysisStatus
from app.db.cruds import update_file_record, create_initial_record
from app.config import settings

logger = logging.getLogger(__name__)
get_settings = settings()

async def ml_analysis_drive(user_id: str, files: list, google_token: str, description: str):
    db = SessionLocal()
    target_url = f"{get_settings.ML_SERVER_URL}/analyze-drive"
    
    async with httpx.AsyncClient(timeout=180.0) as client:
        for file_info in files:
            record = create_initial_record(
                db=db, 
                user_id=user_id, 
                filename=file_info.get("name"), 
                s3_key=None 
            )
            
            try:
                payload = {
                    "file_id": file_info.get("id"),
                    "google_token": google_token,
                    "filename": file_info.get("name"),
                    "mime_type": file_info.get("mimeType"),
                    "description": description
                }

                resp = await client.post(target_url, json=payload)
                
                if resp.status_code == 200:
                    ml_data = resp.json()
                    update_file_record(
                        db, 
                        file_id=str(record.id), 
                        status=AnalysisStatus.COMPLETED, 
                        score=ml_data.get("match_score", 0),
                        details=ml_data.get("analysis_details", {}),
                        candidate_info=ml_data.get("candidate_info", {})
                    )
                else:
                    logger.error(f"ML Error for {file_info.get('name')}: {resp.text}")
                    update_file_record(db, file_id=str(record.id), status=AnalysisStatus.FAILED)
                    
            except Exception as e:
                logger.error(f"Background Task Error for {file_info.get('name')}: {e}")
                update_file_record(db, file_id=str(record.id), status=AnalysisStatus.FAILED)
    
    db.close()

async def ml_analysis_s3(file_id: str, s3_url: str, filename: str, description: str):
    db = SessionLocal()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            target_url = f"{get_settings.ML_SERVER_URL}/analyze-s3"
            
            resp = await client.post(
                target_url, 
                json={
                    "filename": filename, 
                    "file_url": s3_url,
                    "description": description
                }
            )
            
            if resp.status_code == 200:
                ml_data = resp.json()
                update_file_record(
                    db, file_id, 
                        status=AnalysisStatus.COMPLETED, 
                        score=ml_data.get("match_score", 0),
                        details=ml_data.get("analysis_details", {}),
                        candidate_info=ml_data.get("candidate_info", {})
                )
            else:
                update_file_record(db, file_id, status=AnalysisStatus.FAILED)
    except Exception as e:
        logger.error(f"S3 ML Task Crash: {e}")
        update_file_record(db, file_id, status=AnalysisStatus.FAILED)
    finally:
        db.close()