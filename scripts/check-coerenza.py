#!/usr/bin/env python3
"""Controllo di coerenza da lanciare prima di ogni commit (2026-09-26).

Regole complete e cose da ricordare a mano in docs/CHECKLIST_AGGIORNAMENTO.md.

Uso (dalla cartella ferroteca-backend):  python3 scripts/check-coerenza.py
Esce con codice 1 se c'è qualcosa da sistemare (PROBLEMI): in quel caso non si
committa. Gli AVVISI vanno letti ma non bloccano. Non contatta la rete, non
tocca Supabase, non legge .env né data/pdfs/ (solo i nomi dei file).
"""
import ast, io, json, re, subprocess, sys, tokenize
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
problems, warnings = [], []

# 1) Ultima decisione del diario = data dell'ultima intestazione "## AAAA-MM-GG"
log = (ROOT / "docs/DECISION_LOG.md").read_text(encoding="utf-8")
LAST = max(re.findall(r"^## (\d{4}-\d{2}-\d{2})", log, re.M))

# 2) Documenti di stato che dichiarano "Allineato a"
for f in ["../CLAUDE.md", "docs/AUDIT.md", "docs/BLUEPRINT.md", "docs/DECISIONS.md",
          "docs/CHECKLIST_AGGIORNAMENTO.md"]:
    p = ROOT / f
    if not p.exists():
        warnings.append(f"{f}: non trovato (fuori dal repository?)")
        continue
    m = re.search(r"Allineato a:\s*(\d{4}-\d{2}-\d{2})", p.read_text(encoding="utf-8"))
    if not m:
        problems.append(f'{f}: manca la riga "Allineato a"')
    elif m.group(1) != LAST:
        problems.append(f"{f}: allineato a {m.group(1)}, ultima decisione {LAST} → rileggilo e aggiornalo")

# 3) Codice Python: deve girare su Python 3.11 (Dockerfile di produzione)
py_files = [p for p in ROOT.rglob("*.py") if "venv" not in p.parts and "__pycache__" not in p.parts]
for p in py_files:
    src = p.read_text(encoding="utf-8")
    rel = p.relative_to(ROOT)
    try:
        ast.parse(src, feature_version=(3, 11))
    except SyntaxError as e:
        problems.append(f"{rel}: errore di sintassi ({e})")
        continue
    # ast non intercetta la barra rovesciata dentro le {} di una f-string,
    # valida solo da Python 3.12: su Render (3.11) l'app non partirebbe.
    if sys.version_info >= (3, 12):
        depth_f, braces = 0, []
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            name = tokenize.tok_name[tok.type]
            if name == "FSTRING_START":
                depth_f += 1; braces.append(0)
            elif name == "FSTRING_END":
                depth_f -= 1; braces.pop()
            elif depth_f and tok.type == tokenize.OP and tok.string in "{}":
                braces[-1] += 1 if tok.string == "{" else -1
            elif depth_f and braces and braces[-1] > 0 and "\\" in tok.string:
                problems.append(f"{rel}:{tok.start[0]}: barra rovesciata dentro {{}} di una f-string (non valida su Python 3.11)")

# 4) Solo services/llm_provider.py parla con l'SDK del provider (DECISIONS.md)
for p in py_files:
    if p.name == "llm_provider.py":
        continue
    if re.search(r"^\s*(from|import)\s+(google\.genai|google\.generativeai|google import genai|langchain_google_genai)",
                 p.read_text(encoding="utf-8"), re.M):
        problems.append(f"{p.relative_to(ROOT)}: importa direttamente l'SDK Gemini → passare da services/llm_provider.py")

# 5) Mappatura arricchimenti: JSON valido, nomi file univoci (index_pdf cancella per nome file)
try:
    m = json.loads((ROOT / "docs/enrichment_mapping.json").read_text(encoding="utf-8"))["mappatura_per_volume"]
    rels = {r for e in m.values() for r in e.get("da_citazione", [])}
    dup = [n for n, c in Counter(Path(r).name for r in rels).items() if c > 1]
    if dup:
        problems.append(f"enrichment_mapping.json: nomi file ripetuti in cartelle diverse {dup}")
    mains = {p.name for p in (ROOT / "data/pdfs").glob("*.pdf")}
    if mains:
        clash = {Path(r).name for r in rels} & mains
        if clash:
            problems.append(f"enrichment_mapping.json: arricchimenti con lo stesso nome di un testo principale {clash}")
        missing = set(m) - {Path(n).stem for n in mains}
        if missing:
            warnings.append(f"enrichment_mapping.json: {len(missing)} volumi mappati senza testo principale in data/pdfs "
                            f"(i loro arricchimenti non vengono mai aggiunti in ask()): {sorted(missing)}")
except Exception as e:
    problems.append(f"docs/enrichment_mapping.json illeggibile: {e}")

# 6) Credenziali mai sotto git
tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
for t in tracked:
    if Path(t).name in {".env", "keys.rtf", "env"}:
        problems.append(f"{t}: file di credenziali tracciato da git!")

for w in warnings:
    print("AVVISO  ", w)
for p in problems:
    print("PROBLEMA", p)
print(f"\nUltima decisione: {LAST} — {len(problems)} problemi, {len(warnings)} avvisi")
sys.exit(1 if problems else 0)
