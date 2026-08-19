"""User template management: DOCX parsing, AI placeholder detection, Jinja injection, rendering.

Flow:
  1. User uploads a .docx.
  2. `extract_document_map` reads every paragraph + table cell and returns a structured map with
     stable node_ids (e.g. `p0.r1` or `t0.r2.c1`).
  3. `detect_placeholders_via_llm` sends this map + rules to Claude Sonnet 5. Claude returns a JSON list
     of fields (key, label, type, node_id, replace_text?, append_after_text?, insert_position).
  4. `apply_placeholders` writes Jinja `{{ key }}` tokens into the docx while preserving run formatting.
     The prepared docx is saved separately (original.docx + prepared.docx).
  5. `render_docx` runs docxtpl on the prepared docx with a context dict of values (+ InlineImage for
     image fields).
"""
from __future__ import annotations
import io
import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from docx import Document
from docx.document import Document as DocumentObject
from docx.table import _Cell
from docx.text.paragraph import Paragraph
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
import mammoth


# ---------------------------------------------------------------------------
# Document map extraction
# ---------------------------------------------------------------------------

def _paragraph_text(p: Paragraph) -> str:
    return "".join(r.text for r in p.runs)


def extract_document_map(docx_path: str) -> Dict[str, Any]:
    """Return a structural map of the document useful for LLM analysis."""
    doc = Document(docx_path)
    paragraphs: List[Dict[str, Any]] = []
    for i, p in enumerate(doc.paragraphs):
        text = _paragraph_text(p)
        paragraphs.append({
            "node_id": f"p{i}",
            "text": text,
            "style": p.style.name if p.style else "Normal",
        })

    tables: List[Dict[str, Any]] = []
    for ti, table in enumerate(doc.tables):
        rows_out: List[List[Dict[str, Any]]] = []
        for ri, row in enumerate(table.rows):
            row_cells = []
            for ci, cell in enumerate(row.cells):
                # join all paragraphs in the cell
                cell_text = "\n".join(_paragraph_text(p) for p in cell.paragraphs)
                row_cells.append({"node_id": f"t{ti}.r{ri}.c{ci}", "text": cell_text})
            rows_out.append(row_cells)
        tables.append({"table_index": ti, "rows": rows_out})

    return {"paragraphs": paragraphs, "tables": tables}


# ---------------------------------------------------------------------------
# LLM Placeholder detection
# ---------------------------------------------------------------------------

_DETECT_SYSTEM = """Sen bir Word şablonu analiz uzmanısın. Sana bir Türkçe .docx dosyasının yapılandırılmış içeriği verilecek.
Görevin: kullanıcı tarafından doldurulması GEREKEN boş yerleri (blank alanları) tespit etmek ve her biri için tek bir alan (field) tanımlamak.

## Boş alan işaretleri (ipuçları)
- Alt çizgi: `___`, `____________`
- Boş noktalar: `...............`, `……`
- Boş köşeli parantez: `[      ]`, `[YAZINIZ]`, `[TARIH]`
- Bir etiket + iki noktadan sonra boş: `Ada / Parsel:`, `Sahibi:`, `Tarih:` (etiketten sonraki içerik eksik veya sadece boşluk)
- Boş tablo hücreleri (bir başlık satırından sonraki boş satırlar)
- Görsel/fotoğraf slotları: "Genel Görünüm Fotoğrafı:", "Uydu Görüntüsü:", "Cephe Fotoğrafı:" gibi ifadelerin altındaki boş paragraflar

## Kural
Her tespit ettiğin alan için ŞU JSON şemasında bir nesne döndür (fields dizisi içinde):
{
  "key": "snake_case_kisa_anahtar",  // örn: "ada_parsel", "sahibi", "cephe_fotografi"
  "label": "Türkçe insan okunabilir etiket",  // örn: "Ada / Parsel No"
  "type": "text|number|date|textarea|image",  // image → görsel yükleme, textarea → uzun serbest metin
  "node_id": "hangi paragraf/hücreden geliyor (p3 veya t0.r2.c1)",
  "replace_text": "eğer paragrafta/hücrede birebir değiştirilecek metin varsa (örn '____' veya '[YAZINIZ]'). Yoksa null.",
  "append_after_label": "eğer 'Etiket: ' şeklinde bir etiketten sonra eklenmesi gerekiyorsa etiket metni (örn 'Ada / Parsel:'). Yoksa null.",
  "hint": "AI'a bu alanı kullanıcıya sorarken kullanacağı ipucu (Türkçe, kısa)"
}

Kurallar:
- Anahtar isimleri (key) benzersiz, snake_case, sadece a-z0-9_ olsun.
- Aynı içerikten fazla alan çıkarma.
- Zaten dolu görünen alanlara dokunma.
- Sadece geçerli JSON döndür, açıklama yok.
- Eğer belirsizsen bu alanı ATLA — asla uydurma.

Yalnızca şu formatı döndür:
{"fields": [ ... ]}
"""


