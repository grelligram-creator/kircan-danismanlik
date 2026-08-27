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
Görevin: kullanıcı tarafından doldurulması GEREKEN boş yerleri (blank alanları) tespit etmek.

## Boş alan işaretleri (ipuçları)
- Alt çizgi: `___`, `____________`
- Boş noktalar: `...............`, `……`
- Boş köşeli parantez: `[      ]`, `[YAZINIZ]`, `[TARIH]`
- Bir etiket + iki noktadan sonra boş: `Ada / Parsel:`, `Sahibi:`, `Tarih:` (etiketten sonraki içerik eksik veya sadece boşluk)
- Boş tablo hücreleri (bir başlık satırından sonraki boş satırlar)
- Görsel/fotoğraf slotları: "Genel Görünüm Fotoğrafı:", "Uydu Görüntüsü:", "Cephe Fotoğrafı:"

## Dinamik Tablolar (ÖNEMLİ)
Bir tablonun **DİNAMİK** (kullanıcının satır sayısını belirleyeceği) olduğunu şu ipuçlarından anlarsın:
- Tablo başlığı: "Emsaller", "Karşılaştırma Emsalleri", "Kira Emsalleri", "Malzeme Listesi", "Ürünler", "Bileşenler"
- Tablo başlık satırından sonra tek bir örnek satır (boş veya "1", "2", "3" gibi numaralı) veya birkaç boş satır
- Kullanıcının kaç satır ekleyeceği başlangıçta belli değil

Bu durumda alanı ŞU FORMATTA çıkar:
{
  "key": "emsaller",  // veya "kira_emsalleri" vs.
  "label": "Emsaller",
  "type": "table",
  "node_id": "t2",  // tablonun index'i (tX)
  "header_row_index": 0,
  "template_row_index": 1,  // döngü şablonu olacak satır
  "columns": [
    {"key": "adres", "label": "Adres", "type": "text"},
    {"key": "alan", "label": "Alan (m²)", "type": "number"},
    {"key": "fiyat", "label": "Birim Fiyat (TL/m²)", "type": "number"}
  ],
  "hint": "Emsalleri sırayla girin; kaç adet olacağını da sorun"
}

Statik alanlar için ŞU JSON şemasını kullan:
{
  "key": "snake_case_kisa_anahtar",
  "label": "Türkçe insan okunabilir etiket",
  "type": "text|number|date|textarea|image",  // image → görsel yükleme
  "node_id": "hangi paragraf/hücreden geliyor (p3 veya t0.r2.c1)",
  "replace_text": "değiştirilecek metin varsa (örn '____'). Yoksa null.",
  "append_after_label": "'Ada:' gibi etiketten sonraya eklenecekse etiket metni. Yoksa null.",
  "hint": "AI'ın bu alanı sorarken kullanacağı Türkçe ipucu"
}

Kurallar:
- Anahtar isimleri (key) benzersiz, snake_case.
- Aynı içerikten fazla alan çıkarma.
- Zaten dolu görünen yerlere dokunma.
- Sadece geçerli JSON döndür, açıklama yok.
- Belirsizsen ATLA — asla uydurma.

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
        ftype = f.get("type") if f.get("type") in ("text", "number", "date", "textarea", "image", "table") else "text"
        entry: Dict[str, Any] = {
            "key": key,
            "label": str(f.get("label", key)).strip() or key,
            "type": ftype,
            "node_id": f.get("node_id"),
            "replace_text": f.get("replace_text"),
            "append_after_label": f.get("append_after_label"),
            "hint": f.get("hint", ""),
        }
        if ftype == "table":
            # normalize table structure
            cols_raw = f.get("columns") or []
            cols: List[Dict[str, Any]] = []
            col_keys_seen = set()
            for c in cols_raw:
                ck = re.sub(r"[^a-z0-9_]", "_", str(c.get("key", "")).lower()).strip("_")
                if not ck or ck in col_keys_seen:
                    continue
                col_keys_seen.add(ck)
                cols.append({
                    "key": ck,
                    "label": str(c.get("label", ck)).strip() or ck,
                    "type": c.get("type") if c.get("type") in ("text", "number", "date") else "text",
                })
            entry["columns"] = cols
            entry["header_row_index"] = int(f.get("header_row_index", 0) or 0)
            entry["template_row_index"] = int(f.get("template_row_index", 1) or 1)
        out.append(entry)
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


