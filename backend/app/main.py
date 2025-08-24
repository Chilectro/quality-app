from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_, case
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from .auth import verify_token, require_roles
from pydantic import BaseModel, EmailStr, constr
from fastapi import Path
from typing import Literal


app = FastAPI(title="Quality Backend", version="0.1.0")

# CORS para el frontend local (cuando lo montemos)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/me")
def me(decoded=Depends(verify_token)):
    # En modo AUTH_DISABLED=true, devolverá un usuario simulado
    return {
        "name": decoded.get("name"),
        "preferred_username": decoded.get("preferred_username"),
        "roles": decoded.get("roles", []),
        "aud": decoded.get("aud"),
        "iss": decoded.get("iss"),
    }

@app.get("/admin/ping")
def admin_ping(decoded=Depends(require_roles("Admin"))):
    return {"ok": True, "role": "Admin"}

# === NUEVO: endpoints de carga APSA/ACONEX ===
from io import BytesIO
from fastapi import UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
import pandas as pd
from .deps import get_db
from .config import get_settings
from .models.load import Load, SourceEnum
from .models.apsa_protocol import ApsaProtocol
from .models.aconex_doc import AconexDoc
from .utils import (
    sha256_bytes, normalize_cols, find_header_row_for_apsa,
    extract_subsystem_code, normalize_disc_code, discipline_from_subsystem
)
from sqlalchemy import select, delete

from pydantic import BaseModel, EmailStr, Field
from fastapi import Response
from datetime import datetime, timezone

from .models.user import User
from .models.refresh_token import RefreshToken
from .security import hash_password, verify_password, create_access_token, new_refresh_token, hash_token, refresh_token_expiry
from fastapi import Request
from sqlalchemy import literal
from sqlalchemy.orm import aliased
from fastapi import Query
from fastapi.responses import StreamingResponse
from io import StringIO
import csv
from sqlalchemy import literal_column

def set_refresh_cookie(response: Response, token: str):
    s = get_settings()
    cd = (getattr(s, "COOKIE_DOMAIN", None) or "").strip().lower()
    use_domain = cd not in ("", "localhost", "127.0.0.1")

    cookie_kwargs = dict(
        key="refresh_token",
        value=token,
        httponly=True,
        secure=bool(s.COOKIE_SECURE),
        samesite=s.COOKIE_SAMESITE,
        max_age=60 * 60 * 24 * int(s.REFRESH_TOKEN_EXPIRE_DAYS),
        path=s.COOKIE_PATH or "/auth",    # <— AQUÍ
    )
    if use_domain:
        cookie_kwargs["domain"] = cd

    response.set_cookie(**cookie_kwargs)

def clear_refresh_cookie(response: Response):
    s = get_settings()
    cd = (getattr(s, "COOKIE_DOMAIN", None) or "").strip().lower()
    use_domain = cd not in ("", "localhost", "127.0.0.1")

    delete_kwargs = dict(
        key="refresh_token",
        path=s.COOKIE_PATH or "/auth",    # <— AQUÍ
    )
    if use_domain:
        delete_kwargs["domain"] = cd

    response.delete_cookie(**delete_kwargs)

def _norm_sql(expr):
    # UPPER(TRIM(REPLACE(REPLACE(expr,'-',''),' ','')))
    return func.upper(func.trim(func.replace(func.replace(expr, "-", ""), " ", "")))

def _pick_sheet(xls: pd.ExcelFile, preferred_name: str) -> str:
    # Busca por nombre exacto (case-insensitive) y si no, toma la primera
    lowpref = preferred_name.strip().lower()
    for s in xls.sheet_names:
        if s.strip().lower() == lowpref:
            return s
    return xls.sheet_names[0]

def _store_load(db: Session, source: SourceEnum, filename: str, filehash: str) -> Load:
    load = Load(source=source, filename=filename, file_hash=filehash)
    db.add(load)
    db.commit()
    db.refresh(load)
    return load

def _purge_old_loads(db: Session, source: SourceEnum, keep: int = 2):
    # Mantener solo las últimas 'keep' cargas; eliminar el resto (en cascada)
    loads = db.execute(
        select(Load).where(Load.source == source).order_by(Load.loaded_at.desc(), Load.id.desc())
    ).scalars().all()
    if len(loads) > keep:
        to_delete = loads[keep:]
        for l in to_delete:
            db.execute(delete(Load).where(Load.id == l.id))
        db.commit()

def _latest_load_id(db: Session, source: SourceEnum) -> int | None:
    row = db.execute(
        select(Load.id)
        .where(Load.source == source)
        .order_by(Load.loaded_at.desc(), Load.id.desc())
        .limit(1)
    ).scalar()
    return row

def _previous_load_id(db: Session, source: SourceEnum) -> int | None:
    ids = db.execute(
        select(Load.id)
        .where(Load.source == source)
        .order_by(Load.loaded_at.desc(), Load.id.desc())
        .limit(2)
    ).scalars().all()
    return ids[1] if len(ids) > 1 else None

def _purge_source_all(db: Session, source: SourceEnum) -> int:
    """Borra TODAS las cargas y sus filas asociadas para una fuente."""
    load_ids = [lid for (lid,) in db.execute(select(Load.id).where(Load.source == source)).all()]
    if not load_ids:
        return 0
    if source == SourceEnum.APSA:
        db.execute(delete(ApsaProtocol).where(ApsaProtocol.load_id.in_(load_ids)))
    elif source == SourceEnum.ACONEX:
        db.execute(delete(AconexDoc).where(AconexDoc.load_id.in_(load_ids)))
    db.execute(delete(Load).where(Load.id.in_(load_ids)))
    db.commit()
    return len(load_ids)

class BootstrapRequest(BaseModel):
    token: str
    email: EmailStr
    full_name: str | None = None
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = None  # futuro

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    roles: list[str]
    email: EmailStr
    name: str | None = None

class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str | None = None
    roles: list[str]
    is_active: bool
    is_email_verified: bool

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str | None = None
    password: str = Field(..., min_length=8)
    roles: list[str] = ["User"]
    is_active: bool = True

class UserUpdate(BaseModel):
    full_name: str | None = None
    roles: list[str] | None = None
    is_active: bool | None = None

class SetPassword(BaseModel):
    password: str = Field(..., min_length=8)

class ChangePassword(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)

def _user_to_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        email=u.email,
        full_name=u.full_name or "",
        roles=[r.strip() for r in (u.roles or "").split(",") if r.strip()],
        is_active=bool(u.is_active),
        is_email_verified=bool(u.is_email_verified),
    )

