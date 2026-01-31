from fastapi import Header
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

def get_drive_service(authorization: str = Header(...)):
    token = authorization.split(" ")[1]
    creds = Credentials(token=token)
    return build('drive', 'v3', credentials=creds)
