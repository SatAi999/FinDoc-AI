import io
import os
import time
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from PIL import Image
import fitz  # PyMuPDF

from app.core.config import settings
from app.core.logging import logger

class OCRService:
    """
    Unified OCR & Layout Service.
    Handles:
    - Native PyMuPDF text & layout bounding box extraction for digital PDFs.
    - EasyOCR CUDA GPU & PaddleOCR structure extraction for scanned documents.
    - Unified Document Representation with spatial page/text layout structures.
    """
    _cache: Dict[str, Dict[str, Any]] = {}
    _paddle_ocr = None
    _easyocr_reader = None

    @classmethod
    def should_skip_heavy_ocr(cls) -> bool:
        if getattr(settings, "DISABLE_HEAVY_OCR", False):
            return True
        if os.environ.get("RENDER") or os.environ.get("DISABLE_HEAVY_OCR"):
            return True
        return False

    @classmethod
    def get_paddle_ocr(cls):
        if cls.should_skip_heavy_ocr():
            logger.info("RAM-constrained environment detected (Render 512MB). Skipping PaddleOCR initialization to preserve RAM.")
            return None
        if cls._paddle_ocr is None:
            try:
                os.environ["FLAGS_enable_pir_api"] = "0"
                from paddleocr import PaddleOCR
                logger.info("Initializing PaddleOCR singleton (Primary Engine)...")
                cls._paddle_ocr = PaddleOCR(lang='en')
            except Exception as e:
                logger.warning(f"PaddleOCR initialization failed: {e}")
                cls._paddle_ocr = None
        return cls._paddle_ocr

    @classmethod
    def get_easyocr_reader(cls):
        if cls.should_skip_heavy_ocr():
            logger.info("RAM-constrained environment detected (Render 512MB). Skipping EasyOCR PyTorch initialization to preserve RAM.")
            return None
        if cls._easyocr_reader is None:
            try:
                import torch
                import easyocr
                has_cuda = torch.cuda.is_available()
                logger.info(f"Initializing EasyOCR Reader singleton (CUDA: {has_cuda})...")
                cls._easyocr_reader = easyocr.Reader(['en'], gpu=has_cuda, verbose=False)
            except Exception as e:
                logger.warning(f"EasyOCR initialization failed: {e}")
                cls._easyocr_reader = None
        return cls._easyocr_reader

    @classmethod
    def extract_text_and_layout(cls, file_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
        logger.info(f"Routing text & layout extraction via OCRService for: {filename}")
        parse_result = cls.parse_document(file_bytes, filename)
        return parse_result.get("pages_data", [])

    @classmethod
    def parse_document(cls, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        start_time = time.time()
        doc_hash = hashlib.sha256(file_bytes).hexdigest()
        
        if doc_hash in cls._cache:
            logger.info(f"Returning cached parsing result for hash {doc_hash[:10]} ({filename})")
            cached_res = dict(cls._cache[doc_hash])
            cached_res["provenance"]["from_cache"] = True
            return cached_res

        ext = os.path.splitext(filename)[1].lower()
        pages_data: List[Dict[str, Any]] = []
        tables: List[Dict[str, Any]] = []
        headers: List[str] = []
        text_blocks: List[str] = []
        
        is_scanned_doc = False
        ocr_engine_used = None

        if ext == ".pdf":
            try:
                pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
                total_pages = pdf_doc.page_count
                
                # Check for native text across pages
                native_text_pages = 0
                for page_idx in range(total_pages):
                    p = pdf_doc.load_page(page_idx)
                    t = p.get_text("text")
                    if t and len(t.strip()) > 30:
                        native_text_pages += 1

                is_digital_native = (native_text_pages > 0 and (native_text_pages >= total_pages // 2 or total_pages == 1))

                if is_digital_native:
                    logger.info(f"Document '{filename}' is digital native ({native_text_pages}/{total_pages} text pages). Bypassing OCR.")
                    ocr_engine_used = "PyMuPDF (Native Digital Bypass)"
                    
                    for page_idx in range(total_pages):
                        page = pdf_doc.load_page(page_idx)
                        text = page.get_text("text")
                        lines = [l.strip() for l in text.split("\n") if l.strip()]
                        
                        # Extract word bounding boxes for detailed evidence tracking
                        words = page.get_text("words")  # (x0, y0, x1, y1, word, block_no, line_no, word_no)
                        word_tokens = []
                        for w in words:
                            word_tokens.append({
                                "text": w[4],
                                "bbox": [round(w[0], 2), round(w[1], 2), round(w[2], 2), round(w[3], 2)],
                                "confidence": 1.0,
                                "line_number": w[6],
                                "block_number": w[5]
                            })

                        for l in lines:
                            if any(h_kw in l.upper() for h_kw in ["BALANCE SHEET", "PROFIT AND LOSS", "INCOME STATEMENT", "CASH FLOW", "INVOICE"]):
                                if l not in headers:
                                    headers.append(l)

                        pages_data.append({
                            "page_number": page_idx + 1,
                            "full_text": text,
                            "lines": lines,
                            "tokens": word_tokens,
                            "is_scanned": False
                        })
                        text_blocks.extend(lines)
                else:
                    is_scanned_doc = True
                    logger.info(f"Document '{filename}' is scanned/image-heavy. Performing structure extraction...")
                    
                    for page_idx in range(total_pages):
                        page = pdf_doc.load_page(page_idx)
                        pix = page.get_pixmap(dpi=130)
                        img_bytes = pix.tobytes("png")
                        
                        scanned_page, engine = cls._ocr_image_bytes_unified(img_bytes, page_number=page_idx + 1)
                        scanned_page["image_bytes"] = img_bytes
                        scanned_page["mime_type"] = "image/png"
                        ocr_engine_used = engine
                        pages_data.append(scanned_page)
                        text_blocks.extend(scanned_page.get("lines", []))
                        
                        for l in scanned_page.get("lines", []):
                            if any(h_kw in l.upper() for h_kw in ["BALANCE SHEET", "PROFIT AND LOSS", "INCOME STATEMENT", "CASH FLOW", "INVOICE"]):
                                if l not in headers:
                                    headers.append(l)
                
                pdf_doc.close()

            except Exception as e:
                logger.error(f"Error parsing PDF with PyMuPDF/OCR: {e}", exc_info=True)
                raise e
        else:
            # Image file (.jpg, .jpeg, .png)
            is_scanned_doc = True
            mime_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
            
            # Transpose according to EXIF orientation (fixes mobile phone photos taken sideways/upside-down)
            try:
                from PIL import Image, ImageOps
                raw_im = Image.open(io.BytesIO(file_bytes))
                transposed_im = ImageOps.exif_transpose(raw_im)
                if transposed_im is not None:
                    out_buf = io.BytesIO()
                    fmt = "PNG" if ext == ".png" else "JPEG"
                    transposed_im.save(out_buf, format=fmt, quality=95)
                    file_bytes = out_buf.getvalue()
            except Exception as trans_err:
                logger.warning(f"EXIF transpose handling warning for {filename}: {trans_err}")

            scanned_page, engine = cls._ocr_image_bytes_unified(file_bytes, page_number=1)
            scanned_page["image_bytes"] = file_bytes
            scanned_page["mime_type"] = mime_type
            ocr_engine_used = engine
            pages_data.append(scanned_page)
            text_blocks.extend(scanned_page.get("lines", []))
            
            for l in scanned_page.get("lines", []):
                if any(h_kw in l.upper() for h_kw in ["BALANCE SHEET", "PROFIT AND LOSS", "INCOME STATEMENT", "CASH FLOW", "INVOICE"]):
                    if l not in headers:
                        headers.append(l)

        latency_ms = round((time.time() - start_time) * 1000, 2)
        
        result = {
            "hash": doc_hash,
            "filename": filename,
            "is_scanned": is_scanned_doc,
            "pages_data": pages_data,
            "headers": headers,
            "text_blocks": text_blocks,
            "tables": tables,
            "provenance": {
                "hash": doc_hash,
                "ocr_engine": ocr_engine_used or "Native PyMuPDF",
                "is_scanned": is_scanned_doc,
                "parsing_latency_ms": latency_ms,
                "from_cache": False
            }
        }

        cls._cache[doc_hash] = result
        import gc
        gc.collect()
        return result

    @classmethod
    def preprocess_image(cls, image: Image.Image) -> Image.Image:
        try:
            from PIL import ImageEnhance, ImageOps
            gray = ImageOps.grayscale(image)
            enhancer = ImageEnhance.Contrast(gray)
            enhanced = enhancer.enhance(1.8)
            resample_filter = getattr(Image.Resampling, 'LANCZOS', getattr(Image, 'LANCZOS', 3))
            if enhanced.width < 1200 or enhanced.height < 1200:
                enhanced = enhanced.resize((enhanced.width * 2, enhanced.height * 2), resample_filter)
            return enhanced.convert("RGB")
        except Exception as err:
            logger.warning(f"Image preprocessing warning: {err}")
            return image

    @classmethod
    def _ocr_image_bytes_unified(cls, img_bytes: bytes, page_number: int) -> Tuple[Dict[str, Any], str]:
        lines: List[str] = []
        tokens: List[Dict[str, Any]] = []
        engine_used = "None"
        
        try:
            from PIL import ImageOps
            raw_image = Image.open(io.BytesIO(img_bytes))
            image = ImageOps.exif_transpose(raw_image)
            if image is None:
                image = raw_image
            image = image.convert("RGB")
            
            max_dim = 1600
            if image.width > max_dim or image.height > max_dim:
                scale = max_dim / float(max(image.width, image.height))
                new_w = int(image.width * scale)
                new_h = int(image.height * scale)
                resample_filter = getattr(Image.Resampling, 'LANCZOS', getattr(Image, 'LANCZOS', 3))
                image = image.resize((new_w, new_h), resample_filter)
            import numpy as np
            img_np = np.array(image)
        except Exception as img_err:
            logger.warning(f"Failed to decode image bytes for OCR on page {page_number}: {img_err}")
            image = None
            img_np = None

        if img_np is not None:
            easy_reader = cls.get_easyocr_reader()
            if easy_reader:
                try:
                    results = easy_reader.readtext(img_np, detail=1)
                    avg_conf = sum(float(item[2]) for item in results if len(item) > 2) / float(max(1, len(results)))
                    
                    # Preprocessing retry if OCR returned almost nothing (fewer than 5 tokens)
                    if len(results) < 5 and image is not None:
                        logger.info(f"Image page {page_number} OCR returned very few tokens ({len(results)}). Applying contrast & upscale preprocessing...")
                        prep_img = cls.preprocess_image(image)
                        prep_np = np.array(prep_img)
                        prep_results = easy_reader.readtext(prep_np, detail=1)
                        if len(prep_results) > len(results):
                            results = prep_results
                            logger.info(f"Preprocessing improved token count from {len(results)} to {len(prep_results)}")

                    for item in results:
                        if len(item) >= 2:
                            bbox_raw = item[0]
                            text = str(item[1]).strip()
                            conf = float(item[2]) if len(item) > 2 else 1.0
                            if text:
                                lines.append(text)
                                tokens.append({
                                    "text": text,
                                    "bbox": bbox_raw,
                                    "confidence": round(conf, 4)
                                })
                    if lines:
                        engine_used = "EasyOCR (CUDA GPU Primary)"
                except Exception as e_err:
                    logger.warning(f"EasyOCR failed on page {page_number}: {e_err}. Falling back to PaddleOCR.")

            # 2. Secondary Fallback: PaddleOCR
            if not lines:
                paddle = cls.get_paddle_ocr()
                if paddle:
                    try:
                        ocr_res = paddle.ocr(img_np)
                        if ocr_res and len(ocr_res) > 0 and ocr_res[0]:
                            for line_item in ocr_res[0]:
                                if line_item and len(line_item) >= 2:
                                    bbox_raw = line_item[0]
                                    text_info = line_item[1]
                                    if text_info and len(text_info) >= 1:
                                        txt = str(text_info[0]).strip()
                                        conf = float(text_info[1]) if len(text_info) > 1 else 1.0
                                        if txt:
                                            lines.append(txt)
                                            tokens.append({
                                                "text": txt,
                                                "bbox": bbox_raw,
                                                "confidence": round(conf, 4)
                                            })
                            if lines:
                                engine_used = "PaddleOCR (Fallback)"
                    except Exception as p_err:
                        logger.error(f"PaddleOCR fallback failed on page {page_number}: {p_err}")

        full_text = "\n".join(lines)
        return ({
            "page_number": page_number,
            "full_text": full_text,
            "lines": lines,
            "tokens": tokens,
            "is_scanned": True
        }, engine_used)
