import os
import time
import json
import zipfile
import shutil
import logging
import base64
from datetime import datetime
import requests
import openpyxl
from docx import Document
import pandas as pd
import PyPDF2
import fitz
from gtts import gTTS
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

def _base_dir():
    # Base folder: prefer explicit APP_BASE_DIR env; fallback to directory of this file (project root)
    return os.getenv('APP_BASE_DIR') or os.path.abspath(os.path.dirname(__file__))

def get_upload_base():
    return os.getenv('UPLOAD_FOLDER') or os.path.join(_base_dir(), 'uploads')

def get_productos_dir_for_config(config=None):
    """
    Return (productos_dir, tenant_slug). Ensures uploads/productos/<tenant_slug> exists.
    Compatible con app.get_productos_dir_for_config.
    """
    if config is None:
        config = {}
    dominio = (config.get('dominio') or '').strip().lower()
    tenant_slug = dominio.split('.')[0] if dominio else 'default'
    productos_dir = os.path.join(get_upload_base(), 'productos', tenant_slug)
    os.makedirs(productos_dir, exist_ok=True)
    return productos_dir, tenant_slug

def get_docs_dir_for_config(config=None):
    """
    Return (docs_dir, tenant_slug). Ensures uploads/docs/<tenant_slug> exists.
    Compatible con app.get_docs_dir_for_config.
    """
    if config is None:
        config = {}
    dominio = (config.get('dominio') or '').strip().lower()
    tenant_slug = dominio.split('.')[0] if dominio else 'default'
    docs_dir = os.path.join(get_upload_base(), 'docs', tenant_slug)
    try:
        os.makedirs(docs_dir, exist_ok=True)
    except Exception as e:
        logger.warning(f"⚠️ Could not create docs_dir {docs_dir}: {e}")
        docs_dir = os.path.join(get_upload_base(), 'docs')
        os.makedirs(docs_dir, exist_ok=True)
    return docs_dir, tenant_slug