@app.get("/admin/users", response_model=list[UserOut])
def admin_users_list(db: Session = Depends(get_db), decoded=Depends(require_roles("Admin"))):
    rows = db.execute(select(User).order_by(User.id.asc())).scalars().all()
    return [_user_to_out(u) for u in rows]

@app.post("/admin/users", response_model=UserOut)
def admin_users_create(body: UserCreate, db: Session = Depends(get_db), decoded=Depends(require_roles("Admin"))):
    email = str(body.email).lower()
    exists = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="Ya existe un usuario con ese email")

    roles_csv = ",".join(sorted(set([r.strip() for r in (body.roles or ["User"]) if r.strip()])))
    u = User(
        email=email,
        full_name=body.full_name or "",
        password_hash=hash_password(body.password),
        roles=roles_csv or "User",
        is_active=bool(body.is_active),
        is_email_verified=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return _user_to_out(u)

@app.patch("/admin/users/{user_id}", response_model=UserOut)
def admin_users_update(
    user_id: int = Path(..., ge=1),
    body: UserUpdate | None = None,
    db: Session = Depends(get_db),
    decoded=Depends(require_roles("Admin"))
):
    u = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if body is not None:
        if body.full_name is not None:
            u.full_name = body.full_name

        if body.roles is not None:
            roles_csv = ",".join(sorted(set([r.strip() for r in body.roles if r.strip()])))
            u.roles = roles_csv or "User"

        if body.is_active is not None:
            u.is_active = bool(body.is_active)
            if not u.is_active:
                # Revoca todos los refresh tokens del usuario
                db.query(RefreshToken).filter(RefreshToken.user_id == u.id).update({"revoked": True})

    db.add(u)
    db.commit()
    db.refresh(u)
    return _user_to_out(u)

@app.post("/admin/users/{user_id}/set-password")
def admin_users_set_password(
    user_id: int,
    body: SetPassword,
    db: Session = Depends(get_db),
    decoded=Depends(require_roles("Admin"))
):
    u = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    u.password_hash = hash_password(body.password)
    db.query(RefreshToken).filter(RefreshToken.user_id == u.id).update({"revoked": True})
    db.add(u)
    db.commit()
    return {"ok": True, "user_id": u.id}

@app.post("/auth/change-password")
def auth_change_password(
    body: ChangePassword,
    db: Session = Depends(get_db),
    decoded=Depends(verify_token)
):
    # decoded["sub"] es el user_id
    try:
        user_id = int(decoded.get("sub"))
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido")

    u = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not u or not u.is_active:
        raise HTTPException(status_code=401, detail="Usuario inválido o inactivo")

    if not verify_password(body.current_password, u.password_hash):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")

    u.password_hash = hash_password(body.new_password)
    db.query(RefreshToken).filter(RefreshToken.user_id == u.id).update({"revoked": True})
    db.add(u)
    db.commit()
    return {"ok": True}

@app.delete("/admin/users/{user_id}")
def admin_users_delete(
    user_id: int = Path(..., ge=1),
    hard: bool = False,  # si quieres borrar físicamente: /admin/users/123?hard=true
    db: Session = Depends(get_db),
    decoded=Depends(require_roles("Admin"))
):
    # evita que un admin se autodestruya :)
    try:
        current_id = int(decoded.get("sub"))
    except Exception:
        current_id = None

    if current_id == user_id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario")

    u = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # revoca refresh tokens vigentes
    db.query(RefreshToken).filter(RefreshToken.user_id == u.id).update({"revoked": True})

    if hard:
        # borrar físico (solo si estás seguro que no rompe FKs)
        db.delete(u)
    else:
        # “eliminar” lógico = desactivar
        u.is_active = False
        db.add(u)

    db.commit()
    return {"ok": True, "user_id": user_id, "deleted": bool(hard), "now_active": bool(u.is_active) if not hard else False}

@app.post("/auth/bootstrap")
def auth_bootstrap(body: BootstrapRequest, db: Session = Depends(get_db)):
    """
    Crea el PRIMER usuario Admin si no hay usuarios en la tabla.
    Protegido por BOOTSTRAP_TOKEN (en .env).
    """
    s = get_settings()
    existing = db.execute(select(func.count()).select_from(User)).scalar()
    if existing and existing > 0:
        raise HTTPException(status_code=400, detail="Ya existe al menos un usuario")

    if not s.BOOTSTRAP_TOKEN or body.token != s.BOOTSTRAP_TOKEN:
        raise HTTPException(status_code=401, detail="Token de bootstrap inválido")

    user = User(
        email=str(body.email).lower(),
        full_name=body.full_name or "",
        password_hash=hash_password(body.password),
        roles="Admin",
        is_active=True,
        is_email_verified=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"ok": True, "user_id": user.id, "email": user.email, "roles": user.roles.split(",")}

@app.post("/auth/login", response_model=LoginResponse)
def auth_login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == str(body.email).lower())).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas")

    # TODO: si user.mfa_secret existe, verifica body.totp_code (pyotp)

    roles = [r.strip() for r in (user.roles or "User").split(",") if r.strip()]
    access_token = create_access_token(user.id, user.email, user.full_name, roles)

    # refresh token rotativo
    raw_refresh = new_refresh_token()
    rt = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh),
        expires_at=refresh_token_expiry(),
        revoked=False
    )
    db.add(rt)
    db.commit()

    set_refresh_cookie(response, raw_refresh)

    return LoginResponse(
        access_token=access_token,
        expires_in=get_settings().ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        roles=roles,
        email=user.email,
        name=user.full_name
    )

@app.post("/auth/refresh", response_model=LoginResponse)
def auth_refresh(
    response: Response,
    request: Request,                                # <— TIPADO AQUÍ
    db: Session = Depends(get_db)
):
    raw_refresh = request.cookies.get("refresh_token")
    if not raw_refresh:
        raise HTTPException(status_code=401, detail="Sin refresh token")

    token_h = hash_token(raw_refresh)
    now = datetime.now(timezone.utc)

    rt = db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_h,
            RefreshToken.revoked == False,
            RefreshToken.expires_at > now
        )
    ).scalar_one_or_none()

    if not rt:
        raise HTTPException(status_code=401, detail="Refresh inválido o expirado")

    user = db.execute(select(User).where(User.id == rt.user_id)).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Usuario inactivo")

    # rotación
    rt.revoked = True
    db.add(rt)

    roles = [r.strip() for r in (user.roles or "User").split(",") if r.strip()]
    access_token = create_access_token(user.id, user.email, user.full_name, roles)

    new_raw = new_refresh_token()
    new_rt = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(new_raw),
        expires_at=refresh_token_expiry(),
        revoked=False,
        parent_id=rt.id
    )
    db.add(new_rt)
    db.commit()

    set_refresh_cookie(response, new_raw)

    return LoginResponse(
        access_token=access_token,
        expires_in=get_settings().ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        roles=roles,
        email=user.email,
        name=user.full_name
    )


