import re
import json
from typing import Dict, Any, List, Optional
from app.core.config import settings
from app.core.logging import logger

class ExtractionService:
    @classmethod
    def extract_structured_data(cls, pages_data: List[Dict[str, Any]], document_type: str) -> Dict[str, Any]:
        logger.info(f"Extracting structured data for document_type: {document_type}")
        
        full_text = "\n\n".join([f"--- PAGE {p['page_number']} ---\n" + p["full_text"] for p in pages_data])
        
        def enrich_if_needed(extracted_dict: Dict[str, Any]) -> Dict[str, Any]:
            if document_type in ["balance_sheet", "profit_and_loss", "cash_flow_statement"]:
                rule_parsed = cls._extract_rule_based(full_text, document_type, pages_data)
                rule_periods = rule_parsed.get("periods", [])
                periods = extracted_dict.get("periods", [])
                
                if not periods or len(rule_periods) > len(periods):
                    extracted_dict["periods"] = rule_periods
                    if not extracted_dict.get("reporting_date") and rule_parsed.get("reporting_date"):
                        extracted_dict["reporting_date"] = rule_parsed.get("reporting_date")
                else:
                    for r_p, p_p in zip(rule_periods, periods):
                        for k, v in r_p.items():
                            if isinstance(v, (int, float)) and v is not None:
                                current_v = p_p.get(k)
                                if current_v is None or (isinstance(current_v, (int, float)) and current_v <= 20 and v > 100):
                                    p_p[k] = v
                    if not extracted_dict.get("company_name") or "STATEMENT" in str(extracted_dict.get("company_name")).upper():
                        if rule_parsed.get("company_name"):
                            extracted_dict["company_name"] = rule_parsed.get("company_name")
            elif document_type == "invoice":
                all_lines = [l.strip() for page in pages_data for l in page.get("lines", []) if l.strip()] if pages_data else full_text.split("\n")
                rule_parsed = cls._parse_rule_invoice(all_lines, full_text, pages_data)
                for k in ["vendor_name", "customer_name", "invoice_number", "invoice_date", "due_date", "po_number", "payment_terms", "payment_method", "phone", "email", "address", "tax_id", "receipt_number", "cashier", "subtotal", "tax_amount", "discount", "total_amount", "cash_paid", "change_amount"]:
                    if not extracted_dict.get(k) and rule_parsed.get(k):
                        extracted_dict[k] = rule_parsed.get(k)
                if not extracted_dict.get("line_items") and rule_parsed.get("line_items"):
                    extracted_dict["line_items"] = rule_parsed.get("line_items")
            has_visual = any(p.get("image_bytes") for p in pages_data) or any(p.get("is_scanned") for p in pages_data)
            return cls._verify_grounding_pass(extracted_dict, full_text, has_visual_input=has_visual)

        # 1. PRIMARY: Try Gemini API via google.genai
        if settings.GEMINI_API_KEY and len(settings.GEMINI_API_KEY.strip()) > 10:
            try:
                extracted = cls._extract_with_gemini(full_text, document_type, pages_data)
                if extracted:
                    logger.info("Structured extraction successfully executed via Gemini API.")
                    return enrich_if_needed(extracted)
            except Exception as e:
                logger.warning(f"Gemini API extraction failed: {e}")

        # 2. SECONDARY: Try Grok (Groq) API if Gemini fails
        if (settings.GROK_API_KEY and len(settings.GROK_API_KEY.strip()) > 10) or (settings.GROQ_API_KEY and len(settings.GROQ_API_KEY.strip()) > 10):
            try:
                extracted = cls._extract_with_grok(full_text, document_type, pages_data)
                if extracted:
                    logger.info("Structured extraction successfully executed via Grok API.")
                    return enrich_if_needed(extracted)
            except Exception as e:
                logger.warning(f"Grok API extraction failed: {e}")

        # 3. TERTIARY: Deterministic, rule-based zero-hallucination parser fallback
        logger.info("Executing deterministic rule-based AI parser fallback.")
        return cls._extract_rule_based(full_text, document_type, pages_data)

    @classmethod
    def _extract_with_gemini(cls, full_text: str, document_type: str, pages_data: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        prompt = cls._build_extraction_prompt(full_text, document_type)
        
        contents = []
        for p in pages_data:
            if p.get("image_bytes"):
                mime = p.get("mime_type", "image/jpeg")
                contents.append(types.Part.from_bytes(data=p["image_bytes"], mime_type=mime))
        
        if contents:
            contents.append(prompt)
        else:
            contents = prompt

        config = types.GenerateContentConfig(
            response_mime_type="application/json"
        )
        
        models_to_try = ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-3.7-flash"]
        for m_name in models_to_try:
            try:
                logger.info(f"Attempting Gemini extraction with model: {m_name}")
                response = client.models.generate_content(
                    model=m_name,
                    contents=contents,
                    config=config
                )
                if response and response.text:
                    cleaned_json = cls._clean_json_response(response.text)
                    data = json.loads(cleaned_json)
                    human_name = f"Gemini {m_name.replace('gemini-', '').replace('-preview', '').title()}"
                    data["_metadata"] = {"model_used": human_name}
                    return data
            except Exception as m_err:
                logger.warning(f"Gemini model {m_name} failed: {m_err}. Trying next model...")
        
        return None

    @classmethod
    def _extract_with_grok(cls, full_text: str, document_type: str, pages_data: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        import urllib.request
        api_key = (settings.GROK_API_KEY or settings.GROQ_API_KEY or "").strip()
        if not api_key:
            return None

        prompt = cls._build_extraction_prompt(full_text, document_type)
        models_to_try = ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b", "groq/compound"]

        for m_name in models_to_try:
            try:
                logger.info(f"Attempting Grok/Groq extraction with model: {m_name}")
                payload = {
                    "model": m_name,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an expert financial document intelligence AI. Extract structured data in strict accordance with the prompt schema. Return valid JSON only without markdown formatting."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1
                }
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                }
                req = urllib.request.Request(
                    "https://api.groq.com/openai/v1/chat/completions",
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers
                )
                with urllib.request.urlopen(req, timeout=25) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    content = resp_data["choices"][0]["message"]["content"]
                    if content:
                        cleaned = cls._clean_json_response(content)
                        parsed = json.loads(cleaned)
                        parsed["_metadata"] = {"model_used": f"Grok ({m_name.split('/')[-1]})"}
                        return parsed
            except Exception as m_err:
                logger.warning(f"Grok model {m_name} failed: {m_err}. Trying next model...")

        return None

    @classmethod
    def _build_extraction_prompt(cls, full_text: str, document_type: str) -> str:
        text_content = full_text.strip() if full_text and full_text.strip() else "(Document image/page attached. Extract all fields, metadata, and tables directly from the visual document content.)"
        prompt_base = f"""
You are a financial document intelligence AI system.
Document Type: {document_type}
Document Content:
{text_content}

CRITICAL ANTI-HALLUCINATION & COMPLETE TABLE EXTRACTION RULES:
1. Extract ALL visible document metadata (document_title, company_name/vendor_name, customer_name, reporting_date/invoice_date, currency, scale/unit).
2. Distinguish document_title (e.g. "TAX INVOICE", "BALANCE SHEET") from vendor_name/company_name (e.g. "Shankar Enterprises").
3. Extract ALL visible table rows, line items, schedule numbers, section totals, and amounts present in the document.
4. For invoices, extract EVERY item in the table into line_items: description, quantity, unit_price, line_total.
5. If a field or line item is NOT present in the document, return NULL for that field. Do NOT invent, assume, infer, or calculate missing values.
6. Parse negative values in parentheses like '(5,000)' or '(500.00)' as negative numbers like -5000.0 or -500.0.
7. Return all financial and quantity values strictly as numbers (float/int), NOT formatted strings with currency symbols or commas.
8. Provide field-level evidence dictionary containing source_text and page_number.
"""
        if document_type == "invoice":
            prompt_base += """
Return strict JSON structure:
{
  "document_title": "INVOICE",
  "invoice_number": string or null,
  "invoice_date": string or null,
  "vendor_name": string or null,
  "customer_name": string or null,
  "currency": string or null,
  "unit": string or null,
  "subtotal": float or null,
  "tax_amount": float or null,
  "discount": float or null,
  "total_amount": float or null,
  "cash_paid": float or null,
  "change_amount": float or null,
  "line_items": [
    {
      "description": string or null,
      "quantity": float or null,
      "unit_price": float or null,
      "discount_percentage": float or null,
      "line_total": float or null
    }
  ],
  "evidence": {
    "invoice_number": {"source_text": string, "page_number": 1},
    "total_amount": {"source_text": string, "page_number": 1}
  }
}
"""
        elif document_type == "balance_sheet":
            prompt_base += """
Return strict JSON structure with comparative periods and complete table rows:
{
  "document_title": string or null,
  "company_name": string or null,
  "reporting_date": string or null,
  "currency": string or null,
  "unit": string or null,
  "periods": [
    {
      "period_name": string (e.g. "March 31, 2026" or "2026"),
      "total_assets": float or null,
      "total_liabilities": float or null,
      "total_equity": float or null,
      "total_capital_and_liabilities": float or null,
      "asset_line_items": [
        {
          "line_item_name": string,
          "schedule": string or null,
          "amount": float or null,
          "values": {"period_name": float}
        }
      ],
      "liability_equity_line_items": [
        {
          "line_item_name": string,
          "schedule": string or null,
          "amount": float or null,
          "values": {"period_name": float}
        }
      ]
    }
  ],
  "additional_disclosures": [
    {
      "label": string,
      "schedule": string or null,
      "amount": float or null,
      "values": {"period_name": float}
    }
  ],
  "evidence": {}
}
"""
        elif document_type == "profit_and_loss":
            prompt_base += """
Return strict JSON structure with comparative periods and complete table rows:
{
  "document_title": string or null,
  "company_name": string or null,
  "reporting_date": string or null,
  "currency": string or null,
  "unit": string or null,
  "periods": [
    {
      "period_name": string,
      "revenue": float or null,
      "cost_of_sales": float or null,
      "gross_profit": float or null,
      "interest_earned": float or null,
      "other_income": float or null,
      "total_income": float or null,
      "operating_expenses": float or null,
      "interest_expended": float or null,
      "provisions_and_contingencies": float or null,
      "total_expenditure": float or null,
      "operating_profit": float or null,
      "tax": float or null,
      "net_profit_before_minority_interest": float or null,
      "minority_interest": float or null,
      "net_profit": float or null,
      "current_profit": float or null,
      "brought_forward_profit": float or null,
      "total_available_for_appropriation": float or null,
      "line_items": [
        {
          "line_item_name": string,
          "schedule": string or null,
          "amount": float or null,
          "values": {"period_name": float}
        }
      ]
    }
  ],
  "additional_disclosures": [],
  "evidence": {}
}
"""
        elif document_type == "cash_flow_statement":
            prompt_base += """
Return strict JSON structure with comparative periods and complete table rows:
{
  "document_title": string or null,
  "company_name": string or null,
  "reporting_date": string or null,
  "currency": string or null,
  "unit": string or null,
  "periods": [
    {
      "period_name": string,
      "operating_cash_flow": float or null,
      "investing_cash_flow": float or null,
      "financing_cash_flow": float or null,
      "fx_translation_adjustment": float or null,
      "net_change_in_cash": float or null,
      "opening_cash": float or null,
      "cash_acquired_adjustments": float or null,
      "closing_cash": float or null,
      "line_items": [
        {
          "line_item_name": string,
          "schedule": string or null,
          "amount": float or null,
          "values": {"period_name": float}
        }
      ]
    }
  ],
  "additional_disclosures": [],
  "evidence": {}
}
"""
        return prompt_base

    @classmethod
    def _clean_json_response(cls, text: str) -> str:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    @classmethod
    def _extract_rule_based(cls, full_text: str, document_type: str, pages_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        lines = [line.strip() for page in pages_data for line in page.get("lines", []) if line.strip()]

        if document_type == "invoice":
            return cls._parse_rule_invoice(lines, full_text, pages_data)
        elif document_type == "balance_sheet":
            return cls._parse_rule_balance_sheet(lines, full_text, pages_data)
        elif document_type == "profit_and_loss":
            return cls._parse_rule_profit_and_loss(lines, full_text, pages_data)
        elif document_type == "cash_flow_statement":
            return cls._parse_rule_cash_flow(lines, full_text, pages_data)

        return {"_metadata": {"model_used": "Rule-based Engine"}}

    @classmethod
    def _parse_amount(cls, val_str: str) -> Optional[float]:
        if not val_str:
            return None
        val_str = val_str.strip()
        is_negative = False
        if (val_str.startswith("(") and val_str.endswith(")")) or val_str.startswith("-"):
            is_negative = True
            val_str = val_str.strip("()-")

        val_str = val_str.strip(",. ")
        if not val_str:
            return None

        if "." in val_str and "," in val_str:
            if re.search(r"\,\d{2}$", val_str):
                val_str = val_str.replace(".", "").replace(",", ".")
            else:
                val_str = val_str.replace(",", "")
        elif val_str.count(".") > 1:
            val_str = val_str.replace(".", "")
        elif val_str.count(",") > 1:
            val_str = val_str.replace(",", "")
        else:
            if "," in val_str:
                if re.search(r"\,\d{2}$", val_str):
                    val_str = val_str.replace(",", ".")
                else:
                    val_str = val_str.replace(",", "")

        val_cleaned = re.sub(r"[^\d.]", "", val_str)
        if not val_cleaned:
            return None
        try:
            val = float(val_cleaned)
            return -val if is_negative else val
        except ValueError:
            return None

    @classmethod
    def _verify_grounding_pass(cls, data: Dict[str, Any], full_text: str, has_visual_input: bool = False) -> Dict[str, Any]:
        """
        Anti-Hallucination Evidence Grounding Verification.
        Verifies that every extracted non-null numeric value is present in the source text evidence or mathematically derived.
        When visual inputs (images) are provided to a multimodal model, visual extractions are preserved.
        """
        if not data or not isinstance(data, dict):
            return data

        # Normalize string numeric values to float
        for field in ["subtotal", "tax_amount", "discount", "total_amount", "cash_paid", "change_amount"]:
            if field in data and data[field] is not None and isinstance(data[field], str):
                data[field] = cls._parse_amount(data[field])

        if "line_items" in data and isinstance(data["line_items"], list):
            for item in data["line_items"]:
                if isinstance(item, dict):
                    for num_k in ["quantity", "unit_price", "discount_percentage", "line_total"]:
                        if num_k in item and item[num_k] is not None and isinstance(item[num_k], str):
                            item[num_k] = cls._parse_amount(item[num_k])

        # If source text is empty or minimal (e.g. pure image processed visually without native text stream),
        # preserve valid visual extractions
        if not full_text or len(full_text.strip()) < 10:
            return data

        # Include evidence text snippets for complete grounding context
        evidence_snippets = []
        if isinstance(data.get("evidence"), dict):
            for ev_k, ev_v in data["evidence"].items():
                if isinstance(ev_v, dict) and "source_text" in ev_v:
                    evidence_snippets.append(str(ev_v["source_text"]))
                elif isinstance(ev_v, str):
                    evidence_snippets.append(ev_v)

        combined_text = full_text + " " + " ".join(evidence_snippets)
        full_text_clean = combined_text.replace(",", "").replace(" ", "").replace("₹", "").replace("$", "").replace("€", "").replace("£", "")
        full_text_digits = re.sub(r"[^\d.]", " ", combined_text)
        
        def is_numeric_in_text(val: Optional[float]) -> bool:
            if val is None:
                return True
            abs_val = abs(val)
            val_str = f"{val:.2f}"
            abs_val_str = f"{abs_val:.2f}"
            val_int_str = str(int(round(val)))
            abs_val_int_str = str(int(round(abs_val)))
            val_raw_str = str(val)
            abs_val_raw_str = str(abs_val)

            return (
                (val_str in full_text_clean) or (abs_val_str in full_text_clean) or
                (val_int_str in full_text_clean) or (abs_val_int_str in full_text_clean) or
                (val_raw_str in full_text_clean) or (abs_val_raw_str in full_text_clean) or
                (f"{val:,.2f}" in combined_text) or (f"{abs_val:,.2f}" in combined_text) or
                (abs_val_str in full_text_digits) or (abs_val_int_str in full_text_digits)
            )

        # Check line items sum for mathematical grounding
        line_items = data.get("line_items", [])
        line_totals_sum = sum(
            (item.get("line_total") or 0.0)
            for item in line_items
            if isinstance(item, dict) and item.get("line_total") is not None
        ) if line_items else None

        # Check top-level numeric fields
        for field in ["subtotal", "tax_amount", "discount", "total_amount", "cash_paid", "change_amount"]:
            if field in data and data[field] is not None:
                is_grounded = is_numeric_in_text(data[field])
                if not is_grounded:
                    # Mathematical grounding checks
                    if line_totals_sum is not None:
                        if field in ["subtotal", "total_amount"] and abs(data[field] - line_totals_sum) <= 2.0:
                            is_grounded = True
                        elif field == "total_amount" and data.get("subtotal") and data.get("tax_amount"):
                            if abs(data[field] - (data["subtotal"] + data["tax_amount"])) <= 2.0:
                                is_grounded = True
                    if field == "tax_amount" and data.get("subtotal") and data.get("total_amount"):
                        if abs((data["subtotal"] + data[field]) - data["total_amount"]) <= 2.0:
                            is_grounded = True
                    if has_visual_input and data[field] is not None and data[field] > 0:
                        is_grounded = True

                if not is_grounded:
                    logger.warning(f"Grounding check failed for field '{field}' ({data[field]}). Resetting to None.")
                    data[field] = None

        # Check line_items
        if "line_items" in data and isinstance(data["line_items"], list):
            for item in data["line_items"]:
                if isinstance(item, dict):
                    if not has_visual_input:
                        for num_k in ["quantity", "unit_price", "line_total"]:
                            if num_k in item and item[num_k] is not None:
                                if not is_numeric_in_text(item[num_k]):
                                    item[num_k] = None

        # Check financial statement periods
        if "periods" in data and isinstance(data["periods"], list):
            for p in data["periods"]:
                if isinstance(p, dict):
                    for k, v in list(p.items()):
                        if isinstance(v, (int, float)) and v is not None and k != "period_name":
                            if not is_numeric_in_text(v) and not has_visual_input:
                                logger.warning(f"Grounding check failed for period field '{k}' ({v}). Resetting to None.")
                                p[k] = None

        return data

    @classmethod
    def _parse_rule_invoice(cls, lines: List[str], full_text: str, pages_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        inv_no = None
        inv_date = None
        due_date = None
        po_number = None
        payment_terms = None
        payment_method = None
        vendor = None
        customer = None
        phone = None
        email = None
        address = None
        tax_id = None
        receipt_number = None
        cashier = None
        currency = None
        unit = None
        subtotal = None
        tax_amount = None
        discount = None
        total_amount = None
        cash_paid = None
        change_amount = None
        line_items = []
        evidence = {}

        # Currency detection (check MYR/RM before generic $)
        if "RM" in full_text or "RH" in full_text or "MYR" in full_text:
            currency = "MYR"
        elif "$" in full_text:
            currency = "USD"
        elif "EUR" in full_text or "€" in full_text:
            currency = "EUR"
        elif "INR" in full_text or "₹" in full_text:
            currency = "INR"
        elif "GBP" in full_text or "£" in full_text:
            currency = "GBP"

        # Email & Phone extraction across document
        m_email = re.search(r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})", full_text)
        if m_email:
            email = m_email.group(1)

        m_phone = re.search(r"(?:tel|phone|ph|mobile)[:\.\s;]*\s*(\+?[0-9\-\(\)\s]{7,15})", full_text, re.IGNORECASE)
        if m_phone:
            phone = m_phone.group(1).strip()

        m_tax = re.search(r"(?:tax\s*id|vat\s*#|vat\s*reg|gstin|tin\s*#)[:\.\s]*\s*([A-Za-z0-9\-_]+)", full_text, re.IGNORECASE)
        if m_tax:
            tax_id = m_tax.group(1).strip()

        # Helper: extract the last amount-like number from a line
        def _extract_last_amount(text: str):
            """Extract the rightmost currency amount from a line."""
            # Try currency-prefixed amounts first: $157.48, $12.48
            currency_amounts = re.findall(r"[\$€₹£]\s*([0-9,]+\.?[0-9]*)", text)
            if currency_amounts:
                return cls._parse_amount(currency_amounts[-1])
            # Try standalone amounts (last number on line)
            amounts = re.findall(r"(?<![A-Za-z])([0-9,]+\.[0-9]{2})(?![0-9])", text)
            if amounts:
                return cls._parse_amount(amounts[-1])
            # Try comma-decimal format: 138,90
            comma_amounts = re.findall(r"(?<![0-9])([0-9]+,[0-9]{2})(?![0-9])", text)
            if comma_amounts:
                return cls._parse_amount(comma_amounts[-1])
            return None

        # Helper: look ahead for amounts on subsequent lines (for multi-line totals)
        def _lookahead_amount(start_idx: int, max_look: int = 3):
            """Look ahead in lines for the first standalone amount."""
            for j in range(start_idx + 1, min(start_idx + 1 + max_look, len(lines))):
                nxt = lines[j].strip()
                # Skip currency labels like "RH", "RM", "SR"
                if re.match(r"^(RH|RM|SR|MYR|USD|\$|£|€|₹)f?$", nxt, re.IGNORECASE):
                    continue
                amt = _extract_last_amount(nxt)
                if amt is not None and amt > 0:
                    return amt
            return None

        for idx, line in enumerate(lines):
            l_lower = line.lower().strip()
            if not l_lower:
                continue
            
            # Invoice Number — expanded patterns (including slashes like SCI/25-26/3331)
            if not inv_no:
                m = re.search(r"(?:invoice\s*#|inv\s*#|invoice\s*(?:number|no\.?)|inv\s*no\.?|receipt\s*#|order\s*#|check\s*#|ref\s*#|cb\s*#)[:\.\s;]*\s*([A-Za-z0-9\-_/]+)", line, re.IGNORECASE)
                if m:
                    inv_no = m.group(1)
                    evidence["invoice_number"] = {"source_text": line, "page_number": 1}

            if not receipt_number:
                m = re.search(r"(?:receipt\s*#|receipt\s*no\.?|ticket\s*#|trans\s*#)[:\.\s;]*\s*([A-Za-z0-9\-_/]+)", line, re.IGNORECASE)
                if m:
                    receipt_number = m.group(1)

            if not po_number:
                m = re.search(r"(?:po\s*#|p\.o\.\s*#|po\s*number|purchase\s*order)[:\.\s;]*\s*([A-Za-z0-9\-_/]+)", line, re.IGNORECASE)
                if m:
                    po_number = m.group(1)

            if not due_date:
                m = re.search(r"(?:due\s*date|payment\s*due|due)[:\s]*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}[/\.][0-9]{1,2}[/\.][0-9]{2,4}|[A-Za-z]+\s+[0-9]{1,2},\s*[0-9]{4})", line, re.IGNORECASE)
                if m:
                    due_date = m.group(1)

            if not payment_method:
                if any(pm in l_lower for pm in ["visa", "mastercard", "amex", "debit", "credit card"]):
                    m_pm = re.search(r"\b(visa|mastercard|amex|debit|credit card)\b", l_lower)
                    if m_pm:
                        payment_method = m_pm.group(1).upper()
                # Handle "CASH" only if it's explicitly a payment line, not "cash flow" etc
                elif re.match(r"^cash[\.\s:]*$", l_lower) or l_lower.startswith("cash paid") or l_lower.startswith("cash:"):
                    payment_method = "CASH"

            if not cashier:
                m_c = re.search(r"(?:cashier|server|operator|clerk)[:\.\s;]*\s*([A-Za-z0-9][A-Za-z0-9\s\-_]*)", line, re.IGNORECASE)
                if m_c:
                    val = m_c.group(1).strip()
                    if len(val) >= 1 and len(val) <= 30:
                        cashier = val

            # Invoice Date — expanded patterns including "Date of issue", standalone date
            if not inv_date:
                # Labeled date: "date:", "inv date:", "date of issue:", "dated:"
                m = re.search(r"(?:date\s*(?:of\s*issue)?|inv\s*date|invoice\s*date|dated)[:\s]*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}[/\.][0-9]{1,2}[/\.][0-9]{2,4}|[A-Za-z]+\s+[0-9]{1,2},\s*[0-9]{4}|[0-9]{1,2}-[A-Za-z]{3}-[0-9]{2,4})", line, re.IGNORECASE)
                if m:
                    inv_date = m.group(1)
                    evidence["invoice_date"] = {"source_text": line, "page_number": 1}
                # Standalone date line (receipts): pure date like "19/10/2018" or "07/03/2013"
                elif not inv_date and re.match(r"^[0-9]{1,2}[/\.][0-9]{1,2}[/\.][0-9]{2,4}\s*$", line.strip()):
                    inv_date = line.strip()
                    evidence["invoice_date"] = {"source_text": line, "page_number": 1}
                # Date with time: "17/01/2018 8.09.53"
                elif not inv_date:
                    m2 = re.match(r"^([0-9]{1,2}[/\.][0-9]{1,2}[/\.][0-9]{2,4})\s+[0-9]", line.strip())
                    if m2:
                        inv_date = m2.group(1)
                        evidence["invoice_date"] = {"source_text": line, "page_number": 1}

            # Vendor / Customer — handle labeled lines (look at same line and next line)
            if not vendor:
                if "seller:" in l_lower or "vendor:" in l_lower or "from:" in l_lower or "billed by:" in l_lower or "store:" in l_lower:
                    parts = line.split(":")
                    val = parts[1].strip() if len(parts) > 1 else ""
                    if val and len(val) > 1 and val.lower() not in ["", "seller", "vendor", "from"]:
                        vendor = val
                    elif idx + 1 < len(lines):
                        next_line = lines[idx + 1].strip()
                        if next_line and re.search(r"[A-Za-z]{2,}", next_line):
                            vendor = next_line
                elif idx < 3 and any(w in line for w in ["Enterprises", "Limited", "Ltd", "Corp", "Inc", "Pvt", "Co."]):
                    vendor = line.strip()

            if not customer:
                if any(k in l_lower for k in ["client:", "customer:", "bill to:", "billed to:", "ship to:", "buyer (bill to)", "buyer:"]):
                    parts = line.split(":") if ":" in line else [line, ""]
                    val = parts[1].strip() if len(parts) > 1 else ""
                    if val and len(val) > 1:
                        customer = val
                    elif idx + 1 < len(lines):
                        next_line = lines[idx + 1].strip()
                        if next_line and re.search(r"[A-Za-z]{2,}", next_line):
                            customer = next_line

            # Subtotal, Tax, Total, Cash, Change — improved extraction
            if "subtotal" in l_lower or "sub total" in l_lower or "sub-total" in l_lower:
                amt = _extract_last_amount(line)
                if amt is not None:
                    subtotal = amt
                    evidence["subtotal"] = {"source_text": line, "page_number": 1}
                elif amt is None:
                    amt = _lookahead_amount(idx)
                    if amt is not None:
                        subtotal = amt
                        evidence["subtotal"] = {"source_text": line, "page_number": 1}
            elif ("tax" in l_lower or "gst" in l_lower or "vat" in l_lower) and tax_amount is None:
                # GUARD: Skip lines that are Tax IDs, GST reg numbers, or VAT registration
                if any(skip in l_lower for skip in ["tax id", "tax_id", "gst reg", "vat reg", "gstin", "tin #", "tin:", "iban"]):
                    pass  # Not a tax amount line
                elif "net amt" in l_lower or "net worth" in l_lower:
                    pass  # GST summary header, not tax amount
                elif l_lower in ["gst", "vat", "tax"]:
                    pass  # Standalone label, not tax amount
                else:
                    amt = _extract_last_amount(line)
                    if amt is not None and amt < 1000000:  # Sanity: tax amounts shouldn't be millions
                        tax_amount = amt
                        evidence["tax_amount"] = {"source_text": line, "page_number": 1}
            elif "discount" in l_lower or "disc" in l_lower:
                amt = _extract_last_amount(line)
                if amt is not None:
                    discount = amt
            elif total_amount is None and (
                "total amount" in l_lower or "grand total" in l_lower or
                "total due" in l_lower or "total inclusive" in l_lower or
                "total amt" in l_lower or "total akt" in l_lower or
                (l_lower.strip() == "total") or
                re.match(r"^total[:\s]", l_lower) or
                l_lower.endswith(" total")
            ):
                # Exclude subtotal, tax, line total, qty lines
                if not any(k in l_lower for k in ["subtotal", "sub total", "tax", "line", "#total qty", "total qty", "net"]):
                    amt = _extract_last_amount(line)
                    if amt is not None:
                        total_amount = amt
                        evidence["total_amount"] = {"source_text": line, "page_number": 1}
                    else:
                        # Look ahead for the amount (multi-line total)
                        amt = _lookahead_amount(idx)
                        if amt is not None:
                            total_amount = amt
                            evidence["total_amount"] = {"source_text": line, "page_number": 1}
            elif "cash" in l_lower and cash_paid is None:
                if not any(k in l_lower for k in ["total", "subtotal", "tax", "change", "cashier", "cash flow"]):
                    amt = _extract_last_amount(line)
                    if amt is not None:
                        cash_paid = amt
                    else:
                        amt = _lookahead_amount(idx)
                        if amt is not None:
                            cash_paid = amt
            elif ("change" in l_lower or "chaxge" in l_lower) and change_amount is None:
                if "exchange" not in l_lower:
                    amt = _extract_last_amount(line)
                    if amt is not None:
                        change_amount = amt
                    else:
                        amt = _lookahead_amount(idx)
                        if amt is not None:
                            change_amount = amt

            # Table line item patterns
            skip_kw = ["subtotal", "sub total", "total", "tax", "vat", "gst", "grand total", "cash",
                        "paid", "change", "balance", "due", "amount", "discount", "disc",
                        "invoice", "receipt", "date", "card", "visa", "mastercard", "amex",
                        "check", "thank you", "store", "tel", "fax", "phone", "page", "table",
                        "server", "cashier", "order", "seller", "client", "vendor", "customer",
                        "items", "summary", "iban", "rounding", "roundirg", "shipping", "handling",
                        "net worth", "net amt", "gross", "type:", "description", "quantity",
                        "price", "qty", "welcome", "goods sold", "please come", "terms",
                        "condition", "interest", "payment", "bill to", "ship to"]
            if not any(kw in l_lower for kw in skip_kw):
                # Pattern A: 4-column: DESC QTY PRICE TOTAL
                m_item4 = re.search(r"^([A-Za-z0-9\s\-_&#]+?)\s+([0-9]+(?:\.[0-9]+)?)\s+[\$€₹£]?\s*([0-9,]+\.[0-9]{2})\s+[\$€₹£]?\s*([0-9,]+\.[0-9]{2})$", line)
                if m_item4:
                    desc, qty_str, price_str, total_str = m_item4.groups()
                    line_items.append({
                        "description": desc.strip(),
                        "quantity": float(qty_str),
                        "unit_price": cls._parse_amount(price_str),
                        "line_total": cls._parse_amount(total_str)
                    })
                    continue

                # Pattern B: QTY x DESC TOTAL (or QTY DESC TOTAL)
                m_item_qty_desc = re.search(r"^([0-9]+(?:\.[0-9]+)?)\s*(?:x|\*|\s)\s+([A-Za-z0-9\s\-_&#]{2,})\s+[\$€₹£]?\s*([0-9,]+\.[0-9]{2})$", line, re.IGNORECASE)
                if m_item_qty_desc:
                    qty_str, desc, total_str = m_item_qty_desc.groups()
                    q = float(qty_str)
                    tot = cls._parse_amount(total_str)
                    u_price = round(tot / q, 2) if (tot is not None and q > 0) else None
                    line_items.append({
                        "description": desc.strip(),
                        "quantity": q,
                        "unit_price": u_price,
                        "line_total": tot
                    })
                    continue

                # Pattern C: 2-column receipt line item: DESC TOTAL
                m_item2 = re.search(r"^([A-Za-z0-9\s\-_&#]{2,})\s+[\$€₹£]?\s*([0-9,]+\.[0-9]{2})\s*(?:[A-Z])?$", line)
                if m_item2:
                    desc, total_str = m_item2.groups()
                    tot = cls._parse_amount(total_str)
                    if tot is not None and tot > 0:
                        line_items.append({
                            "description": desc.strip(),
                            "quantity": None,
                            "unit_price": None,
                            "line_total": tot
                        })
                        continue

        # Vendor name clean fallback — improved skip list
        if not vendor and len(lines) > 0:
            vendor_skip = ["invoice", "date", "bill to", "tax", "subtotal", "total", "page",
                          "receipt", "welcome", "tel", "fax", "items", "seller:", "client:",
                          "customer:", "vendor:", "description", "quantity", "price",
                          "iban", "no.", "no "]
            for l in lines[:6]:
                l_clean = l.strip()
                l_lower_c = l_clean.lower()
                if re.search(r"[A-Za-z]{3,}", l_clean) and not any(k in l_lower_c for k in vendor_skip):
                    if len(l_clean) > 2 and l_clean.upper() not in ["INVOICE", "RECEIPT", "TAX INVOICE", "TAXINVOICE", "TAXINVQICE"]:
                        vendor = l_clean
                        break

        # Customer fallback: if we have "Seller:" in lines, look for "Client:" pattern
        # Also try to find customer from address block following "Client:" or "Bill To:"
        if not customer:
            for idx2, line2 in enumerate(lines):
                l2_lower = line2.lower().strip()
                if l2_lower.startswith("client") and idx2 + 1 < len(lines):
                    next_l = lines[idx2 + 1].strip()
                    if next_l and re.search(r"[A-Za-z]{2,}", next_l) and len(next_l) > 2:
                        customer = next_l
                        break

        return {
            "document_title": "INVOICE",
            "invoice_number": inv_no,
            "invoice_date": inv_date,
            "due_date": due_date,
            "po_number": po_number,
            "payment_terms": payment_terms,
            "payment_method": payment_method,
            "vendor_name": vendor,
            "customer_name": customer,
            "phone": phone,
            "email": email,
            "address": address,
            "tax_id": tax_id,
            "receipt_number": receipt_number,
            "cashier": cashier,
            "currency": currency,
            "unit": unit,
            "subtotal": subtotal,
            "tax_amount": tax_amount,
            "discount": discount,
            "total_amount": total_amount,
            "cash_paid": cash_paid,
            "change_amount": change_amount,
            "line_items": line_items,
            "evidence": evidence,
            "_metadata": {"model_used": "Rule-based Engine"}
        }

    @classmethod
    def _parse_rule_balance_sheet(cls, lines: List[str], full_text: str, pages_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        doc_title = None
        company_name = None
        currency = None
        unit = None
        reporting_date = None

        if "crore" in full_text.lower():
            unit = "crore"
            currency = "INR"
        elif "thousand" in full_text.lower():
            unit = "thousands"
        elif "million" in full_text.lower():
            unit = "millions"

        if "$" in full_text:
            currency = "USD"
        elif "₹" in full_text or "INR" in full_text:
            currency = "INR"
        elif "EUR" in full_text or "€" in full_text:
            currency = "EUR"

        # Document Title
        for l in lines[:10]:
            l_str = l.strip()
            if "BALANCE SHEET" in l_str.upper() and not doc_title:
                doc_title = l_str
                break

        # Company Name
        corp_indicators = ["LIMITED", "LTD", "INC", "CORP", "CORPORATION", "HOLDINGS", "PLC", "BANK"]
        for l in lines[:15]:
            l_str = l.strip()
            l_upper = l_str.upper()
            if any(ind in l_upper for ind in corp_indicators) and "BALANCE SHEET" not in l_upper and "REPORT" not in l_upper and "REGISTRATION" not in l_upper:
                company_name = l_str
                break
        
        if not company_name:
            for l in reversed(lines[-25:]):
                l_str = l.strip()
                l_upper = l_str.upper()
                if any(ind in l_upper for ind in corp_indicators) and "INTEGRATED" not in l_upper and "REPORT" not in l_upper and "AUDIT" not in l_upper:
                    company_name = l_str
                    break

        # Comparative Periods
        year_matches = sorted(list(set(re.findall(r"\b(20[0-9]{2}|19[0-9]{2})\b", full_text))), reverse=True)
        period_names = []
        if year_matches:
            for y in year_matches:
                if y not in period_names:
                    period_names.append(y)
        else:
            period_names = ["Current Year"]

        full_period_names = []
        for yr in period_names:
            m = re.search(rf"([A-Za-z]+\s+[0-9]{1,2},\s*{yr})", full_text, re.IGNORECASE)
            if m:
                full_period_names.append(m.group(1))
            else:
                full_period_names.append(yr)

        if full_period_names:
            reporting_date = full_period_names[0]

        periods_map = {}
        for p_name in full_period_names:
            periods_map[p_name] = {
                "period_name": p_name,
                "total_assets": None,
                "total_liabilities": None,
                "total_equity": None,
                "total_capital_and_liabilities": None,
                "asset_line_items": [],
                "liability_equity_line_items": []
            }

        additional_disclosures = []
        evidence = {}

        current_section = "LIABILITIES"
        i = 0
        num_lines = len(lines)

        while i < num_lines:
            line = lines[i].strip()
            l_upper = line.upper()

            if "CAPITAL AND LIABILITIES" in l_upper or "LIABILITIES AND EQUITY" in l_upper or "LIABILITIES & EQUITY" in l_upper:
                current_section = "LIABILITIES"
                i += 1
                continue
            elif (l_upper == "ASSETS" or "ASSETS" in l_upper) and "TOTAL" not in l_upper and "FIXED" not in l_upper and "OTHER" not in l_upper:
                current_section = "ASSETS"
                i += 1
                continue

            amounts_on_line = [cls._parse_amount(a) for a in re.findall(r"\(?[0-9,]+(?:\.[0-9]+)?\)?", line) if cls._parse_amount(a) is not None]

            # Check for Total line
            if l_upper == "TOTAL" or l_upper.startswith("TOTAL "):
                total_amounts = list(amounts_on_line)
                j = i + 1
                while j < min(i + 4, num_lines) and len(total_amounts) < len(full_period_names):
                    nxt_line = lines[j].strip()
                    n_amts = [cls._parse_amount(a) for a in re.findall(r"\(?[0-9,]+(?:\.[0-9]+)?\)?", nxt_line) if cls._parse_amount(a) is not None]
                    if n_amts:
                        total_amounts.extend(n_amts)
                    j += 1

                if total_amounts:
                    if "TOTAL LIABILITIES" in l_upper and "EQUITY" not in l_upper and "CAPITAL" not in l_upper:
                        for idx, yr in enumerate(full_period_names):
                            if idx < len(total_amounts):
                                periods_map[yr]["total_liabilities"] = total_amounts[idx]
                                evidence[f"total_liabilities_{yr}"] = {"source_text": line, "page_number": 1}
                    elif "TOTAL EQUITY" in l_upper:
                        for idx, yr in enumerate(full_period_names):
                            if idx < len(total_amounts):
                                periods_map[yr]["total_equity"] = total_amounts[idx]
                                evidence[f"total_equity_{yr}"] = {"source_text": line, "page_number": 1}
                    elif current_section == "LIABILITIES" or "CAPITAL" in l_upper or "LIABILITIES" in l_upper:
                        for idx, yr in enumerate(full_period_names):
                            if idx < len(total_amounts):
                                periods_map[yr]["total_capital_and_liabilities"] = total_amounts[idx]
                                evidence[f"total_capital_and_liabilities_{yr}"] = {"source_text": line, "page_number": 1}
                        current_section = "ASSETS"
                    elif current_section == "ASSETS" or "ASSETS" in l_upper:
                        for idx, yr in enumerate(full_period_names):
                            if idx < len(total_amounts):
                                periods_map[yr]["total_assets"] = total_amounts[idx]
                                evidence[f"total_assets_{yr}"] = {"source_text": line, "page_number": 1}
                        current_section = "DISCLOSURES"

                i = max(i + 1, j if 'j' in locals() else i + 1)
                continue

            # Table line items
            is_label = bool(re.search(r"[A-Za-z]{3,}", line)) and not any(k in l_upper for k in ["SCHEDULE", "MARCH", "DECEMBER", "AS AT", "IN CRORE", "BALANCES SHEET", "CONSOLIDATED"])
            
            if is_label:
                item_label = line
                schedule_num = None
                extracted_amounts = list(amounts_on_line)
                
                j = i + 1
                while j < min(i + 5, num_lines):
                    next_line = lines[j].strip()
                    n_upper = next_line.upper()

                    if any(h in n_upper for h in ["CAPITAL AND LIABILITIES", "ASSETS"]) and not re.search(r"[0-9,]+(?:\.[0-9]+)?", next_line):
                        break
                    if n_upper == "TOTAL" or n_upper.startswith("TOTAL "):
                        break
                    
                    m_sch = re.match(r"^([0-9]{1,2}\s*(?:\([0-9]+\))?|[0-9]{1,2}[A-Z]?)$", next_line)
                    if m_sch and not schedule_num and not cls._parse_amount(next_line):
                        schedule_num = m_sch.group(1)
                        j += 1
                        continue

                    n_amts = [cls._parse_amount(a) for a in re.findall(r"\(?[0-9,]+(?:\.[0-9]+)?\)?", next_line) if cls._parse_amount(a) is not None]
                    if n_amts:
                        extracted_amounts.extend(n_amts)
                        if len(extracted_amounts) >= len(full_period_names):
                            break

                    if re.search(r"[A-Za-z]{4,}", next_line) and not n_amts:
                        break
                    
                    j += 1

                if extracted_amounts:
                    if "CONTINGENT" in item_label.upper() or "BILLS FOR COLLECTION" in item_label.upper() or current_section == "DISCLOSURES":
                        disc_obj = {
                            "label": item_label,
                            "schedule": schedule_num,
                            "amount": extracted_amounts[0] if extracted_amounts else None,
                            "values": {yr: extracted_amounts[idx] for idx, yr in enumerate(full_period_names) if idx < len(extracted_amounts)}
                        }
                        additional_disclosures.append(disc_obj)
                    else:
                        item_obj = {
                            "line_item_name": item_label,
                            "schedule": schedule_num,
                            "amount": extracted_amounts[0] if extracted_amounts else None,
                            "values": {yr: extracted_amounts[idx] for idx, yr in enumerate(full_period_names) if idx < len(extracted_amounts)}
                        }
                        
                        if current_section == "LIABILITIES":
                            for idx, yr in enumerate(full_period_names):
                                if idx < len(extracted_amounts):
                                    periods_map[yr]["liability_equity_line_items"].append({
                                        "line_item_name": item_label,
                                        "schedule": schedule_num,
                                        "amount": extracted_amounts[idx],
                                        "values": item_obj["values"]
                                    })
                        elif current_section == "ASSETS":
                            for idx, yr in enumerate(full_period_names):
                                if idx < len(extracted_amounts):
                                    periods_map[yr]["asset_line_items"].append({
                                        "line_item_name": item_label,
                                        "schedule": schedule_num,
                                        "amount": extracted_amounts[idx],
                                        "values": item_obj["values"]
                                    })

                    i = j - 1

            i += 1

        return {
            "document_title": doc_title or "CONSOLIDATED BALANCE SHEET",
            "company_name": company_name or None,
            "reporting_date": reporting_date,
            "currency": currency,
            "unit": unit,
            "periods": list(periods_map.values()),
            "additional_disclosures": additional_disclosures,
            "evidence": evidence,
            "_metadata": {"model_used": "Rule-based Engine"}
        }

    @classmethod
    def _parse_rule_profit_and_loss(cls, lines: List[str], full_text: str, pages_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        company_name = None
        doc_title = None
        corp_indicators = ["LIMITED", "LTD", "INC", "CORP", "CORPORATION", "HOLDINGS", "PLC", "BANK"]
        for l in lines[:10]:
            l_str = l.strip()
            l_upper = l_str.upper()
            if "PROFIT" in l_upper and "LOSS" in l_upper and not doc_title:
                doc_title = l_str
            elif any(ind in l_upper for ind in corp_indicators) and not company_name and "STATEMENT" not in l_upper and "PROFIT" not in l_upper:
                company_name = l_str

        if not company_name and len(lines) > 0:
            company_name = lines[0]

        years = re.findall(r"\b(20[0-9]{2}|19[0-9]{2})\b", full_text)
        years = sorted(list(set(years)), reverse=True)
        if not years:
            years = ["Current Year"]

        periods_map: Dict[str, Dict[str, Any]] = {}
        for yr in years:
            periods_map[yr] = {
                "period_name": yr,
                "revenue": None,
                "cost_of_sales": None,
                "gross_profit": None,
                "interest_earned": None,
                "other_income": None,
                "total_income": None,
                "operating_expenses": None,
                "interest_expended": None,
                "provisions_and_contingencies": None,
                "total_expenditure": None,
                "operating_profit": None,
                "tax": None,
                "net_profit_before_minority_interest": None,
                "minority_interest": None,
                "net_profit": None,
                "current_profit": None,
                "brought_forward_profit": None,
                "total_available_for_appropriation": None,
                "line_items": []
            }

        evidence = {}
        num_lines = len(lines)
        current_section = "INCOME"
        i = 0

        def get_amounts(start_idx):
            found = []
            line = lines[start_idx]
            raw_tokens = re.findall(r"\(?[0-9][0-9,.]*\)?", line)
            nums = [cls._parse_amount(t) for t in raw_tokens if cls._parse_amount(t) is not None]
            if nums:
                found.extend(nums)
            if len(found) >= len(years):
                return found, start_idx
            
            j = start_idx + 1
            while j < min(start_idx + 4, num_lines):
                nxt = lines[j]
                nxt_lower = nxt.lower()
                if any(kw in nxt_lower for kw in ["income", "expenditure", "profit", "appropriations", "interest", "total", "revenue", "operating"]):
                    if not re.search(r"^[0-9,.() ]+$", nxt):
                        break
                nxt_tokens = re.findall(r"\(?[0-9][0-9,.]*\)?", nxt)
                nxt_nums = [cls._parse_amount(t) for t in nxt_tokens if cls._parse_amount(t) is not None]
                if nxt_nums:
                    found.extend(nxt_nums)
                    if len(found) >= len(years):
                        return found, j
                j += 1
            return found, j - 1

        while i < num_lines:
            line = lines[i].strip()
            l_lower = line.lower()
            l_upper = line.upper()

            if l_upper in ["INCOME", "EXPENDITURE", "PROFIT", "APPROPRIATIONS"]:
                current_section = l_upper
                i += 1
                continue

            field_key = None
            if "interest earned" in l_lower or "interest income" in l_lower:
                field_key = "interest_earned"
            elif "other income" in l_lower:
                field_key = "other_income"
            elif ("total income" in l_lower) or (current_section == "INCOME" and l_lower == "total"):
                field_key = "total_income"
                current_section = "EXPENDITURE"
            elif "interest expended" in l_lower or "interest expense" in l_lower:
                field_key = "interest_expended"
            elif "operating expenses" in l_lower or "opex" in l_lower:
                field_key = "operating_expenses"
            elif "provisions" in l_lower or "contingencies" in l_lower:
                field_key = "provisions_and_contingencies"
            elif "total expenditure" in l_lower or "total expenses" in l_lower or (current_section == "EXPENDITURE" and l_lower == "total"):
                field_key = "total_expenditure"
                current_section = "PROFIT"
            elif "net profit for the year" in l_lower or "net profit" in l_lower or "profit for the year" in l_lower:
                if "attributable" not in l_lower:
                    field_key = "net_profit"
            elif "minority interest" in l_lower:
                field_key = "minority_interest"
            elif "attributable to the group" in l_lower or "consolidated profit for the year" in l_lower:
                field_key = "net_profit_before_minority_interest"
            elif "brought forward" in l_lower:
                field_key = "brought_forward_profit"
            elif "total available for appropriation" in l_lower or (current_section == "APPROPRIATIONS" and l_lower == "total"):
                field_key = "total_available_for_appropriation"
            elif ("revenue" in l_lower or "sales" in l_lower) and "cost" not in l_lower:
                field_key = "revenue"
            elif "cost of sales" in l_lower or "cogs" in l_lower:
                field_key = "cost_of_sales"
            elif "gross profit" in l_lower:
                field_key = "gross_profit"
            elif "operating profit" in l_lower:
                field_key = "operating_profit"

            if field_key:
                parsed_amounts, last_j = get_amounts(i)
                if len(parsed_amounts) > len(years):
                    parsed_amounts = [a for a in parsed_amounts if a > 30 or a < 0 or "." in str(a)]
                for idx, yr in enumerate(years):
                    if idx < len(parsed_amounts):
                        periods_map[yr][field_key] = parsed_amounts[idx]
                        evidence[f"{field_key}_{yr}"] = {"source_text": line, "page_number": 1}
                i = max(i, last_j)

            i += 1

        return {
            "document_title": doc_title or "CONSOLIDATED STATEMENT OF PROFIT AND LOSS",
            "company_name": company_name or None,
            "reporting_date": years[0] if years else None,
            "currency": "USD" if "$" in full_text else "INR",
            "unit": "crore" if "crore" in full_text.lower() else None,
            "periods": list(periods_map.values()),
            "additional_disclosures": [],
            "evidence": evidence,
            "_metadata": {"model_used": "Rule-based Engine"}
        }

    @classmethod
    def _parse_rule_cash_flow(cls, lines: List[str], full_text: str, pages_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        company_name = None
        doc_title = None
        corp_indicators = ["LIMITED", "LTD", "INC", "CORP", "CORPORATION", "HOLDINGS", "PLC", "BANK"]
        for l in lines[:10]:
            l_str = l.strip()
            l_upper = l_str.upper()
            if "CASH FLOW" in l_upper and not doc_title:
                doc_title = l_str
            elif any(ind in l_upper for ind in corp_indicators) and not company_name and "STATEMENT" not in l_upper:
                company_name = l_str

        if not company_name and len(lines) > 0:
            company_name = lines[0]

        years = re.findall(r"\b(20[0-9]{2}|19[0-9]{2})\b", full_text)
        years = sorted(list(set(years)), reverse=True)
        if not years:
            years = ["Current Year"]

        periods_map: Dict[str, Dict[str, Any]] = {}
        for yr in years:
            periods_map[yr] = {
                "period_name": yr,
                "operating_cash_flow": None,
                "investing_cash_flow": None,
                "financing_cash_flow": None,
                "fx_translation_adjustment": None,
                "net_change_in_cash": None,
                "opening_cash": None,
                "cash_acquired_adjustments": None,
                "closing_cash": None,
                "line_items": []
            }

        evidence = {}
        num_lines = len(lines)
        i = 0

        def get_amounts(start_idx):
            found = []
            line = lines[start_idx]
            raw_tokens = re.findall(r"\(?[0-9][0-9,.]*\)?", line)
            nums = [cls._parse_amount(t) for t in raw_tokens if cls._parse_amount(t) is not None]
            if nums:
                found.extend(nums)
            if len(found) >= len(years):
                return found, start_idx
            
            j = start_idx + 1
            while j < min(start_idx + 4, num_lines):
                nxt = lines[j]
                nxt_lower = nxt.lower()
                if any(kw in nxt_lower for kw in ["cash flow", "activities", "net increase", "opening", "closing"]):
                    if not re.search(r"^[0-9,.() ]+$", nxt):
                        break
                nxt_tokens = re.findall(r"\(?[0-9][0-9,.]*\)?", nxt)
                nxt_nums = [cls._parse_amount(t) for t in nxt_tokens if cls._parse_amount(t) is not None]
                if nxt_nums:
                    found.extend(nxt_nums)
                    if len(found) >= len(years):
                        return found, j
                j += 1
            return found, j - 1

        while i < num_lines:
            line = lines[i].strip()
            l_lower = line.lower()

            field_key = None
            if "operating activities" in l_lower or "operating cash flow" in l_lower:
                field_key = "operating_cash_flow"
            elif "investing activities" in l_lower or "investing cash flow" in l_lower:
                field_key = "investing_cash_flow"
            elif "financing activities" in l_lower or "financing cash flow" in l_lower:
                field_key = "financing_cash_flow"
            elif "foreign exchange" in l_lower or "fx adjustment" in l_lower or "translation adjustment" in l_lower:
                field_key = "fx_translation_adjustment"
            elif "net increase" in l_lower or "net change in cash" in l_lower or "net cash flow" in l_lower:
                field_key = "net_change_in_cash"
            elif "opening cash" in l_lower or "cash at beginning" in l_lower or "cash at start" in l_lower:
                field_key = "opening_cash"
            elif "amalgamation" in l_lower or "cash acquired" in l_lower:
                field_key = "cash_acquired_adjustments"
            elif "closing cash" in l_lower or "cash at end" in l_lower:
                field_key = "closing_cash"

            if field_key:
                parsed_amounts, last_j = get_amounts(i)
                if len(parsed_amounts) > len(years):
                    parsed_amounts = [a for a in parsed_amounts if a > 30 or a < 0 or "." in str(a)]
                for idx, yr in enumerate(years):
                    if idx < len(parsed_amounts):
                        periods_map[yr][field_key] = parsed_amounts[idx]
                        evidence[f"{field_key}_{yr}"] = {"source_text": line, "page_number": 1}
                i = max(i, last_j)
            else:
                # Dynamic Activity Line Item candidate check
                is_label = bool(re.search(r"[A-Za-z]{4,}", line)) and not any(k in l_lower for k in ["cash flow", "statement", "march", "december", "crore", "page", "annual report"])
                if is_label:
                    parsed_amounts, last_j = get_amounts(i)
                    if parsed_amounts:
                        item_obj = {
                            "line_item_name": line,
                            "schedule": None,
                            "amount": parsed_amounts[0],
                            "values": {yr: parsed_amounts[idx] for idx, yr in enumerate(years) if idx < len(parsed_amounts)}
                        }
                        for yr in years:
                            periods_map[yr]["line_items"].append(item_obj)
                        i = max(i, last_j)

            i += 1

        return {
            "document_title": doc_title or "CONSOLIDATED CASH FLOW STATEMENT",
            "company_name": company_name or None,
            "reporting_date": years[0] if years else None,
            "currency": "USD" if "$" in full_text else "INR",
            "unit": "crore" if "crore" in full_text.lower() else None,
            "periods": list(periods_map.values()),
            "additional_disclosures": [],
            "evidence": evidence,
            "_metadata": {"model_used": "Rule-based Engine"}
        }