ALLOWED_EXTENSIONS = {
    'pdf', 'xlsx', 'xls', 'csv', 'docx', 'txt',
    'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg',
    'mp4', 'mov', 'webm', 'avi', 'mkv', 'ogg', 'mpeg'
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def determinar_extension(mime_type, filename):
    mime_to_extension = {
        'application/pdf': 'pdf',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
        'application/vnd.ms-excel': 'xls',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
        'text/csv': 'csv',
        'text/plain': 'txt'
    }
    extension = mime_to_extension.get(mime_type)
    if not extension and '.' in filename:
        extension = filename.split('.')[-1].lower()
    return extension or 'bin'

def extraer_imagenes_embedded_excel(filepath, output_dir=None, config=None):
    """
    Extrae imágenes embebidas de un .xlsx usando openpyxl, guarda en output_dir.
    Retorna lista de dicts: {'filename','path','sheet','anchor','row','col'}
    """
    try:
        if output_dir is None:
            output_dir, _ = get_productos_dir_for_config(config)
        os.makedirs(output_dir, exist_ok=True)

        wb = openpyxl.load_workbook(filepath)
        imagenes_extraidas = []

        for sheet in wb.worksheets:
            for idx, img in enumerate(getattr(sheet, '_images', [])):
                try:
                    img_obj = img.image
                    img_format = (getattr(img_obj, 'format', None) or 'PNG').lower()
                    img_filename = f"excel_img_{sheet.title}_{idx+1}_{int(time.time())}.{img_format}"
                    img_path = os.path.join(output_dir, img_filename)
                    try:
                        img_obj.save(img_path)
                    except Exception as e:
                        logger.warning(f"⚠️ Could not save embedded image {img_filename}: {e}")
                        continue

                    row = None; col = None
                    anchor = getattr(img, 'anchor', None)
                    try:
                        marker = None
                        for attr in ('_from', 'from', 'from_', 'anchor_from'):
                            marker = getattr(anchor, attr, None)
                            if marker:
                                break
                        if marker:
                            row_candidate = getattr(marker, 'row', None)
                            col_candidate = getattr(marker, 'col', None)
                            if row_candidate is None and hasattr(marker, '__len__'):
                                try:
                                    maybe = list(marker)
                                    ints = [m for m in maybe if isinstance(m, int)]
                                    if len(ints) >= 1:
                                        row_candidate = ints[0]
                                except Exception:
                                    pass
                            if isinstance(row_candidate, int):
                                row = int(row_candidate) + 1
                            if isinstance(col_candidate, int):
                                col = int(col_candidate) + 1
                        if row is None and isinstance(anchor, str):
                            try:
                                from openpyxl.utils.cell import coordinate_from_string, column_index_from_string
                                col_letter, row_num = coordinate_from_string(anchor)
                                col = column_index_from_string(col_letter)
                                row = int(row_num)
                            except Exception:
                                pass
                    except Exception:
                        row = None; col = None

                    imagenes_extraidas.append({
                        'filename': img_filename,
                        'path': img_path,
                        'sheet': sheet.title,
                        'anchor': anchor,
                        'row': row,
                        'col': col
                    })
                    logger.info(f"✅ Extracted embedded image: {img_filename} (sheet={sheet.title} row={row} col={col})")
                except Exception as e:
                    logger.warning(f"⚠️ Error extracting embedded image on sheet {sheet.title} idx {idx}: {e}")
                    continue

        return imagenes_extraidas

    except Exception as e:
        logger.error(f"🔴 extraer_imagenes_embedded_excel error: {e}")
        return []

def _extraer_imagenes_desde_zip_xlsx(filepath, output_dir):
    """
    Fallback: extrae imágenes desde el ZIP de un .xlsx leyendo xl/media/.
    """
    os.makedirs(output_dir, exist_ok=True)
    imagenes = []
    try:
        with zipfile.ZipFile(filepath, 'r') as z:
            media_files = [f for f in z.namelist() if f.startswith('xl/media/')]
            for idx, media_path in enumerate(media_files):
                try:
                    ext = os.path.splitext(media_path)[1].lstrip('.').lower() or 'bin'
                    timestamp = int(time.time())
                    filename = f"excel_unzip_img_{idx+1}_{timestamp}.{ext}"
                    dest_path = os.path.join(output_dir, filename)
                    with z.open(media_path) as src, open(dest_path, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                    imagenes.append({
                        'filename': filename,
                        'path': dest_path,
                        'sheet': None,
                        'anchor': None,
                        'row': None,
                        'col': None
                    })
                    logger.info(f"✅ Extracted zip image: {filename} from {media_path}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not extract {media_path} from zip: {e}")
    except zipfile.BadZipFile:
        logger.warning("⚠️ Not a valid .xlsx zip; zip fallback failed")
    except Exception as e:
        logger.warning(f"⚠️ Error extracting images from zip: {e}")
    return imagenes

def extraer_texto_e_imagenes_pdf(file_path, config=None):
    """
    Extrae texto e imágenes de PDF usando PyMuPDF (fitz). Guarda imágenes en productos dir.
    Retorna (texto, imagenes_list). imagenes_list = [{'filename','path','page','size','xref','rect'}]
    """
    try:
        texto = ""
        imagenes = []

        doc = fitz.open(file_path)
        try:
            productos_dir, tenant_slug = get_productos_dir_for_config(config)
        except Exception:
            productos_dir = os.path.join(get_upload_base(), 'productos')
        os.makedirs(productos_dir, exist_ok=True)

        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            texto += page.get_text()
            image_list = page.get_images(full=True)
            for img_idx, img_info in enumerate(image_list):
                try:
                    xref = img_info[0]
                    base_img = doc.extract_image(xref)
                    imagen_bytes = base_img["image"]
                    extension = base_img.get("ext", "png")
                    img_filename = f"producto_{page_num+1}_{img_idx+1}_{int(time.time())}.{extension}"
                    img_path = os.path.join(productos_dir, img_filename)
                    with open(img_path, "wb") as img_file:
                        img_file.write(imagen_bytes)
                    try:
                        rect = page.get_image_bbox(xref)
                    except Exception:
                        rect = fitz.Rect(0, 0, 0, 0)
                    imagenes.append({
                        'filename': img_filename,
                        'path': img_path,
                        'page': page_num,
                        'size': len(imagen_bytes),
                        'position': img_info[1:],
                        'xref': xref,
                        'rect': rect
                    })
                    logger.info(f"✅ Extracted PDF image: {img_filename}")
                except Exception as e:
                    logger.warning(f"⚠️ Error extracting image {img_idx} on page {page_num+1}: {e}")
                    continue
        doc.close()
        logger.info(f"✅ Extracted text length: {len(texto)}; images: {len(imagenes)}")
        return texto.strip(), imagenes
    except Exception as e:
        logger.error(f"🔴 extraer_texto_e_imagenes_pdf error: {e}")
        # fallback to text-only
        try:
            texto = extraer_texto_pdf(file_path)
            return texto or None, []
        except Exception:
            return None, []

def extraer_texto_pdf(file_path):
    """Extrae texto de PDF con fitz y fallback a PyPDF2"""
    try:
        texto = ""
        try:
            doc = fitz.open(file_path)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                texto += page.get_text()
            doc.close()
            logger.info(f"✅ Extraido texto con PyMuPDF: {len(texto)} chars")
            return texto.strip()
        except Exception as e:
            logger.warning(f"⚠️ PyMuPDF failed, trying PyPDF2: {e}")

        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for p in reader.pages:
                try:
                    txt = p.extract_text() or ""
                except Exception:
                    txt = ""
                texto += txt
        logger.info(f"✅ Extraido texto con PyPDF2: {len(texto)} chars")
        return texto.strip()
    except Exception as e:
        logger.error(f"🔴 extraer_texto_pdf error: {e}")
        return None

def extraer_texto_excel(filepath):
    """Extrae texto de Excel (openpyxl + pandas fallback)"""
    try:
        texto = ""
        try:
            workbook = openpyxl.load_workbook(filepath, data_only=True)
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                texto += f"\n--- Hoja: {sheet_name} ---\n"
                for row in sheet.iter_rows(values_only=True):
                    fila_texto = " | ".join(str(cell) for cell in row if cell is not None)
                    if fila_texto.strip():
                        texto += fila_texto + "\n"
        except Exception as e:
            logger.warning(f"⚠️ openpyxl failed parsing excel: {e}")

        try:
            excel_file = pd.ExcelFile(filepath)
            for sheet_name in excel_file.sheet_names:
                df = pd.read_excel(filepath, sheet_name=sheet_name)
                texto += f"\n--- Hoja: {sheet_name} (pandas) ---\n"
                texto += df.to_string() + "\n"
        except Exception as e:
            logger.warning(f"⚠️ pandas excel fallback failed: {e}")

        return texto.strip() if texto.strip() else None
    except Exception as e:
        logger.error(f"🔴 extraer_texto_excel error: {e}")
        return None

def extraer_texto_csv(filepath):
    try:
        df = pd.read_csv(filepath)
        return df.to_string()
    except Exception as e:
        logger.warning(f"⚠️ pandas read_csv failed: {e}")
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            return None

def extraer_texto_docx(filepath):
    try:
        doc = Document(filepath)
        texto = "\n".join(p.text for p in doc.paragraphs if p.text)
        return texto.strip() if texto.strip() else None
    except Exception as e:
        logger.error(f"🔴 extraer_texto_docx error: {e}")
        return None

def extraer_texto_archivo(filepath, extension):
    try:
        ext = (extension or os.path.splitext(filepath)[1].lstrip('.')).lower()
        if ext == 'pdf':
            return extraer_texto_pdf(filepath)
        if ext in ('xlsx', 'xls'):
            return extraer_texto_excel(filepath)
        if ext == 'csv':
            return extraer_texto_csv(filepath)
        if ext == 'docx':
            return extraer_texto_docx(filepath)
        if ext == 'txt':
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        logger.warning(f"⚠️ extraer_texto_archivo: unsupported extension {ext}")
        return None
    except Exception as e:
        logger.error(f"🔴 extraer_texto_archivo error: {e}")
        return None

def obtener_imagen_whatsapp(media_id, config=None):
    """
    Descarga metadata y contenido desde Graph API y devuelve (base64_string, public_url).
    public_url is relative (e.g. /static/images/whatsapp/filename) — caller stores file if needed.
    """
    try:
        if config is None:
            config = {}
        token = config.get('whatsapp_token') or os.getenv('MEKTIA_WHATSAPP_TOKEN') or os.getenv('WHATSAPP_TOKEN')
        if not token:
            logger.error("🔴 obtener_imagen_whatsapp: no whatsapp token configured")
            return None, None

        url_meta = f"https://graph.facebook.com/v18.0/{media_id}"
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        r = requests.get(url_meta, headers=headers, timeout=30)
        r.raise_for_status()
        meta = r.json()
        download_url = meta.get('url')
        mime = meta.get('mime_type', 'image/jpeg')
        if not download_url:
            logger.error(f"🔴 No download url in metadata: {meta}")
            return None, None

        img_r = requests.get(download_url, headers=headers, timeout=30)
        img_r.raise_for_status()
        content = img_r.content
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        static_dir = os.path.join(_base_dir(), 'static', 'images', 'whatsapp')
        os.makedirs(static_dir, exist_ok=True)
        filename = secure_filename(f"whatsapp_image_{timestamp}.jpg")
        filepath = os.path.join(static_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(content)

        b64 = base64.b64encode(content).decode('utf-8')
        base64_string = f"data:{mime};base64,{b64}"
        public_url = f"/static/images/whatsapp/{filename}"
        logger.info(f"✅ Saved whatsapp image: {filepath}")
        return base64_string, public_url
    except Exception as e:
        logger.error(f"🔴 obtener_imagen_whatsapp error: {e}")
        return None, None

def obtener_audio_whatsapp(audio_id, config=None):
    """
    Descarga audio desde Graph API y guarda en uploads; retorna (audio_path, public_url)
    """
    try:
        if config is None:
            config = {}
        token = config.get('whatsapp_token') or os.getenv('MEKTIA_WHATSAPP_TOKEN') or os.getenv('WHATSAPP_TOKEN')
        if not token:
            logger.error("🔴 obtener_audio_whatsapp: no whatsapp token configured")
            return None, None

        meta_url = f"https://graph.facebook.com/v18.0/{audio_id}"
        headers = {'Authorization': f'Bearer {token}'}
        r = requests.get(meta_url, headers=headers, timeout=30)
        r.raise_for_status()
        meta = r.json()
        download_url = meta.get('url')
        if not download_url:
            logger.error(f"🔴 No download url for audio: {meta}")
            return None, None

        audio_r = requests.get(download_url, headers=headers, timeout=30)
        audio_r.raise_for_status()
        content = audio_r.content

        uploads = get_upload_base()
        os.makedirs(uploads, exist_ok=True)
        audio_path = os.path.join(uploads, f"audio_{audio_id}.ogg")
        with open(audio_path, 'wb') as f:
            f.write(content)

        dominio = (config.get('dominio') or os.getenv('MI_DOMINIO') or 'http://localhost:5000').rstrip('/')
        if not dominio.startswith('http'):
            dominio = f"https://{dominio}"
        audio_url = f"{dominio}/uploads/{os.path.basename(audio_path)}"
        logger.info(f"✅ Saved whatsapp audio: {audio_path}")
        return audio_path, audio_url
    except Exception as e:
        logger.error(f"🔴 obtener_audio_whatsapp error: {e}")
        return None, None

def texto_a_voz(texto, filename, config=None):
    """
    Genera MP3 con gTTS en static/audio/respuestas y retorna filepath absoluto.
    Caller must build public URL.
    """
    try:
        base_dir = _base_dir()
        audio_dir = os.path.join(base_dir, 'static', 'audio', 'respuestas')
        os.makedirs(audio_dir, exist_ok=True)
        filepath = os.path.join(audio_dir, f"{filename}.mp3")
        tts = gTTS(text=texto, lang='es', slow=False)
        tts.save(filepath)
        logger.info(f"✅ texto_a_voz saved: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"🔴 texto_a_voz error: {e}")
        return None