@app.post("/auth/logout")
def auth_logout(
    response: Response,
    request: Request,                                 # <— TIPADO AQUÍ
    db: Session = Depends(get_db),
    decoded=Depends(verify_token)
):
    raw_refresh = request.cookies.get("refresh_token")
    if raw_refresh:
        token_h = hash_token(raw_refresh)
        rt = db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_h)).scalar_one_or_none()
        if rt:
            rt.revoked = True
            db.add(rt)
            db.commit()

    clear_refresh_cookie(response)
    return {"ok": True}

@app.post("/admin/upload/apsa")
def upload_apsa(
    file: UploadFile = File(...),
    hard: bool = Query(False, description="Si true, elimina TODAS las cargas APSA antes de insertar"),
    db: Session = Depends(get_db),
    decoded=Depends(require_roles("Admin"))
):
    # Si pides hard=true, vaciamos APSA
    if hard:
        _purge_source_all(db, SourceEnum.APSA)
    # Leer bytes y hash
    content = file.file.read()
    filehash = sha256_bytes(content)

    # Elegir hoja
    try:
        sheet = _pick_sheet(pd.ExcelFile(BytesIO(content)), "APSA")
    except Exception:
        sheet = "APSA"

    # Detectar fila de encabezados y leer
    header_row = find_header_row_for_apsa(BytesIO(content), sheet)
    df = pd.read_excel(BytesIO(content), sheet_name=sheet, header=header_row)

    # Normalizar nombres de columnas
    df = normalize_cols(df)

    # ---- Aliases robustos (acepta 'Z DISCIPLINA', 'N SUBSISTEMA', etc.) ----
    def find_col(df_cols, *candidates_contains):
        for c in df_cols:
            U = str(c).upper().strip()
            if any(tok in U for tok in candidates_contains):
                return c
        return None

    COL_CODIGO = find_col(df.columns, "CÓDIGO CMDIC", "CODIGO CMDIC")
    COL_DESC   = find_col(df.columns, "DESCRIPCIÓN DE ELEMENTOS", "DESCRIPCIÓN", "DESCRIPCION")
    COL_TAG    = find_col(df.columns, "TAG")
    COL_SUBS   = find_col(df.columns, "SUBSISTEMA")
    COL_DISC   = find_col(df.columns, "DISCIPLINA")
    COL_STATUS = find_col(df.columns, "STATUS BIM 360", "STATUS BIM360")

    required = [
        ("N° CÓDIGO CMDIC", COL_CODIGO),
        ("DESCRIPCIÓN/DE ELEMENTOS", COL_DESC),
        ("TAG", COL_TAG),
        ("SUBSISTEMA", COL_SUBS),
        ("DISCIPLINA", COL_DISC),
        ("STATUS BIM 360 FIELD", COL_STATUS),
    ]
    missing = [name for name, col in required if col is None]
    if missing:
        raise HTTPException(status_code=400, detail=f"Columnas faltantes en APSA: {missing}")

    # Crear registro de carga
    load = _store_load(db, SourceEnum.APSA, file.filename, filehash)

    # Insertar filas normalizadas
    rows: list[ApsaProtocol] = []
    for _, r in df.iterrows():
        # Subsistema limpio
        subs_raw = r.get(COL_SUBS, "")
        subs_str = "" if pd.isna(subs_raw) else str(subs_raw).strip().upper()
        if subs_str in ("NAN", "NONE", "NULL"):
            subs_str = ""

        # Disciplina: primero desde la celda; si no hay, derivar desde el subsistema (ej '5620-...' => '56')
        disc_code = normalize_disc_code(r.get(COL_DISC, ""))
        if not disc_code or disc_code == "0":
            disc_code = discipline_from_subsystem(subs_str)

        rows.append(ApsaProtocol(
            load_id=load.id,
            codigo_cmdic=str(r.get(COL_CODIGO, "") or "").strip(),
            descripcion=str(r.get(COL_DESC, "") or "").strip(),
            tag=str(r.get(COL_TAG, "") or "").strip(),
            subsistema=subs_str,
            disciplina=disc_code,
            status_bim360=str(r.get(COL_STATUS, "") or "").strip().upper(),
        ))

    if rows:
        db.bulk_save_objects(rows)
        db.commit()

    # Mantener solo las 2 últimas cargas APSA
    _purge_old_loads(db, SourceEnum.APSA, keep=2)

    return {"ok": True, "rows_inserted": len(rows), "sheet": sheet, "header_row": int(header_row)}

