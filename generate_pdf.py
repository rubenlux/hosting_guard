"""
generate_pdf.py - Exporta todo el codigo fuente de hosting_guard a un PDF.
Uso: python generate_pdf.py
Genera: hosting_guard_complete.pdf en el directorio raiz del proyecto.
"""

import os
import sys
import warnings
import unicodedata
warnings.filterwarnings("ignore")

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from datetime import datetime

# ── Config ─────────────────────────────────────────────────────────────────────

ROOT        = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(ROOT, "hosting_guard_complete.pdf")

SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", "dist", "build",
    ".venv", "venv", ".pytest_cache", ".mypy_cache", ".next",
    ".turbo", "coverage", ".cache",
}

CODE_EXTS = {
    ".py", ".jsx", ".js", ".ts", ".tsx",
    ".css", ".html", ".md", ".toml", ".yml", ".yaml",
    ".txt", ".sh", ".env", ".ini", ".cfg", ".sql",
}

# JSON solo si no es lock
SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
}

MAX_FILE_CHARS = 60_000

# ── Colors ────────────────────────────────────────────────────────────────────
C_BG_HEADER  = (10,  10,  14)
C_GREEN      = (0,   220, 120)
C_BG_FILE    = (22,  22,  30)
C_BG_CODE    = (14,  14,  18)
C_FG_CODE    = (175, 210, 175)
C_FG_LINENUM = (70,  70,  90)
C_FG_COMMENT = (95,  140, 95)
C_FG_KEYWORD = (120, 180, 255)
C_PAGE_NUM   = (80,  80,  80)
C_WHITE      = (220, 220, 230)
C_GRAY       = (140, 140, 150)


def to_latin1(text):
    """
    Convierte texto a latin-1 reemplazando caracteres no soportados.
    Normaliza acentos (a -> a) para que queden legibles.
    """
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_approx = nfkd.encode("ascii", "ignore").decode("ascii")
    # Fallback: char a char, reemplaza lo que no encaje
    result = []
    for ch in ascii_approx:
        try:
            ch.encode("latin-1")
            result.append(ch)
        except Exception:
            result.append("?")
    return "".join(result)


def safe_code_line(text):
    """Limpia una linea de codigo para FPDF (solo ASCII imprimible + tab->spaces)."""
    out = []
    for ch in text:
        cp = ord(ch)
        if cp == 9:
            out.append("    ")
        elif cp == 10:
            out.append("\n")
        elif cp < 32 or cp > 126:
            try:
                nfkd = unicodedata.normalize("NFKD", ch)
                approx = nfkd.encode("ascii", "ignore").decode("ascii")
                out.append(approx if approx else "?")
            except Exception:
                out.append("?")
        else:
            out.append(ch)
    return "".join(out)


def collect_files():
    result = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted([
            d for d in dirnames
            if d not in SKIP_DIRS and not d.startswith(".")
        ])
        for fname in sorted(filenames):
            if fname in SKIP_FILES:
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext not in CODE_EXTS:
                continue
            abs_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(abs_path, ROOT).replace("\\", "/")
            result.append((rel_path, abs_path))
    return result


def read_safe(path):
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except Exception:
            continue
    return "[unreadable]"


# ── PDF ───────────────────────────────────────────────────────────────────────

