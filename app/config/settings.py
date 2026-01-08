import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # SOLO esto por ahora
    ALLOWED_EXTENSIONS = {
        'pdf', 'txt', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg',
        'mp4', 'mov', 'webm', 'avi', 'mkv', 'ogg', 'mpeg',
        'xlsx', 'xls', 'csv', 'docx', 'doc', 
        'ppt', 'pptx', 'mp3', 'wav', 'ogg', 'm4a',
        'zip', 'rar', '7z', 'rtf'
    }