@app.post("/admin/upload/aconex")
def upload_aconex(
    file: UploadFile = File(...),
    hard: bool = Query(True, description="Si true, elimina TODAS las cargas ACONEX antes de insertar"),
    db: Session = Depends(get_db),
    decoded=Depends(require_roles("Admin"))
):
    if hard:
        _purge_source_all(db, SourceEnum.ACONEX)
    content = file.file.read()
    filehash = sha256_bytes(content)

    # Elegir hoja
    try:
        sheet = _pick_sheet(pd.ExcelFile(BytesIO(content)), "Cargados ACONEX")
    except Exception:
        sheet = "Cargados ACONEX"

    # Leer y normalizar
    df = pd.read_excel(BytesIO(content), sheet_name=sheet)
    df = normalize_cols(df)

    # Aliases de columnas
    COL_DOCNO   = next((c for c in df.columns if c in ("DOCUMENT NO","DOCUMENT NUMBER","DOCUMENT N°","DOCUMENT Nº")), None)
    COL_TITLE   = next((c for c in df.columns if c == "TITLE"), None)
    COL_DISC    = next((c for c in df.columns if c == "DISCIPLINE"), None)
    COL_FUNC    = next((c for c in df.columns if c == "FUNCTION"), None)
    COL_SUBSYS  = next((c for c in df.columns if c in ("SUBSYSTEM N°","SUBSYSTEM Nº","SUBSYSTEM NO","SUBSYSTEM NUMBER")), None)
    COL_SYSNO   = next((c for c in df.columns if c in ("SYSTEM N°","SYSTEM Nº","SYSTEM NO","SYSTEM NUMBER")), None)
    COL_FILE    = next((c for c in df.columns if c == "FILE NAME"), None)
    COL_EQUIP   = next((c for c in df.columns if c in ("EQUIPMENT/TAG N°","EQUIPMENT/TAG NO","EQUIPMENT/TAG")), None)
    COL_DATE    = next((c for c in df.columns if c in ("DATE RECEIVED","RECEIVED DATE")), None)
    COL_REV     = next((c for c in df.columns if c == "REVISION"), None)
    COL_TRANS   = next((c for c in df.columns if c in ("TRANSMITTED","TRANSMITTAL IN")), None)

    required = [("DOCUMENT NO", COL_DOCNO), ("FUNCTION", COL_FUNC), ("SUBSYSTEM N°", COL_SUBSYS)]
    missing = [name for name, col in required if col is None]
    if missing:
        raise HTTPException(status_code=400, detail=f"Columnas faltantes en ACONEX: {missing}")

    # Crear carga
    load = _store_load(db, SourceEnum.ACONEX, file.filename, filehash)

    rows: list[AconexDoc] = []
    for _, r in df.iterrows():
        subsystem_text = str(r.get(COL_SUBSYS, "") or "").strip()
        subsystem_code = extract_subsystem_code(subsystem_text)

        # FUNCTION trae cosas tipo: "57 Construcción - Electricidad"
        function_val = str(r.get(COL_FUNC, "") or "").strip()

        # Si DISCIPLINE está vacío, saca el código de FUNCTION
        disc_raw = str(r.get(COL_DISC, "") or "").strip() if COL_DISC else ""
        discipline_code = normalize_disc_code(disc_raw or function_val)

        rows.append(AconexDoc(
            load_id=load.id,
            document_no=str(r.get(COL_DOCNO, "") or "").strip(),
            title=str(r.get(COL_TITLE, "") or "").strip(),
            discipline=discipline_code,
            function=function_val,
            subsystem_text=subsystem_text,
            subsystem_code=subsystem_code or "",
            system_no=str(r.get(COL_SYSNO, "") or "").strip(),
            file_name=str(r.get(COL_FILE, "") or "").strip(),
            equipment_tag_no=str(r.get(COL_EQUIP, "") or "").strip(),
            date_received=str(r.get(COL_DATE, "") or "").strip(),
            revision=str(r.get(COL_REV, "") or "").strip(),
            transmitted=str(r.get(COL_TRANS, "") or "").strip(),
        ))

    if rows:
        db.bulk_save_objects(rows)
        db.commit()

    _purge_old_loads(db, SourceEnum.ACONEX, keep=2)

    return {"ok": True, "rows_inserted": len(rows), "sheet": sheet}

@app.get("/metrics/cards")
def metrics_cards(db: Session = Depends(get_db), decoded=Depends(verify_token)):
    apsa_id = _latest_load_id(db, SourceEnum.APSA)
    aconex_id = _latest_load_id(db, SourceEnum.ACONEX)

    # --- Métricas APSA (universo/abiertos/cerrados)
    abiertos = cerrados = universo = 0
    if apsa_id:
        abiertos = db.execute(
            select(func.count()).select_from(ApsaProtocol).where(
                ApsaProtocol.load_id == apsa_id,
                ApsaProtocol.status_bim360 == "ABIERTO"
            )
        ).scalar() or 0

        cerrados = db.execute(
            select(func.count()).select_from(ApsaProtocol).where(
                ApsaProtocol.load_id == apsa_id,
                ApsaProtocol.status_bim360 == "CERRADO"
            )
        ).scalar() or 0

        universo = (abiertos or 0) + (cerrados or 0)

    # --- Normalizador SQL (sin depender de utils)
    # TRIM + UPPER + remove spaces/hyphens/underscores para comparar códigos
    def N(expr):
        return func.replace(
            func.replace(
                func.replace(
                    func.upper(func.trim(expr)),
                    " ", ""
                ),
                "-", ""
            ),
            "_", ""
        )

    # --- Métricas ACONEX
    # Queremos:
    #  - aconex_cargados   -> filas crudas del log (total rows)
    #  - aconex_unicos     -> documentos únicos normalizados
    #  - aconex_validos    -> doc únicos normalizados que matchean con APSA por codigo_cmdic normalizado
    #  - aconex_invalidos  -> unicos - validos
    #  - aconex_duplicados -> filas crudas - unicos
    aconex_rows = aconex_unicos = aconex_validos = 0

    if aconex_id:
        # 1) Filas crudas (todo el log cargado)
        aconex_rows = db.execute(
            select(func.count()).select_from(AconexDoc).where(AconexDoc.load_id == aconex_id)
        ).scalar() or 0

        # 2) Documentos únicos (normalizados)
        aconex_unicos = db.execute(
            select(func.count(func.distinct(N(AconexDoc.document_no)))).where(AconexDoc.load_id == aconex_id)
        ).scalar() or 0

        # 3) Válidos: doc únicos normalizados que matchean con APSA por código (normalizado)
        if apsa_id:
            aconex_validos = db.execute(
                select(func.count(func.distinct(N(AconexDoc.document_no)))).where(
                    AconexDoc.load_id == aconex_id,
                    # correlated subquery con .exists() (no requiere import exists)
                    select(1).where(
                        ApsaProtocol.load_id == apsa_id,
                        N(ApsaProtocol.codigo_cmdic) == N(AconexDoc.document_no)
                    ).exists()
                )
            ).scalar() or 0

    aconex_invalidos = max(0, (aconex_unicos or 0) - (aconex_validos or 0))
    aconex_duplicados = max(0, (aconex_rows or 0) - (aconex_unicos or 0))

    # RESPUESTA: mantenemos claves para el front actual y añadimos diagnóstico
    return {
        "universo": int(universo),
        "abiertos": int(abiertos),
        "cerrados": int(cerrados),

        # Tarjeta actual del front:
        "aconex_cargados": int(aconex_rows),      # filas crudas del log (ej. 9345)

        # Extras/diagnóstico (útiles en el futuro):
        "aconex_unicos": int(aconex_unicos),             # ej. 9276
        "aconex_validos": int(aconex_validos),           # ej. 9043
        "aconex_invalidos": int(aconex_invalidos),       # ej. 233
        "aconex_duplicados": int(aconex_duplicados),     # ej. 69
    }

