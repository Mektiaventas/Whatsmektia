import os
import time
import traceback
import zipfile
import shutil
import logging

import pandas as pd
import openpyxl
import PyPDF2
import fitz
from docx import Document
from werkzeug.utils import secure_filename

# Intentar reusar `app` y constantes si el módulo principal ya existe.
try:
    from app import app, UPLOAD_FOLDER, obtener_configuracion_por_host, get_productos_dir_for_config
except Exception:
    # Fallbacks mínimos para desarrollo/local
    app = None
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'uploads')
    def obtener_configuracion_por_host():
        return {}
    def get_productos_dir_for_config(config=None):
        productos_dir = os.path.join(UPLOAD_FOLDER, 'productos')
        os.makedirs(productos_dir, exist_ok=True)
        return productos_dir, 'default'

# Logger: prefer app.logger cuando esté disponible
logger = app.logger if app is not None else logging.getLogger(__name__)

def determinar_extension(mime_type, filename):
    """Determina la extensión del archivo basado en MIME type y nombre"""
    mime_to_extension = {
        'application/pdf': 'pdf',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
        'application/vnd.ms-excel': 'xls',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
        'text/csv': 'csv',
        'text/plain': 'txt'
    }
    
    # Primero intentar por MIME type
    extension = mime_to_extension.get(mime_type)
    
    # Si no se encuentra, intentar por extensión del nombre de archivo
    if not extension and '.' in filename:
        extension = filename.split('.')[-1].lower()
    
    return extension or 'bin'

def extraer_imagenes_embedded_excel(filepath, output_dir=None, config=None):
    """
    Extrae imágenes embebidas de un archivo Excel (.xlsx) y las guarda en output_dir.
    Soporta multi-tenant: si no se pasa output_dir, usa get_productos_dir_for_config(config)
    para guardar en uploads/productos/<tenant_slug>.
    Retorna lista de dicts: {'filename','path','sheet','anchor','row','col'}
    """
    try:
        # Determine tenant-aware output dir when none provided
        if output_dir is None:
            try:
                productos_dir, tenant_slug = get_productos_dir_for_config(config)
                output_dir = productos_dir
            except Exception as e:
                # Fallback to legacy dir if tenant helper fails
                logger.warning(f"⚠️ get_productos_dir_for_config falló, usando legacy. Error: {e}")
                output_dir = os.path.join(UPLOAD_FOLDER, 'productos')

        os.makedirs(output_dir, exist_ok=True)

        wb = openpyxl.load_workbook(filepath)
        imagenes_extraidas = []

        for sheet in wb.worksheets:
            for idx, img in enumerate(getattr(sheet, '_images', [])):
                try:
                    img_obj = img.image
                    img_format = (img_obj.format or 'PNG').lower()
                    img_filename = f"excel_img_{sheet.title}_{idx+1}_{int(time.time())}.{img_format}"
                    img_path = os.path.join(output_dir, img_filename)

                    # Guardar imagen en disco
                    try:
                        img_obj.save(img_path)
                    except Exception as e:
                        logger.warning(f"⚠️ No se pudo guardar imagen en disco {img_filename}: {e}")
                        continue

                    # Intentar leer la ancla (fila/col) de varias formas
                    row = None
                    col = None
                    anchor = getattr(img, 'anchor', None)
                    try:
                        marker = None
                        # Common attribute names in different openpyxl versions
                        for attr in ('_from', 'from', 'from_', 'anchor_from'):
                            marker = getattr(anchor, attr, None)
                            if marker:
                                break

                        if marker:
                            # marker usually tiene row, col (0-based)
                            row_candidate = getattr(marker, 'row', None)
                            col_candidate = getattr(marker, 'col', None)
                            # Algunas versiones devuelven atributos como tuples o listas
                            if row_candidate is None and hasattr(marker, '__len__') and len(marker) >= 1:
                                # try tuple-like (col, row) or (row, col)
                                try:
                                    maybe = list(marker)
                                    # buscar primer int
                                    ints = [m for m in maybe if isinstance(m, int)]
                                    if len(ints) >= 1:
                                        row_candidate = ints[0]
                                except Exception:
                                    pass

                            if isinstance(row_candidate, int):
                                row = int(row_candidate) + 1
                            if isinstance(col_candidate, int):
                                col = int(col_candidate) + 1

                        # Si anchor es string con coordenada (ej. "A2"), parsearla
                        if row is None and isinstance(anchor, str):
                            try:
                                from openpyxl.utils.cell import coordinate_from_string, column_index_from_string
                                col_letter, row_num = coordinate_from_string(anchor)
                                col = column_index_from_string(col_letter)
                                row = int(row_num)
                            except Exception:
                                pass
                    except Exception:
                        row = None
                        col = None

                    imagenes_extraidas.append({
                        'filename': img_filename,
                        'path': img_path,
                        'sheet': sheet.title,
                        'anchor': anchor,
                        'row': row,
                        'col': col
                    })
                    logger.info(f"✅ Imagen extraída: {img_filename} (sheet={sheet.title} row={row} col={col}) tenant_dir={output_dir}")
                except Exception as e:
                    logger.warning(f"⚠️ Error extrayendo imagen en sheet {sheet.title} idx {idx}: {e}")
                    continue

        return imagenes_extraidas

    except Exception as e:
        logger.error(f"🔴 Error en extraer_imagenes_embedded_excel: {e}")
        logger.error(traceback.format_exc())
        return []