def _inject_dynamic_table(doc: DocumentObject, field: Dict[str, Any]) -> bool:
    """Inject docxtpl row-loop around the template row.

    docxtpl's tr-preprocessor REPLACES the entire `<w:tr>` containing `{%tr ...%}` with the raw
    Jinja tag. So the marker rows must be SEPARATE table rows dedicated to the tag, wrapping the
    actual template row that has `{{ r.col }}` placeholders.

    Layout after injection (header row omitted):
      [row: {%tr for r in key %}]     <- consumed
      [row: {{r.c1}} {{r.c2}} ...]    <- repeated per item
      [row: {%tr endfor %}]           <- consumed
    """
    from copy import deepcopy
    node_id = field.get("node_id", "")
    m = re.match(r"t(\d+)", node_id or "")
    if not m:
        return False
    ti = int(m.group(1))
    if ti >= len(doc.tables):
        return False
    table = doc.tables[ti]
    tri = int(field.get("template_row_index", 1) or 1)
    if tri >= len(table.rows):
        return False
    row = table.rows[tri]
    key = field["key"]
    cols = field.get("columns", [])
    if not cols:
        return False

    # 1. Put `{{ r.<col_key> }}` into each cell of the template row
    n_cells = len(row.cells)
    for ci, cell in enumerate(row.cells):
        col_key = cols[ci]["key"] if ci < len(cols) else None
        for p in list(cell.paragraphs)[1:]:
            p._element.getparent().remove(p._element)
        p = cell.paragraphs[0] if cell.paragraphs else cell.add_paragraph()
        for r in list(p.runs):
            r.text = ""
        if col_key:
            token = "{{r." + col_key + "}}"
            if p.runs:
                p.runs[0].text = token
            else:
                p.add_run(token)

    # 2. Insert new marker rows BEFORE and AFTER the template row by cloning the row's XML.
    row_xml = row._element
    tbl = row_xml.getparent()
    idx = list(tbl).index(row_xml)

    def _make_marker_row(tag_text: str):
        new_row = deepcopy(row_xml)
        # Clear all cell paragraph text, keep first cell's first paragraph, set marker there.
        # We iterate over w:tc elements.
        w_ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        tcs = new_row.findall(w_ns + "tc")
        for tc_i, tc in enumerate(tcs):
            # remove all <w:p> and re-add one empty
            for p in tc.findall(w_ns + "p"):
                tc.remove(p)
            new_p_xml = etree.SubElement(tc, w_ns + "p")
            if tc_i == 0:
                new_r = etree.SubElement(new_p_xml, w_ns + "r")
                new_t = etree.SubElement(new_r, w_ns + "t")
                new_t.text = tag_text
                new_t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        return new_row

    from lxml import etree
    for_row = _make_marker_row("{%tr for r in " + key + " %}")
    endfor_row = _make_marker_row("{%tr endfor %}")

    # Insert for_row before template row, endfor_row after
    tbl.insert(idx, for_row)
    tbl.insert(idx + 2, endfor_row)  # idx+1 is the template row after inserting for_row
    return True