@app.get("/metrics/disciplinas")
def metrics_disciplinas(db: Session = Depends(get_db), decoded=Depends(verify_token)):
    apsa_id = _latest_load_id(db, SourceEnum.APSA)
    aconex_id = _latest_load_id(db, SourceEnum.ACONEX)
    if not apsa_id:
        return []

    disciplinas = [str(d) for d in range(50, 60)]
    out = []

    for d in disciplinas:
        universo = db.execute(
            select(func.count()).select_from(ApsaProtocol).where(
                ApsaProtocol.load_id == apsa_id,
                ApsaProtocol.disciplina == d
            )
        ).scalar() or 0

        abiertos = db.execute(
            select(func.count()).select_from(ApsaProtocol).where(
                ApsaProtocol.load_id == apsa_id,
                ApsaProtocol.disciplina == d,
                ApsaProtocol.status_bim360 == "ABIERTO"
            )
        ).scalar() or 0

        cerrados = db.execute(
            select(func.count()).select_from(ApsaProtocol).where(
                ApsaProtocol.load_id == apsa_id,
                ApsaProtocol.disciplina == d,
                ApsaProtocol.status_bim360 == "CERRADO"
            )
        ).scalar() or 0

        # SOLO por coincidencia de código (document_no == codigo_cmdic)
        aconex = 0
        if aconex_id:
            aconex = db.execute(
                select(func.count(func.distinct(ApsaProtocol.codigo_cmdic)))
                .where(
                    ApsaProtocol.load_id == apsa_id,
                    ApsaProtocol.disciplina == d,
                    select(1).where(
                        AconexDoc.load_id == aconex_id,
                        AconexDoc.document_no == ApsaProtocol.codigo_cmdic
                    ).exists()
                )
            ).scalar() or 0

        out.append({
            "disciplina": d,
            "universo": universo,
            "abiertos": abiertos,
            "cerrados": cerrados,
            "aconex": aconex,
        })

    return out

@app.get("/metrics/grupos")
def metrics_grupos(db: Session = Depends(get_db), decoded=Depends(verify_token)):
    apsa_id = _latest_load_id(db, SourceEnum.APSA)
    aconex_id = _latest_load_id(db, SourceEnum.ACONEX)
    if not apsa_id:
        return []

    grupos = {
        "Obra civil": [str(x) for x in range(50, 55)],  # 50-54
        "Mecánico Pipping": ["55", "56"],
        "I&E": ["57", "58"],
    }

    out = []
    for nombre, lista in grupos.items():
        universo = db.execute(
            select(func.count()).select_from(ApsaProtocol).where(
                ApsaProtocol.load_id == apsa_id,
                ApsaProtocol.disciplina.in_(lista)
            )
        ).scalar() or 0

        abiertos = db.execute(
            select(func.count()).select_from(ApsaProtocol).where(
                ApsaProtocol.load_id == apsa_id,
                ApsaProtocol.disciplina.in_(lista),
                ApsaProtocol.status_bim360 == "ABIERTO"
            )
        ).scalar() or 0

        cerrados = db.execute(
            select(func.count()).select_from(ApsaProtocol).where(
                ApsaProtocol.load_id == apsa_id,
                ApsaProtocol.disciplina.in_(lista),
                ApsaProtocol.status_bim360 == "CERRADO"
            )
        ).scalar() or 0

        # SOLO por coincidencia de código
        aconex = 0
        if aconex_id:
            aconex = db.execute(
                select(func.count(func.distinct(ApsaProtocol.codigo_cmdic)))
                .where(
                    ApsaProtocol.load_id == apsa_id,
                    ApsaProtocol.disciplina.in_(lista),
                    select(1).where(
                        AconexDoc.load_id == aconex_id,
                        AconexDoc.document_no == ApsaProtocol.codigo_cmdic
                    ).exists()
                )
            ).scalar() or 0

        out.append({
            "grupo": nombre,
            "universo": universo,
            "abiertos": abiertos,
            "cerrados": cerrados,
            "aconex": aconex,
        })

    return out

@app.get("/metrics/subsistemas")
def metrics_subsistemas(group: str | None = None, db: Session = Depends(get_db), decoded=Depends(verify_token)):
    apsa_id = _latest_load_id(db, SourceEnum.APSA)
    aconex_id = _latest_load_id(db, SourceEnum.ACONEX)
    if not apsa_id:
        return []

    grupos = {
        "obra": [str(x) for x in range(50, 55)],
        "mecanico": ["55", "56"],
        "ie": ["57", "58"],
    }
    filtro_disc = grupos.get((group or "").lower())

    base_q = (
        select(
            ApsaProtocol.subsistema.label("subsistema"),
            func.count().label("universo"),
            func.sum(case((ApsaProtocol.status_bim360 == "ABIERTO", 1), else_=0)).label("abiertos"),
            func.sum(case((ApsaProtocol.status_bim360 == "CERRADO", 1), else_=0)).label("cerrados"),
        )
        .where(ApsaProtocol.load_id == apsa_id)
        .group_by(ApsaProtocol.subsistema)
    )
    if filtro_disc:
        base_q = base_q.where(ApsaProtocol.disciplina.in_(filtro_disc))

    rows = db.execute(base_q).all()

    # Cargado Aconex por subsistema (SOLO por match de código)
    cargados_map: dict[str, int] = {}
    if aconex_id:
        carg_q = (
            select(
                ApsaProtocol.subsistema,
                func.count(func.distinct(ApsaProtocol.codigo_cmdic))
            )
            .where(
                ApsaProtocol.load_id == apsa_id,
                select(1).where(
                    AconexDoc.load_id == aconex_id,
                    AconexDoc.document_no == ApsaProtocol.codigo_cmdic
                ).exists()
            )
            .group_by(ApsaProtocol.subsistema)
        )
        if filtro_disc:
            carg_q = carg_q.where(ApsaProtocol.disciplina.in_(filtro_disc))

        for sub, cnt in db.execute(carg_q).all():
            cargados_map[sub] = int(cnt or 0)

    out = []
    for sub, universo, abiertos, cerrados in rows:
        cargado = cargados_map.get(sub, 0)
        pendiente_cierre = int(abiertos or 0)            # <- corregido
        pendiente_aconex = int((universo or 0) - (cargado or 0))
        out.append({
            "subsistema": sub,
            "universo": int(universo or 0),
            "abiertos": int(abiertos or 0),
            "cerrados": int(cerrados or 0),
            "pendiente_cierre": pendiente_cierre,
            "cargado_aconex": int(cargado),
            "pendiente_aconex": pendiente_aconex,
        })

    out.sort(key=lambda x: (-x["pendiente_aconex"], x["subsistema"] or ""))
    return out

@app.get("/debug/apsa/disciplinas-distinct")
def debug_apsa_disc(db: Session = Depends(get_db), decoded=Depends(verify_token)):
    apsa_id = _latest_load_id(db, SourceEnum.APSA)
    if not apsa_id:
        return []
    rows = db.execute(
        select(ApsaProtocol.disciplina, func.count())
        .where(ApsaProtocol.load_id == apsa_id)
        .group_by(ApsaProtocol.disciplina)
        .order_by(func.count().desc())
        .limit(30)
    ).all()
    return [{"disciplina": d or "", "count": int(c)} for d, c in rows]

