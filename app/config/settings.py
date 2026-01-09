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

# Prefijos de país para banderas (movido desde app.py)
PREFIJOS_PAIS = {
    '52': 'mx', '1': 'us', '54': 'ar', '57': 'co', '55': 'br',
    '34': 'es', '51': 'pe', '56': 'cl', '58': 've', '593': 'ec',
    '591': 'bo', '507': 'pa', '502': 'gt'
}
