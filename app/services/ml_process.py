import httpx
import asyncio
import logging
from app.db.connect import SessionLocal
from app.db.models import AnalysisStatus
from app.db.cruds import update_file_record, create_initial_record
from app.config import settings

logger = logging.getLogger(__name__)
get_settings = settings()

async def ml_health_check(max_retries=5, delay=5):
    async with httpx.AsyncClient() as client:
        for i in range(max_retries):
            try:
                # Lower timeout so we don't hang on a dead socket
                response = await client.get(f"{get_settings.ML_SERVER_URL}/health", timeout=2.0)
                if response.status_code == 200:
                    return True
            except (httpx.ConnectError, httpx.RequestError):
                # This happens while the ML server is "Waking Up"
                print(f"ML Server waking up (attempt {i+1})...")
            
            await asyncio.sleep(delay)
    return False


async def ml_analysis_drive(user_id: str, files: list, google_token: str, description: str):
    is_awake = await ml_health_check(max_retries=12, delay=10)
    
    db = SessionLocal()
    try:
        if not is_awake:
            logger.error("ML Server failed to wake up. Aborting drive analysis.")
            return

        target_url = f"{get_settings.ML_SERVER_URL}/analyze-drive"
        
        async with httpx.AsyncClient(timeout=180.0) as client:
            for file_info in files:
                # Create the 'Pending' record
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

                    headers = {"X-API-Key": get_settings.ML_SERVER_API_KEY}
                    resp = await client.post(target_url,  json=payload, headers=headers)
                    
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
                        update_file_record(db, file_id=str(record.id), status=AnalysisStatus.FAILED)
                        
                except Exception as e:
                    logger.error(f"Error processing {file_info.get('name')}: {e}")
                    update_file_record(db, file_id=str(record.id), status=AnalysisStatus.FAILED)
    finally:
        db.close()

async def ml_analysis_s3(file_id: str, s3_url: str, filename: str, description: str):
    is_awake = await ml_health_check(max_retries=12, delay=10)
    
    db = SessionLocal()
    try:
        if not is_awake:
            update_file_record(db, file_id, status=AnalysisStatus.FAILED)
            return

        async with httpx.AsyncClient(timeout=120.0) as client:
            target_url = f"{get_settings.ML_SERVER_URL}/analyze-s3"
            headers = {"X-API-Key": get_settings.ML_SERVER_API_KEY}
            resp = await client.post(
                target_url, 
                json={
                    "filename": filename, 
                    "file_url": s3_url,
                    "description": description
                },
                timeout=120.0,
                headers=headers
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