def _extraer_imagenes_desde_zip_xlsx(filepath, output_dir):
    """
    Fallback: extrae imágenes desde el ZIP de un .xlsx leyendo xl/media/.
    Retorna lista de dicts compatible con extraer_imagenes_embedded_excel.
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
                    logger.info(f"✅ Imagen (zip) extraída: {filename} from {media_path}")
                except Exception as e:
                    logger.warning(f"⚠️ No se pudo extraer {media_path} desde zip: {e}")
    except zipfile.BadZipFile:
        logger.warning("⚠️ Archivo no es un .xlsx válido o está corrupto; zip fallback falló")
    except Exception as e:
        logger.warning(f"⚠️ Error extrayendo imágenes desde zip: {e}")
    return imagenes

def get_docs_dir_for_config(config=None):
    """Return (docs_dir, tenant_slug). Ensures uploads/docs/<tenant_slug> exists."""
    if config is None:
        try:
            # in some contexts, app context exists and helper available
            config = obtener_configuracion_por_host()
        except Exception:
            config = {}
    dominio = (config.get('dominio') or '').strip().lower()
    tenant_slug = dominio.split('.')[0] if dominio else 'default'
    docs_dir = os.path.join(os.path.abspath(UPLOAD_FOLDER), 'docs', tenant_slug)
    try:
        os.makedirs(docs_dir, exist_ok=True)
    except Exception as e:
        logger.warning(f"⚠️ No se pudo crear docs_dir {docs_dir}: {e}")
        # fallback to a shared docs dir
        docs_dir = os.path.join(os.path.abspath(UPLOAD_FOLDER), 'docs')
        os.makedirs(docs_dir, exist_ok=True)
    return docs_dir, tenant_slug

def get_productos_dir_for_config(config=None):
    """Return (productos_dir, tenant_slug). Ensures uploads/productos/<tenant_slug> exists."""
    if config is None:
        try:
            config = obtener_configuracion_por_host()
        except Exception:
            config = {}
    dominio = (config.get('dominio') or '').strip().lower()
    tenant_slug = dominio.split('.')[0] if dominio else 'default'
    productos_dir = os.path.join(os.path.abspath(UPLOAD_FOLDER), 'productos', tenant_slug)
    os.makedirs(productos_dir, exist_ok=True)
    return productos_dir, tenant_slug

def extraer_texto_e_imagenes_pdf(file_path):
    """Extrae texto e imágenes de un archivo PDF"""
    try:
        texto = ""
        imagenes = []
        
        # Abrir el PDF con PyMuPDF
        doc = fitz.open(file_path)
        
        # Crear directorio para imágenes si no existe (tenant-aware fallback)
        try:
            productos_dir, tenant_slug = get_productos_dir_for_config()
            img_dir = productos_dir
        except Exception as e:
            logger.warning(f"⚠️ get_productos_dir_for_config falló, usando legacy uploads/productos. Error: {e}")
            img_dir = os.path.join(UPLOAD_FOLDER, 'productos')
        os.makedirs(img_dir, exist_ok=True)
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            
            # Extraer texto
            texto += page.get_text()
            
            # Extraer imágenes
            image_list = page.get_images(full=True)
            for img_idx, img_info in enumerate(image_list):
                try:
                    xref = img_info[0]
                    
                    # Verificar si la imagen es válida antes de procesarla
                    try:
                        base_img = doc.extract_image(xref)
                        
                        # Obtener la imagen en bytes
                        imagen_bytes = base_img["image"]
                        
                        # Determinar formato de imagen
                        extension = base_img["ext"]
                        
                        # Crear nombre único para la imagen
                        img_filename = f"producto_{page_num+1}_{img_idx+1}_{int(time.time())}.{extension}"
                        img_path = os.path.join(img_dir, img_filename)
                        
                        # Guardar la imagen
                        with open(img_path, "wb") as img_file:
                            img_file.write(imagen_bytes)
                        
                        # Intentar obtener el rectángulo de la imagen de manera segura
                        try:
                            rect = page.get_image_bbox(xref)
                        except ValueError:
                            # Si falla, usar un rectángulo vacío
                            rect = fitz.Rect(0, 0, 0, 0)
                        
                        # Agregar a la lista de imágenes con metadatos útiles
                        imagenes.append({
                            'filename': img_filename,
                            'path': img_path,
                            'page': page_num,
                            'size': len(imagen_bytes),
                            'position': img_info[1:],  # Info de posición para asociar con texto
                            'xref': xref,
                            'rect': rect
                        })
                        
                        logger.info(f"✅ Imagen extraída: {img_filename} (tenant_dir={img_dir})")
                        
                    except Exception as e:
                        logger.warning(f"⚠️ Error extrayendo imagen específica {xref}: {e}")
                        continue
                        
                except Exception as e:
                    logger.warning(f"⚠️ Error procesando imagen {img_idx} en página {page_num+1}: {e}")
                    continue
        
        doc.close()
        
        logger.info(f"✅ Texto extraído: {len(texto)} caracteres")
        logger.info(f"🖼️ Imágenes extraídas: {len(imagenes)}")
        
        return texto.strip(), imagenes
        
    except Exception as e:
        logger.error(f"🔴 Error extrayendo contenido PDF: {e}")
        logger.error(traceback.format_exc())
        
        # Intenta al menos extraer el texto usando el método anterior
        try:
            texto = extraer_texto_pdf(file_path)
            logger.info(f"✅ Se pudo extraer texto con método alternativo: {len(texto)} caracteres")
            return texto, []  # Devolver texto pero sin imágenes
        except:
            return None, []

def extraer_texto_pdf(file_path):
    """Extrae texto de un archivo PDF"""
    try:
        texto = ""
        
        # Intentar con PyMuPDF primero (más robusto)
        try:
            doc = fitz.open(file_path)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                texto += page.get_text()
            doc.close()
            logger.info(f"✅ Texto extraído con PyMuPDF: {len(texto)} caracteres")
            return texto.strip()
        except Exception as e:
            logger.warning(f"⚠️ PyMuPDF falló, intentando con PyPDF2: {e}")
        
        # Fallback a PyPDF2
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                texto += page.extract_text()
        
        logger.info(f"✅ Texto extraído con PyPDF2: {len(texto)} caracteres")
        return texto.strip()
        
    except Exception as e:
        logger.error(f"🔴 Error extrayendo texto PDF: {e}")
        return None

def extraer_texto_excel(filepath):
    """Extrae texto de archivos Excel"""
    try:
        texto = ""
        
        # Leer todas las hojas
        if filepath.endswith('.xlsx'):
            workbook = openpyxl.load_workbook(filepath)
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                texto += f"\n--- Hoja: {sheet_name} ---\n"
                
                for row in sheet.iter_rows(values_only=True):
                    fila_texto = " | ".join(str(cell) for cell in row if cell is not None)
                    if fila_texto.strip():
                        texto += fila_texto + "\n"
        
        # Alternativa con pandas para mejor compatibilidad
        try:
            excel_file = pd.ExcelFile(filepath)
            for sheet_name in excel_file.sheet_names:
                df = pd.read_excel(filepath, sheet_name=sheet_name)
                texto += f"\n--- Hoja: {sheet_name} (Pandas) ---\n"
                texto += df.to_string() + "\n"
        except Exception as e:
            logger.warning(f"⚠️ Pandas falló: {e}")
        
        return texto.strip() if texto.strip() else None
        
    except Exception as e:
        logger.error(f"🔴 Error procesando Excel: {e}")
        return None

def extraer_texto_csv(filepath):
    """Extrae texto de archivos CSV"""
    try:
        df = pd.read_csv(filepath)
        return df.to_string()
    except Exception as e:
        logger.error(f"🔴 Error leyendo CSV: {e}")
        # Intentar lectura simple
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except:
            return None

def extraer_texto_docx(filepath):
    """Extrae texto de archivos Word"""
    try:
        doc = Document(filepath)
        texto = ""
        for paragraph in doc.paragraphs:
            texto += paragraph.text + "\n"
        return texto.strip() if texto.strip() else None
    except Exception as e:
        logger.error(f"🔴 Error leyendo DOCX: {e}")
        return None

def extraer_texto_archivo(filepath, extension):
    """Extrae texto de diferentes tipos de archivos"""
    try:
        if extension == 'pdf':
            return extraer_texto_pdf(filepath)
        
        elif extension in ['xlsx', 'xls']:
            return extraer_texto_excel(filepath)
        
        elif extension == 'csv':
            return extraer_texto_csv(filepath)
        
        elif extension == 'docx':
            return extraer_texto_docx(filepath)
        
        elif extension == 'txt':
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        
        else:
            logger.warning(f"⚠️ Formato no soportado: {extension}")
            return None
            
    except Exception as e:
        logger.error(f"🔴 Error extrayendo texto de {extension}: {e}")
        return None