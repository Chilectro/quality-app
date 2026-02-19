import hashlib
import re
import pandas as pd

SUBSYSTEM_REGEX = re.compile(r"\b(\d{4}-[A-Z0-9]{2,3}-\d{3})\b")


def sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()

def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().upper().replace("\n", " ").replace("  ", " ") for c in df.columns]
    return df

def find_header_row_for_apsa(path: str, sheet: str, max_scan: int = 20) -> int:
    # Escaneamos primeras filas hasta encontrar fila con varias cabeceras clave
    probe = pd.read_excel(path, sheet_name=sheet, header=None, nrows=max_scan, engine='calamine')
    keys = {"N° CÓDIGO CMDIC","N° CODIGO CMDIC","DESCRIPCIÓN","DESCRIPCION","DESCRIPCIÓN DE ELEMENTOS","SUBSISTEMA","DISCIPLINA","STATUS BIM 360 FIELD"}
    for i in range(len(probe.index)):
        row_vals = [str(x).strip().upper() for x in list(probe.iloc[i].values)]
        hits = sum(1 for v in row_vals if v in keys)
        if hits >= 2:
            return i
    return 0  # fallback

def extract_subsystem_code(text: str) -> str | None:
    if not text:
        return None
    t = str(text).upper()
    m = SUBSYSTEM_REGEX.search(t)
    if m:
        return m.group(1)
    if " - " in t:
        left = t.split(" - ", 1)[0].strip()
        if SUBSYSTEM_REGEX.match(left):
            return left
    return None

def normalize_disc_code(val) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if not s or s.upper() == "NAN":
        return ""
    try:
        f = float(s.replace(",", "."))  # por si viene "56,0"
        i = int(f)
        if 0 <= i <= 99:
            return str(i)
    except:
        pass
    m = re.search(r"\b(\d{2})\b", s)
    if m:
        return str(int(m.group(1)))
    return ""

def discipline_from_subsystem(subs: str) -> str:
    """
    Toma '5620-S01-003' y devuelve '56'.
    """
    code = extract_subsystem_code(subs or "")
    if not code:
        return ""
    m = re.match(r"(\d{2})\d{2}-", code)  # primeros 2 dígitos
    return m.group(1) if m else ""