def apply_placeholders(original_path: str, prepared_path: str, fields: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Modify docx by inserting Jinja `{{ key }}` tokens at the fields' node positions.
    Handles both scalar fields and dynamic table fields (`type: table`).
    Returns a summary of which fields were successfully applied."""
    doc = Document(original_path)
    applied: List[str] = []
    skipped: List[Dict[str, str]] = []

    for f in fields:
        key = f["key"]
        if f.get("type") == "table":
            ok = _inject_dynamic_table(doc, f)
            (applied if ok else skipped).append(key if ok else {"key": key, "reason": "table injection failed"})
            continue

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
                # empty cell: set token
                if not p.runs:
                    p.add_run(token)
                else:
                    p.runs[0].text = token
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

def render_docx(prepared_path: str, out_path: str, values: Dict[str, Any], image_paths: Dict[str, Any]) -> None:
    """Render the prepared docx with values + inline images.
    `image_paths` maps field key -> either a path string OR a dict {path, width_mm}.
    `values` may contain list-of-dicts under table keys, which docxtpl loops over via `{%tr for r in <key> %}...{%tr endfor %}` markers.
    """
    tpl = DocxTemplate(prepared_path)
    ctx: Dict[str, Any] = dict(values or {})
    # Strip UI-only meta rows (e.g. {"__widths__": {...}}) from any table lists — docxtpl loops would render them as blank rows otherwise.
    for k, v in list(ctx.items()):
        if isinstance(v, list):
            ctx[k] = [r for r in v if not (isinstance(r, dict) and r.get("__widths__"))]
    for k, meta in (image_paths or {}).items():
        try:
            if isinstance(meta, dict):
                path = meta.get("path")
                width_mm = float(meta.get("width_mm") or 80)
            else:
                path, width_mm = meta, 80.0
            if path:
                ctx[k] = InlineImage(tpl, path, width=Mm(width_mm))
            else:
                ctx[k] = ""
        except Exception:
            ctx[k] = ""
    tpl.render(ctx, autoescape=False)
    tpl.save(out_path)


def preview_html(prepared_path: str, values: Dict[str, Any], image_urls: Dict[str, Any], table_data: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> str:
    """Return an HTML preview with placeholders substituted for the current values.

    For dynamic tables (docxtpl `{%tr for r in <key> %}...{%tr endfor %}` markers), we replace the
    tokens with `<!-- LOOP:key -->` and then post-process the resulting HTML to expand rows.
    """
    html = docx_to_html(prepared_path)

    # Expand dynamic tables. `_inject_dynamic_table` writes THREE separate <tr>s:
    #   <tr>{%tr for r in key %}</tr>  <tr>{{r.col1}}...</tr>  <tr>{%tr endfor %}</tr>
    # Mammoth preserves that structure, so we look for the whole triple and expand the middle row.
    if table_data:
        for tkey, rows in table_data.items():
            triple_pattern = re.compile(
                r"<tr[^>]*>(?:(?!</tr>).)*?\{\%tr\s+for\s+r\s+in\s+" + re.escape(tkey) +
                r"\s+\%\}(?:(?!</tr>).)*?</tr>"
                r"(?P<template>\s*<tr[^>]*>(?:(?!</tr>).)*?</tr>)\s*"
                r"<tr[^>]*>(?:(?!</tr>).)*?\{\%tr\s+endfor\s+\%\}(?:(?!</tr>).)*?</tr>",
                re.DOTALL,
            )

            def build_rows(match):
                template_tr = match.group("template")
                out_rows: List[str] = []
                # Skip meta rows (e.g. {"__widths__": {...}}) — they're UI-only hints, not data.
                data_rows = [r for r in (rows or []) if not (isinstance(r, dict) and r.get("__widths__"))]
                for row_data in data_rows:
                    body = re.sub(
                        r"\{\{\s*r\.([a-zA-Z0-9_]+)\s*\}\}",
                        lambda m: str(row_data.get(m.group(1), "") or f'<span class="ph-empty">[{m.group(1)}]</span>'),
                        template_tr,
                    )
                    out_rows.append(body)
                if not out_rows:
                    body = re.sub(
                        r"\{\{\s*r\.([a-zA-Z0-9_]+)\s*\}\}",
                        lambda m: f'<span class="ph-empty">[{m.group(1)}]</span>',
                        template_tr,
                    )
                    out_rows.append(body.replace("<tr>", '<tr class="ph-empty-row">', 1))
                return "".join(out_rows)

            html = triple_pattern.sub(build_rows, html)

    # any leftover tr markers -> strip
    html = re.sub(r"\{\%tr\s+(for\s+r\s+in\s+[a-zA-Z0-9_]+|endfor)\s+\%\}", "", html)

    def repl(m):
        key = m.group(1).strip()
        img_meta = (image_urls or {}).get(key)
        if img_meta:
            if isinstance(img_meta, dict):
                url = img_meta.get("preview_url") or img_meta.get("url", "")
                width_mm = float(img_meta.get("width_mm") or 80)
            else:
                url, width_mm = img_meta, 80.0
            # Convert mm to px approx (1mm ≈ 3.78px)
            width_px = int(width_mm * 3.78)
            if url:
                return (f'<img data-key="{key}" src="{url}" '
                        f'style="width:{width_px}px;max-width:100%;height:auto;border:1px solid #e5e5e5;border-radius:4px;" />')
        val = values.get(key) if values else None
        if val is None or val == "":
            return f'<span class="ph-empty" data-key="{key}">[{key}]</span>'
        return f'<span class="ph-filled" data-key="{key}">{val}</span>'
    return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", repl, html)