class SourcePDF(FPDF):
    def header(self):
        self.set_fill_color(*C_BG_HEADER)
        self.rect(0, 0, 210, 8, "F")
        self.set_font("Courier", "B", 7)
        self.set_text_color(*C_GREEN)
        self.set_xy(10, 1.5)
        self.cell(0, 5, "HostingGuard - Source Code")

    def footer(self):
        self.set_y(-7)
        self.set_font("Courier", "", 6)
        self.set_text_color(*C_PAGE_NUM)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.cell(0, 4, f"Page {self.page_no()} | Generated {ts}", align="C")

    def cover_page(self, files):
        self.add_page()

        # Title
        self.set_y(45)
        self.set_font("Helvetica", "B", 30)
        self.set_text_color(*C_GREEN)
        self.cell(0, 14, "HostingGuard", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_font("Helvetica", "", 13)
        self.set_text_color(*C_GRAY)
        self.cell(0, 8, "Complete Source Code", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(4)
        self.set_font("Courier", "", 9)
        self.set_text_color(90, 90, 100)
        ts = datetime.now().strftime("Exported %d/%m/%Y at %H:%M")
        self.cell(0, 6, ts, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Divider
        self.ln(6)
        self.set_draw_color(*C_GREEN)
        self.set_line_width(0.4)
        self.line(30, self.get_y(), 180, self.get_y())
        self.ln(8)

        # Stats
        ext_count = {}
        total_lines = 0
        for rel, abs_p in files:
            e = os.path.splitext(rel)[1].lower()
            ext_count[e] = ext_count.get(e, 0) + 1
            try:
                with open(abs_p, encoding="utf-8", errors="replace") as f:
                    total_lines += sum(1 for _ in f)
            except Exception:
                pass

        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*C_WHITE)
        self.cell(0, 7, "Project Statistics", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

        for label, val in [
            ("Total files",   str(len(files))),
            ("Lines of code", f"{total_lines:,}"),
            ("File types",    str(len(ext_count))),
        ]:
            self.set_font("Courier", "", 10)
            self.set_text_color(*C_GRAY)
            self.cell(90, 6, label, align="R")
            self.cell(5,  6, "")
            self.set_text_color(*C_GREEN)
            self.cell(0,  6, val, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Extensions breakdown
        self.ln(5)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*C_WHITE)
        self.cell(0, 6, "Files by type", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

        self.set_font("Courier", "", 8)
        sorted_exts = sorted(ext_count.items(), key=lambda x: -x[1])
        col = 0
        for ext, cnt in sorted_exts:
            x_off = 45 + (col % 3) * 42
            y_row = self.get_y()
            self.set_x(x_off)
            self.set_text_color(*C_GRAY)
            self.cell(22, 4.5, ext or "(none)")
            self.set_text_color(*C_GREEN)
            self.cell(0,  4.5, str(cnt), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            col += 1
            if col % 3 != 0:
                self.set_y(y_row)

        # File index
        self.ln(6)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*C_WHITE)
        self.cell(0, 6, "File Index", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

        self.set_font("Courier", "", 6.5)
        for i, (rel, _) in enumerate(files, 1):
            self.set_text_color(70, 70, 80)
            self.cell(10, 3.8, f"{i:3}.")
            self.set_text_color(170, 195, 170)
            self.cell(0,  3.8, rel, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def write_file(self, rel_path, content):
        self.add_page()

        # Dark background for code page
        self.set_fill_color(*C_BG_CODE)
        self.rect(0, 0, 210, 297, "F")

        # File header bar
        self.set_y(9)
        self.set_fill_color(*C_BG_FILE)
        self.set_font("Courier", "B", 7.5)
        self.set_text_color(*C_GREEN)
        lines_count = content.count("\n") + 1
        self.cell(0, 5.5, f"  >> {rel_path}   ({lines_count} lines)",
                  fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

        # Code lines
        lines = content.split("\n")
        avg_len = sum(len(l) for l in lines[:40]) / max(len(lines[:40]), 1)
        font_size = 6.0 if avg_len > 90 else 6.8
        line_h = font_size * 0.44

        self.set_font("Courier", "", font_size)

        for i, raw in enumerate(lines, 1):
            line = safe_code_line(raw).rstrip()

            # Line number
            self.set_text_color(*C_FG_LINENUM)
            self.cell(9, line_h, f"{i:4}", new_x=XPos.RIGHT, new_y=YPos.TOP)

            # Syntax color (simple)
            stripped = line.lstrip()
            if stripped.startswith(("#", "//", "/*", "*", "<!--")):
                self.set_text_color(*C_FG_COMMENT)
            elif any(stripped.startswith(k) for k in (
                "import ", "from ", "export ", "def ", "class ", "return ",
                "async ", "await ", "const ", "let ", "var ", "function ",
                "if ", "elif ", "else", "for ", "while ", "try:", "except",
                "SELECT ", "INSERT ", "UPDATE ", "CREATE ", "DROP ",
            )):
                self.set_text_color(*C_FG_KEYWORD)
            else:
                self.set_text_color(*C_FG_CODE)

            if len(line) > 150:
                line = line[:148] + "~"

            self.multi_cell(0, line_h, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(1)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Collecting files...")
    files = collect_files()
    files = [(r, a) for r, a in files if not r.endswith("generate_pdf.py")]
    print(f"  Found: {len(files)} files")

    print("Building PDF...")
    pdf = SourcePDF()
    pdf.set_margins(10, 10, 10)
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.set_title("HostingGuard - Complete Source Code")
    pdf.set_author("HostingGuard")

    pdf.cover_page(files)

    for idx, (rel_path, abs_path) in enumerate(files, 1):
        content = read_safe(abs_path)
        if len(content) > MAX_FILE_CHARS:
            content = content[:MAX_FILE_CHARS] + f"\n\n... [truncated - {len(content):,} chars total]"
        n_lines = content.count("\n") + 1
        print(f"  [{idx:3}/{len(files)}] {rel_path} ({n_lines} lines)")
        pdf.write_file(rel_path, content)

    print(f"\nSaving to: {OUTPUT_FILE}")
    pdf.output(OUTPUT_FILE)
    size_mb = os.path.getsize(OUTPUT_FILE) / 1_048_576
    print(f"Done! PDF generated ({size_mb:.1f} MB)")
    print(f"Path: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