async def detect_placeholders_via_llm(document_map: Dict[str, Any], llm_call) -> List[Dict[str, Any]]:
    """`llm_call` is an async function taking a prompt string and returning str.
    Returns list of detected field dicts."""
    payload = {
        "paragraphs": document_map["paragraphs"][:400],   # cap for token safety
        "tables": [
            {"table_index": t["table_index"], "rows": [[c for c in r] for r in t["rows"]]}
            for t in document_map["tables"]
        ][:20],
    }
    user_prompt = "Aşağıdaki dokümanı analiz et ve boş/doldurulacak alanları çıkar:\n\n" + json.dumps(payload, ensure_ascii=False)
    raw = await llm_call(_DETECT_SYSTEM, user_prompt)
    # extract JSON substring
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return []
    try:
        parsed = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    fields = parsed.get("fields", [])
    # normalize
    out: List[Dict[str, Any]] = []
    seen_keys = set()
    for f in fields:
        key = str(f.get("key", "")).strip()
        key = re.sub(r"[^a-z0-9_]", "_", key.lower())
        key = re.sub(r"_+", "_", key).strip("_")
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        out.append({
            "key": key,
            "label": str(f.get("label", key)).strip() or key,
            "type": f.get("type", "text") if f.get("type") in ("text", "number", "date", "textarea", "image") else "text",
            "node_id": f.get("node_id"),
            "replace_text": f.get("replace_text"),
            "append_after_label": f.get("append_after_label"),
            "hint": f.get("hint", ""),
        })
    return out


# ---------------------------------------------------------------------------
# Placeholder injection into DOCX (preserves run formatting)
# ---------------------------------------------------------------------------

def _replace_in_paragraph(p: Paragraph, target: str, replacement: str) -> bool:
    """Replace `target` text in the paragraph with `replacement`. Works even if the target
    spans multiple runs by collapsing all runs into the first run when needed."""
    joined = "".join(r.text for r in p.runs)
    if target not in joined:
        return False
    new_text = joined.replace(target, replacement)
    if not p.runs:
        p.add_run(new_text)
        return True
    # keep first run's formatting; empty out subsequent runs
    p.runs[0].text = new_text
    for r in p.runs[1:]:
        r.text = ""
    return True


def _append_after_label_in_paragraph(p: Paragraph, label: str, token: str) -> bool:
    """If paragraph text starts with (or contains) `label` followed by nothing useful, append token."""
    joined = "".join(r.text for r in p.runs)
    idx = joined.find(label)
    if idx == -1:
        return False
    after = joined[idx + len(label):]
    if after.strip() and not re.match(r"^[\s\._\-…\.]+$", after):
        # already filled, skip
        return False
    new_text = joined[:idx + len(label)] + " " + token
    if not p.runs:
        p.add_run(new_text)
        return True
    p.runs[0].text = new_text
    for r in p.runs[1:]:
        r.text = ""
    return True


def _find_paragraph_by_node(doc: DocumentObject, node_id: str) -> Optional[Tuple[Any, Optional[_Cell]]]:
    """Returns (paragraph, containing_cell) for the given node_id ("pN" or "tT.rR.cC[.pP]")."""
    if node_id.startswith("p"):
        try:
            idx = int(node_id[1:].split(".")[0])
        except ValueError:
            return None
        if 0 <= idx < len(doc.paragraphs):
            return doc.paragraphs[idx], None
        return None
    if node_id.startswith("t"):
        m = re.match(r"t(\d+)\.r(\d+)\.c(\d+)", node_id)
        if not m:
            return None
        ti, ri, ci = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if ti >= len(doc.tables):
            return None
        table = doc.tables[ti]
        if ri >= len(table.rows) or ci >= len(table.rows[ri].cells):
            return None
        cell = table.rows[ri].cells[ci]
        if not cell.paragraphs:
            return None
        return cell.paragraphs[0], cell
    return None