@app.get("/debug/aconex/discipline-function")
def debug_aconex_disc(db: Session = Depends(get_db), decoded=Depends(verify_token)):
    aconex_id = _latest_load_id(db, SourceEnum.ACONEX)
    if not aconex_id:
        return []
    total_by_disc = db.execute(
        select(AconexDoc.discipline, func.count())
        .where(AconexDoc.load_id == aconex_id)
        .group_by(AconexDoc.discipline)
        .order_by(func.count().desc())
    ).all()
    sample_funcs = db.execute(
        select(AconexDoc.function)
        .where(AconexDoc.load_id == aconex_id)
        .limit(5)
    ).all()
    return {
        "discipline_counts": [{"discipline": d or "", "count": int(c)} for d, c in total_by_disc],
        "function_samples": [f[0] for f in sample_funcs]
    }

@app.get("/debug/aconex/unmatched")
def debug_aconex_unmatched(db: Session = Depends(get_db), decoded=Depends(verify_token)):
    apsa_id = _latest_load_id(db, SourceEnum.APSA)
    aconex_id = _latest_load_id(db, SourceEnum.ACONEX)
    if not apsa_id or not aconex_id:
        return {"total_unmatched": 0, "sample": [], "note": "Faltan cargas"}

    # Subconsulta: Aconex DOCs sin match estricto
    sub_no_match_strict = (
        select(AconexDoc.document_no)
        .where(
            AconexDoc.load_id == aconex_id,
            ~select(1).where(
                ApsaProtocol.load_id == apsa_id,
                AconexDoc.document_no == ApsaProtocol.codigo_cmdic
            ).exists()
        )
        .subquery()
    )
    total_no_match_strict = db.execute(
        select(func.count()).select_from(sub_no_match_strict)
    ).scalar() or 0

    # Subconsulta: Aconex DOCs sin match usando normalización (quitando guiones/espacios)
    sub_no_match_norm = (
        select(AconexDoc.document_no)
        .where(
            AconexDoc.load_id == aconex_id,
            ~select(1).where(
                ApsaProtocol.load_id == apsa_id,
                _norm_sql(AconexDoc.document_no) == _norm_sql(ApsaProtocol.codigo_cmdic)
            ).exists()
        )
        .subquery()
    )
    total_no_match_norm = db.execute(
        select(func.count()).select_from(sub_no_match_norm)
    ).scalar() or 0

    sample = [r[0] for r in db.execute(select(sub_no_match_norm.c.document_no).limit(50)).all()]

    return {
        "no_match_strict": int(total_no_match_strict),
        "no_match_normalized": int(total_no_match_norm),
        "sample_normalized_no_match": sample,
        "hint": "Si 'no_match_normalized' baja mucho respecto a 'no_match_strict', conviene usar la comparación normalizada.",
    }

