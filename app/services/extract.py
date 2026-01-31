import io
from PyPDF2 import PdfReader
from docx import Document

def text(content: bytes, mime_type: str) -> str:
    text = ""
    try:
        if not content:
            print("Error: Received empty content bytes")
            return ""

        if mime_type == "application/pdf":
            stream = io.BytesIO(content)
            reader = PdfReader(stream)
            page_texts = []
            for page in reader.pages:
                extracted = page.text()
                if extracted:
                    page_texts.append(extracted)
            text = " ".join(page_texts)

        elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            stream = io.BytesIO(content)
            doc = Document(stream)
            text = " ".join([para.text for para in doc.paragraphs if para.text])

        elif mime_type == "text/plain":
            text = content.decode("utf-8", errors="ignore")

    except Exception as e:
        print(f"Extraction Error: {str(e)}")
        
    return text.strip()