def apply_placeholders(original_path: str, prepared_path: str, fields: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Modify docx by inserting Jinja `{{ key }}` tokens at the fields' node positions.
    Returns a summary of which fields were successfully applied."""
    doc = Document(original_path)
    applied: List[str] = []
    skipped: List[Dict[str, str]] = []

    for f in fields:
        key = f["key"]
        token = f"{{{{ {key} }}}}"
        node_id = f.get("node_id")
        replace_text = f.get("replace_text")
        append_label = f.get("append_after_label")
        target = _find_paragraph_by_node(doc, node_id) if node_id else None

        ok = False
        if target:
            p, cell = target
            if replace_text and replace_text in "".join(r.text for r in p.runs):
                ok = _replace_in_paragraph(p, replace_text, token)
            elif append_label:
                ok = _append_after_label_in_paragraph(p, append_label, token)
            elif cell is not None and not "".join(r.text for r in p.runs).strip():
                # empty cell: just set token
                p.runs[0].text = token if p.runs else p.add_run(token).text
                if not p.runs:
                    p.add_run(token)
                ok = True

        if not ok and replace_text:
            # Fallback: search across all paragraphs/cells
            for p in doc.paragraphs:
                if _replace_in_paragraph(p, replace_text, token):
                    ok = True; break
            if not ok:
                for t in doc.tables:
                    for row in t.rows:
                        for cell in row.cells:
                            for p in cell.paragraphs:
                                if _replace_in_paragraph(p, replace_text, token):
                                    ok = True; break
                            if ok: break
                        if ok: break
                    if ok: break

        if ok:
            applied.append(key)
        else:
            skipped.append({"key": key, "reason": "node not found or already filled"})

    doc.save(prepared_path)
    return {"applied": applied, "skipped": skipped}


# ---------------------------------------------------------------------------
# HTML preview via mammoth
# ---------------------------------------------------------------------------

_STYLE_MAP = """
p[style-name='Title'] => h1.doc-title:fresh
p[style-name='Heading 1'] => h2.doc-h1:fresh
p[style-name='Heading 2'] => h3.doc-h2:fresh
p[style-name='Heading 3'] => h4.doc-h3:fresh
b => strong
i => em
u => u
""".strip()


def docx_to_html(docx_path: str) -> str:
    with open(docx_path, "rb") as f:
        result = mammoth.convert_to_html(f, style_map=_STYLE_MAP)
    return result.value


# ---------------------------------------------------------------------------
# Rendering (docxtpl)
# ---------------------------------------------------------------------------

def render_docx(prepared_path: str, out_path: str, values: Dict[str, Any], image_paths: Dict[str, str]) -> None:
    """Render the prepared docx with values + inline images.
    `image_paths` maps field key -> local file path to embed as InlineImage.
    """
    tpl = DocxTemplate(prepared_path)
    ctx = dict(values or {})
    for k, path in (image_paths or {}).items():
        try:
            ctx[k] = InlineImage(tpl, path, width=Mm(80))
        except Exception:
            ctx[k] = ""
    # Ensure all keys exist to avoid Jinja UndefinedError
    tpl.render(ctx, autoescape=False)
    tpl.save(out_path)


def preview_html(prepared_path: str, values: Dict[str, Any], image_urls: Dict[str, str]) -> str:
    """Return an HTML preview with placeholders substituted for the current values.
    Uses mammoth to convert to HTML first, then does a simple regex swap on the resulting HTML.
    """
    html = docx_to_html(prepared_path)
    def repl(m):
        key = m.group(1).strip()
        if key in image_urls and image_urls[key]:
            return f'<img data-key="{key}" src="{image_urls[key]}" style="max-width:100%;height:auto;border:1px solid #e5e5e5;border-radius:4px;" />'
        val = values.get(key) if values else None
        if val is None or val == "":
            return f'<span class="ph-empty" data-key="{key}">[{key}]</span>'
        return f'<span class="ph-filled" data-key="{key}">{val}</span>'
    return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", repl, html)