@app.get("/aconex/unmatched")
def aconex_unmatched(
    strict: bool = Query(False, description="Si true, compara sin normalizar"),
    q: str | None = Query(None, description="Filtro por document_no o título (ILIKE)"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    decoded = Depends(verify_token),
):
    apsa_id = _latest_load_id(db, SourceEnum.APSA)
    aconex_id = _latest_load_id(db, SourceEnum.ACONEX)
    if not apsa_id or not aconex_id:
        return {"total": 0, "items": [], "strict": strict}

    left_expr = AconexDoc.document_no if strict else _norm_sql(AconexDoc.document_no)
    right_expr = ApsaProtocol.codigo_cmdic if strict else _norm_sql(ApsaProtocol.codigo_cmdic)

    where_list = [
        AconexDoc.load_id == aconex_id,
        ~select(1).where(
            ApsaProtocol.load_id == apsa_id,
            right_expr == left_expr
        ).exists()
    ]

    if q and q.strip():
        pat = f"%{q.strip()}%"
        where_list.append(or_(AconexDoc.document_no.ilike(pat), AconexDoc.title.ilike(pat)))

    total = db.execute(
        select(func.count()).select_from(AconexDoc).where(*where_list)
    ).scalar() or 0

    rows = db.execute(
        select(
            AconexDoc.document_no,
            AconexDoc.title,
            AconexDoc.function,
            AconexDoc.subsystem_text,
            AconexDoc.revision,
            AconexDoc.file_name,
            AconexDoc.date_received,
        )
        .where(*where_list)
        .order_by(AconexDoc.document_no.asc())
        .limit(limit).offset(offset)
    ).all()

    items = [
        {
            "document_no": r[0],
            "title": r[1],
            "function": r[2],
            "subsystem": r[3],
            "revision": r[4],
            "file_name": r[5],
            "date_received": r[6],
        }
        for r in rows
    ]

    return {"strict": strict, "total": int(total), "items": items}

@app.get("/aconex/unmatched.csv")
def aconex_unmatched_csv(
    strict: bool = Query(False),
    db: Session = Depends(get_db),
    decoded = Depends(require_roles("Admin")),
):
    apsa_id = _latest_load_id(db, SourceEnum.APSA)
    aconex_id = _latest_load_id(db, SourceEnum.ACONEX)
    if not apsa_id or not aconex_id:
        # CSV vacío
        def _iter_empty():
            out = StringIO()
            w = csv.writer(out, delimiter=';')
            w.writerow(["document_no","title","function","subsystem","revision","file_name","date_received"])
            yield out.getvalue()
        return StreamingResponse(_iter_empty(), media_type="text/csv",
                                 headers={"Content-Disposition":"attachment; filename=aconex_unmatched.csv"})

    left_expr = AconexDoc.document_no if strict else _norm_sql(AconexDoc.document_no)
    right_expr = ApsaProtocol.codigo_cmdic if strict else _norm_sql(ApsaProtocol.codigo_cmdic)

    where_list = [
        AconexDoc.load_id == aconex_id,
        ~select(1).where(
            ApsaProtocol.load_id == apsa_id,
            right_expr == left_expr
        ).exists()
    ]

    rows = db.execute(
        select(
            AconexDoc.document_no,
            AconexDoc.title,
            AconexDoc.function,
            AconexDoc.subsystem_text,
            AconexDoc.revision,
            AconexDoc.file_name,
            AconexDoc.date_received,
        ).where(*where_list).order_by(AconexDoc.document_no.asc())
    ).all()

    def _iter_csv():
        out = StringIO()
        w = csv.writer(out, delimiter=';')
        w.writerow(["document_no","title","function","subsystem","revision","file_name","date_received"])
        yield out.getvalue(); out.seek(0); out.truncate(0)
        for r in rows:
            w.writerow([r[0], r[1] or "", r[2] or "", r[3] or "", r[4] or "", r[5] or "", r[6] or ""])
            yield out.getvalue(); out.seek(0); out.truncate(0)

    return StreamingResponse(_iter_csv(), media_type="text/csv",
                             headers={"Content-Disposition":"attachment; filename=aconex_unmatched.csv"})

@app.get("/aconex/duplicates")
def aconex_duplicates(
    strict: bool = Query(False, description="Si true, cuenta duplicados sin normalizar (solo TRIM/UPPER)"),
    db: Session = Depends(get_db),
    decoded = Depends(verify_token),
):
    aconex_id = _latest_load_id(db, SourceEnum.ACONEX)
    if not aconex_id:
        return []

    # clave de agrupación
    key_expr = (
        func.upper(func.trim(AconexDoc.document_no))  # "estricto": solo TRIM/UPPER
        if strict
        else _norm_sql(AconexDoc.document_no)        # normalizado: sin espacios/guiones/underscores
    )

    rows = db.execute(
        select(
            key_expr.label("document_no"),
            func.count().label("count")
        )
        .where(
            AconexDoc.load_id == aconex_id,
            func.length(func.trim(AconexDoc.document_no)) > 0  # ignora vacíos
        )
        .group_by(key_expr)
        .having(func.count() >= 2)
        .order_by(func.count().desc(), key_expr.asc())
    ).all()

    return [{"document_no": (k or ""), "count": int(c or 0)} for (k, c) in rows]

@app.get("/aconex/duplicates.csv")
def aconex_duplicates_csv(
    strict: bool = Query(False, description="Si true, cuenta duplicados sin normalizar (solo TRIM/UPPER)"),
    db: Session = Depends(get_db),
    decoded = Depends(verify_token),
):
    aconex_id = _latest_load_id(db, SourceEnum.ACONEX)
    if not aconex_id:
        return Response(content="document_no;count\n", media_type="text/csv; charset=utf-8")

    key_expr = (
        func.upper(func.trim(AconexDoc.document_no))
        if strict
        else _norm_sql(AconexDoc.document_no)
    )

    rows = db.execute(
        select(
            key_expr.label("document_no"),
            func.count().label("count")
        )
        .where(
            AconexDoc.load_id == aconex_id,
            func.length(func.trim(AconexDoc.document_no)) > 0
        )
        .group_by(key_expr)
        .having(func.count() >= 2)
        .order_by(func.count().desc(), key_expr.asc())
    ).all()

    # arma CSV
    lines = ["document_no;count"]
    for k, c in rows:
        doc = (k or "").replace(";", " ")  # evita romper el CSV
        lines.append(f"{doc};{int(c or 0)}")
    csv_data = "\n".join(lines)

    filename = "aconex_duplicados_strict.csv" if strict else "aconex_duplicados.csv"
    return Response(
        content=csv_data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@app.get("/metrics/subsistemas/changes")
def metrics_subsistemas_changes(
    group: str | None = None,
    db: Session = Depends(get_db),
    decoded=Depends(verify_token),
):
    l1 = _latest_load_id(db, SourceEnum.APSA)
    l0 = _previous_load_id(db, SourceEnum.APSA)
    if not l1 or not l0:
        return []  # si no hay anterior, no hay cambios que reportar

    grupos = {
        "obra": [str(x) for x in range(50, 55)],
        "mecanico": ["55", "56"],
        "ie": ["57", "58"],
    }
    filtro_disc = None
    if group and group.lower() in grupos:
        filtro_disc = grupos[group.lower()]

    def agg_for(load_id: int) -> dict[str, tuple[int,int,int]]:
        q = (
            select(
                ApsaProtocol.subsistema,
                func.count().label("universo"),
                func.sum(case((ApsaProtocol.status_bim360 == "ABIERTO", 1), else_=0)).label("abiertos"),
                func.sum(case((ApsaProtocol.status_bim360 == "CERRADO", 1), else_=0)).label("cerrados"),
            )
            .where(ApsaProtocol.load_id == load_id)
            .group_by(ApsaProtocol.subsistema)
        )
        if filtro_disc:
            q = q.where(ApsaProtocol.disciplina.in_(filtro_disc))
        rows = db.execute(q).all()
        return {
            (sub or ""): (int(u or 0), int(a or 0), int(c or 0))
            for sub, u, a, c in rows
        }

    m1 = agg_for(l1)  # nuevo
    m0 = agg_for(l0)  # anterior

    keys = sorted(set(m1.keys()) | set(m0.keys()), key=lambda s: (s is None, s))
    out = []
    for k in keys:
        u1,a1,c1 = m1.get(k, (0,0,0))
        u0,a0,c0 = m0.get(k, (0,0,0))
        du, da, dc = (u1-u0), (a1-a0), (c1-c0)
        if du or da or dc:
            out.append({
                "subsistema": k or "",
                "universo_prev": u0, "universo_new": u1, "delta_universo": du,
                "abiertos_prev": a0, "abiertos_new": a1, "delta_abiertos": da,
                "cerrados_prev": c0, "cerrados_new": c1, "delta_cerrados": dc,
            })
    return out

@app.get("/metrics/subsistemas/changes.csv")
def metrics_subsistemas_changes_csv(
    group: str | None = None,
    db: Session = Depends(get_db),
    decoded=Depends(verify_token),
):
    # Reutilizamos el cálculo anterior
    from fastapi import Request
    rows = metrics_subsistemas_changes(group=group, db=db, decoded=decoded)

    headers = [
        "subsistema",
        "universo_prev","universo_new","delta_universo",
        "abiertos_prev","abiertos_new","delta_abiertos",
        "cerrados_prev","cerrados_new","delta_cerrados",
    ]
    lines = [";".join(headers)]
    for r in rows:
        vals = [str(r.get(h, "")) for h in headers]
        lines.append(";".join(vals))
    csv_data = "\n".join(lines)

    fname = f"cambios_subsistemas_{(group or 'all')}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )

@app.get("/metrics/changes/summary")
def metrics_changes_summary(
    db: Session = Depends(get_db),
    decoded=Depends(verify_token),
):
    # último y anterior (APSA)
    l1 = _latest_load_id(db, SourceEnum.APSA)
    l0 = _previous_load_id(db, SourceEnum.APSA)
    if not l1 or not l0:
        # Aún no hay histórico para comparar
        new_load = db.execute(select(Load).where(Load.id == l1)).scalar_one_or_none()
        return {
            "has_previous": False,
            "new_loaded_at": new_load.loaded_at.isoformat() if new_load else None,
            "prev_loaded_at": None,
            "changed_count": 0,
        }

    new_load = db.execute(select(Load).where(Load.id == l1)).scalar_one()
    prev_load = db.execute(select(Load).where(Load.id == l0)).scalar_one()

    # --- mismo cálculo que /metrics/subsistemas/changes (sin filtro de grupo) ---
    def agg_for(load_id: int):
        q = (
            select(
                ApsaProtocol.subsistema,
                func.count().label("universo"),
                func.sum(case((ApsaProtocol.status_bim360 == "ABIERTO", 1), else_=0)).label("abiertos"),
                func.sum(case((ApsaProtocol.status_bim360 == "CERRADO", 1), else_=0)).label("cerrados"),
            )
            .where(ApsaProtocol.load_id == load_id)
            .group_by(ApsaProtocol.subsistema)
        )
        rows = db.execute(q).all()
        return {
            (sub or ""): (int(u or 0), int(a or 0), int(c or 0))
            for sub, u, a, c in rows
        }

    m1 = agg_for(l1)  # nuevo
    m0 = agg_for(l0)  # anterior

    changed = 0
    for k in set(m1.keys()) | set(m0.keys()):
        u1,a1,c1 = m1.get(k, (0,0,0))
        u0,a0,c0 = m0.get(k, (0,0,0))
        if (u1-u0) or (a1-a0) or (c1-c0):
            changed += 1

    return {
        "has_previous": True,
        "new_loaded_at": new_load.loaded_at.isoformat(),
        "prev_loaded_at": prev_load.loaded_at.isoformat(),
        "changed_count": int(changed),
        # Tip: el CSV detallado ya lo tienes en /metrics/subsistemas/changes.csv
    }

@app.get("/apsa/options")
def apsa_options(db: Session = Depends(get_db), decoded=Depends(verify_token)):
    apsa_id = _latest_load_id(db, SourceEnum.APSA)
    if not apsa_id:
        return {"disciplinas": [], "subsistemas": []}

    discs = db.execute(
        select(ApsaProtocol.disciplina)
        .where(ApsaProtocol.load_id == apsa_id)
        .group_by(ApsaProtocol.disciplina)
        .order_by(ApsaProtocol.disciplina.asc())
    ).scalars().all()

    subs = db.execute(
        select(ApsaProtocol.subsistema)
        .where(ApsaProtocol.load_id == apsa_id)
        .group_by(ApsaProtocol.subsistema)
        .order_by(ApsaProtocol.subsistema.asc())
    ).scalars().all()

    # limpia nulos/vacíos
    discs = [d for d in discs if (d is not None and str(d).strip() != "")]
    subs  = [s for s in subs  if (s is not None and str(s).strip() != "")]

    return {"disciplinas": discs, "subsistemas": subs}


# --- Listado paginado de protocolos APSA (JSON) ---
@app.get("/apsa/list")
def apsa_list(
    subsistema: str | None = None,
    disciplina: str | None = None,
    q: str | None = None,             # búsqueda libre en codigo/descripcion/tag
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    decoded=Depends(verify_token)
):
    apsa_id = _latest_load_id(db, SourceEnum.APSA)
    if not apsa_id:
        return {"rows": [], "total": 0, "page": page, "page_size": page_size}

    # base query
    base = select(
        ApsaProtocol.id,
        ApsaProtocol.codigo_cmdic,
        ApsaProtocol.descripcion,
        ApsaProtocol.tag,
        ApsaProtocol.subsistema
    ).where(ApsaProtocol.load_id == apsa_id)

    if subsistema:
        base = base.where(ApsaProtocol.subsistema == subsistema)
    if disciplina:
        base = base.where(ApsaProtocol.disciplina == disciplina)
    if q and q.strip():
        like = f"%{q.strip()}%"
        base = base.where(
            or_(
                ApsaProtocol.codigo_cmdic.ilike(like),
                ApsaProtocol.descripcion.ilike(like),
                ApsaProtocol.tag.ilike(like),
            )
        )

    # total
    total = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar() or 0

    # pagina
    page = max(1, int(page))
    page_size = min(500, max(1, int(page_size)))  # hard cap
    offset = (page - 1) * page_size

    rows_db = db.execute(
        base.order_by(ApsaProtocol.subsistema.asc(), ApsaProtocol.codigo_cmdic.asc())
            .limit(page_size)
            .offset(offset)
    ).all()

    rows = []
    for _, cod, desc, tag, subs in rows_db:
        rows.append({
            "document_no": (cod or "").strip(),     # NÚMERO DE DOCUMENTO ACONEX
            "rev": "0",                              # REV. fijo
            "descripcion": (desc or "").strip(),     # DESCRIPCIÓN
            "tag": (str(tag) if tag is not None else "-").strip() or "-",  # TAG
            "subsistema": (subs or "").strip(),      # SUBSISTEMA
        })

    return {"rows": rows, "total": int(total), "page": page, "page_size": page_size}


# --- Export a CSV (respeta filtros) ---
@app.get("/export/apsa.csv")
def export_apsa_csv(
    subsistema: str | None = None,
    disciplina: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    decoded=Depends(verify_token)
):
    apsa_id = _latest_load_id(db, SourceEnum.APSA)
    if not apsa_id:
        raise HTTPException(status_code=400, detail="No hay carga APSA disponible")

    qsel = (
        select(
            ApsaProtocol.codigo_cmdic,
            ApsaProtocol.descripcion,
            ApsaProtocol.tag,
            ApsaProtocol.subsistema
        )
        .where(ApsaProtocol.load_id == apsa_id)
    )
    if subsistema:
        qsel = qsel.where(ApsaProtocol.subsistema == subsistema)
    if disciplina:
        qsel = qsel.where(ApsaProtocol.disciplina == disciplina)
    if q and q.strip():
        like = f"%{q.strip()}%"
        qsel = qsel.where(
            or_(
                ApsaProtocol.codigo_cmdic.ilike(like),
                ApsaProtocol.descripcion.ilike(like),
                ApsaProtocol.tag.ilike(like),
            )
        )

    rows = db.execute(qsel.order_by(ApsaProtocol.subsistema.asc(), ApsaProtocol.codigo_cmdic.asc())).all()

    buf = StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["NÚMERO DE DOCUMENTO ACONEX", "REV.", "DESCRIPCIÓN", "TAG", "SUBSISTEMA"])
    for cod, desc, tag, subs in rows:
        w.writerow([
            (cod or "").strip(),
            "0",
            (desc or "").strip(),
            (str(tag) if tag is not None else "-").strip() or "-",
            (subs or "").strip(),
        ])

    csv_bytes = ("\ufeff" + buf.getvalue()).encode("utf-8")  # BOM para Excel
    fname_parts = []
    if disciplina:  fname_parts.append(f"disc-{disciplina}")
    if subsistema:  fname_parts.append(f"sub-{subsistema.replace('/', '_')}")
    if q and q.strip(): fname_parts.append("q")

    fname = "log_protocolos.csv" if not fname_parts else f"log_protocolos_{'_'.join(fname_parts)}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{fname}"'}
    return StreamingResponse(iter([csv_bytes]), media_type="text/csv; charset=utf-8", headers=headers)