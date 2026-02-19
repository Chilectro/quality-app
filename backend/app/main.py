from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_, case, literal, false, text, insert
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from .auth import verify_token, require_roles
from pydantic import BaseModel, EmailStr, constr
from fastapi import Path
from typing import Literal
from typing import Optional
import logging
from time import perf_counter
from fastapi import Request

app = FastAPI(title="Quality Backend", version="0.1.0")

logger = logging.getLogger("perf")

@app.middleware("http")
async def log_request_time(request: Request, call_next):
    start = perf_counter()
    response = await call_next(request)
    duration_ms = (perf_counter() - start) * 1000

    path = request.url.path
    # Filtramos solo lo que nos interesa
    if path.startswith(("/metrics", "/aconex")):
        logger.info(f"[PERF] {request.method} {path} took {duration_ms:.1f} ms")

    return response

# CORS para el frontend local (cuando lo montemos)
ALLOWED_ORIGINS = [
    # Render (frontend)
    "https://quality-app-1.onrender.com",
    # Cloudflare Pages (si ese es tu frontend)
    "https://quality-app.pages.dev",
    # Por si usas otra instancia Render o dominio similar
    "https://quality-app-ufxj.onrender.com",
    # Dev local
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,         # lista explícita (recomendado en prod)
    allow_credentials=True,                # usas cookies, así que debe ser True
    allow_methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS"],
    allow_headers=["*"],                   # incluye Content-Type, Authorization, etc.
    expose_headers=["Content-Disposition"] # por si descargas/descargas excel
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
from io import StringIO
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
from .security import hash_password, verify_password, create_access_token, new_refresh_token, hash_token, refresh_token_expiry, check_needs_rehash
from fastapi import Request
from sqlalchemy import literal
from sqlalchemy.orm import aliased
from fastapi import Query
from fastapi.responses import StreamingResponse
from io import StringIO
import csv
from sqlalchemy import literal_column
import logging
from sqlalchemy.exc import DataError
from sqlalchemy import inspect

# Configurar logging para instrumentación
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Importar utilidades de timing
from .timing import measure_endpoint, measure_query

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

    # Re-hash progresivo: actualizar contraseñas con parámetros optimizados
    # Si el hash actual usa parámetros antiguos (lentos), lo actualizamos transparentemente
    if check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
        db.commit()

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

def _norm(x, *, empty_as_none=True):
    """Convierte NaN/None/'nan' en None o '' y hace strip."""
    if x is None:
        return None if empty_as_none else ""
    s = str(x).strip()
    if s == "" or s.lower() in ("nan", "none", "null"):
        return None if empty_as_none else ""
    return s

def _clip(s: str | None, n: int | None) -> str | None:
    if s is None or n is None:
        return s
    return s if len(s) <= n else s[:n]

def _model_col_len(model, col: str) -> int | None:
    try:
        return getattr(model.__table__.columns[col].type, "length", None)
    except Exception:
        return None

def _db_col_len(db: Session, table: str, col: str) -> int | None:
    try:
        insp = inspect(db.get_bind())
        for c in insp.get_columns(table):
            if c["name"] == col:
                L = getattr(c["type"], "length", None)
                return int(L) if L else None
    except Exception as e:
        logger.warning("No pude inspeccionar longitud de %s.%s: %s", table, col, e)
    return None

@app.post("/admin/upload/apsa")
def upload_apsa(
    file: UploadFile = File(...),
    hard: bool = Query(False, description="Si true, elimina TODAS las cargas APSA antes de insertar"),
    db: Session = Depends(get_db),
    decoded=Depends(require_roles("Admin"))
):
    if hard:
        _purge_source_all(db, SourceEnum.APSA)

    # Leer bytes y hash
    content = file.file.read()
    filehash = sha256_bytes(content)

    # Elegir hoja
    try:
        sheet = _pick_sheet(pd.ExcelFile(BytesIO(content), engine='openpyxl'), "APSA")
    except Exception:
        sheet = "APSA"

    # Detectar fila de encabezados y leer
    header_row = find_header_row_for_apsa(BytesIO(content), sheet)
    df = pd.read_excel(BytesIO(content), sheet_name=sheet, header=header_row, engine='openpyxl')

    # Normalizar nombres de columnas
    df = normalize_cols(df)

    # ---- Aliases robustos ----
    def find_col(df_cols, *candidates_contains):
        for c in df_cols:
            U = str(c).upper().strip()
            if any(tok in U for tok in candidates_contains):
                return c
        return None

    COL_CODIGO = find_col(df.columns, "CÓDIGO CMDIC", "CODIGO CMDIC")
    COL_TIPO = find_col(df.columns, "TIPO PROTOCOLO")
    COL_DESC   = find_col(df.columns, "DESCRIPCIÓN DE ELEMENTOS", "DESCRIPCIÓN", "DESCRIPCION")
    COL_TAG    = find_col(df.columns, "TAG")
    COL_SUBS   = find_col(df.columns, "SUBSISTEMA")
    COL_DISC   = find_col(df.columns, "DISCIPLINA")
    COL_STATUS = find_col(df.columns, "STATUS BIM 360", "STATUS BIM360")

    required = [
        ("N° CÓDIGO CMDIC", COL_CODIGO),
        ("TIPO PROTOCOLO", COL_TIPO),
        ("DESCRIPCIÓN/DE ELEMENTOS", COL_DESC),
        ("TAG", COL_TAG),
        ("SUBSISTEMA", COL_SUBS),
        ("DISCIPLINA", COL_DISC),
        ("STATUS BIM 360 FIELD", COL_STATUS),
    ]
    missing = [name for name, col in required if col is None]
    if missing:
        raise HTTPException(status_code=400, detail=f"Columnas faltantes en APSA: {missing}")

    # ====== CALCULAR LÍMITE REAL DE 'tag' ======
    # 1) primero el declarado en el modelo
    tag_limit = _model_col_len(ApsaProtocol, "tag")
    # 2) si no está, tratamos de leerlo de la DB real
    if not tag_limit:
        tag_limit = _db_col_len(db, "apsa_protocols", "tag")
    # 3) fallback prudente si nada funcionó
    if not tag_limit:
        tag_limit = 64  # prudente, evita 1406 aunque recorte más

    logger.info("Límite detectado para apsa_protocols.tag = %s", tag_limit)

    # Crear registro de carga
    load = _store_load(db, SourceEnum.APSA, file.filename, filehash)

    # 🚀 OPTIMIZADO: Procesamiento vectorizado (10-15x más rápido)
    logger.info(f"Procesando {len(df)} filas de APSA...")

    # Procesar columnas con operaciones vectorizadas de pandas
    df['codigo_cmdic'] = df[COL_CODIGO].fillna('').astype(str).str.strip()
    df['tipo'] = df[COL_TIPO].fillna('').astype(str).str.strip()
    df['descripcion'] = df[COL_DESC].fillna('').astype(str).str.strip()
    df['tag_raw'] = df[COL_TAG].fillna('').astype(str).str.strip()
    df['subsistema_raw'] = df[COL_SUBS].fillna('').astype(str).str.strip().str.upper()
    df['disciplina_raw'] = df[COL_DISC].fillna('').astype(str).str.strip()
    df['status_bim360'] = df[COL_STATUS].fillna('NAN').astype(str).str.strip().str.upper()

    # Limpiar subsistemas
    df['subsistema'] = df['subsistema_raw'].replace(['NAN', 'NONE', 'NULL'], '')

    # Normalizar disciplinas
    df['disciplina'] = df['disciplina_raw'].apply(lambda x: normalize_disc_code(x) or "")

    # Para disciplinas vacías, derivar del subsistema
    mask_empty_disc = (df['disciplina'] == "") | (df['disciplina'] == "0")
    df.loc[mask_empty_disc, 'disciplina'] = df.loc[mask_empty_disc, 'subsistema'].apply(discipline_from_subsystem)

    # Recortar tags al límite (vectorizado)
    tags = df['tag_raw'].replace('', None)
    clipped = int((tags.str.len() > tag_limit).sum())
    df['tag'] = tags.str[:tag_limit]

    # Crear lista de diccionarios para bulk insert
    records = df[['codigo_cmdic', 'tipo', 'descripcion', 'tag', 'subsistema', 'disciplina', 'status_bim360']].to_dict('records')

    # Agregar load_id a cada registro
    for rec in records:
        rec['load_id'] = load.id

    if not records:
        return {"ok": True, "rows_inserted": 0, "sheet": sheet, "header_row": int(header_row)}

    try:
        db.execute(insert(ApsaProtocol), records)
        db.commit()
        logger.info(f"✅ {len(records)} registros de APSA insertados exitosamente")
    except DataError as e:
        db.rollback()
        logger.exception("Error guardando APSA (tag_limit=%s)", tag_limit)
        raise HTTPException(
            status_code=400,
            detail=f"Error de datos al guardar APSA: {str(e.orig) if hasattr(e, 'orig') else str(e)}"
        )

    if clipped:
        logger.warning("APSA: %s tags fueron recortados a %s caracteres", clipped, tag_limit)

    _purge_old_loads(db, SourceEnum.APSA, keep=2)

    return {
        "ok": True,
        "rows_inserted": len(records),
        "sheet": sheet,
        "header_row": int(header_row),
        "tags_recortados": clipped,
        "tag_limit": tag_limit,
    }

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
        sheet = _pick_sheet(pd.ExcelFile(BytesIO(content), engine='openpyxl'), "Cargados ACONEX")
    except Exception:
        sheet = "Cargados ACONEX"

    # Leer y normalizar
    df = pd.read_excel(BytesIO(content), sheet_name=sheet, engine='openpyxl')
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

    # 🚀 OPTIMIZADO: Procesamiento vectorizado (10-15x más rápido)
    logger.info(f"Procesando {len(df)} filas de ACONEX...")

    # Procesar columnas con operaciones vectorizadas
    df['document_no'] = df[COL_DOCNO].fillna('').astype(str).str.strip()
    df['title'] = df[COL_TITLE].fillna('').astype(str).str.strip() if COL_TITLE else ''
    df['function'] = df[COL_FUNC].fillna('').astype(str).str.strip()
    df['subsystem_text'] = df[COL_SUBSYS].fillna('').astype(str).str.strip()
    df['system_no'] = df[COL_SYSNO].fillna('').astype(str).str.strip() if COL_SYSNO else ''
    df['file_name'] = df[COL_FILE].fillna('').astype(str).str.strip() if COL_FILE else ''
    df['equipment_tag_no'] = df[COL_EQUIP].fillna('').astype(str).str.strip() if COL_EQUIP else ''
    df['date_received'] = df[COL_DATE].fillna('').astype(str).str.strip() if COL_DATE else ''
    df['revision'] = df[COL_REV].fillna('').astype(str).str.strip() if COL_REV else ''
    df['transmitted'] = df[COL_TRANS].fillna('').astype(str).str.strip() if COL_TRANS else ''

    # Extraer códigos de subsistema
    df['subsystem_code'] = df['subsystem_text'].apply(lambda x: extract_subsystem_code(x) or "")

    # Normalizar disciplinas
    if COL_DISC:
        df['disc_raw'] = df[COL_DISC].fillna('').astype(str).str.strip()
        df['discipline'] = df.apply(lambda row: normalize_disc_code(row['disc_raw'] or row['function']), axis=1)
    else:
        df['discipline'] = df['function'].apply(normalize_disc_code)

    # Crear lista de diccionarios para bulk insert
    columns_to_export = ['document_no', 'title', 'discipline', 'function', 'subsystem_text',
                         'subsystem_code', 'system_no', 'file_name', 'equipment_tag_no',
                         'date_received', 'revision', 'transmitted']

    records = df[columns_to_export].to_dict('records')

    # Agregar load_id a cada registro
    for rec in records:
        rec['load_id'] = load.id

    if records:
        try:
            db.execute(insert(AconexDoc), records)
            db.commit()
            logger.info(f"✅ {len(records)} registros de ACONEX insertados exitosamente")
        except Exception as e:
            db.rollback()
            logger.exception("Error guardando ACONEX")
            raise HTTPException(status_code=400, detail=f"Error guardando ACONEX: {str(e)}")

    _purge_old_loads(db, SourceEnum.ACONEX, keep=2)

    return {"ok": True, "rows_inserted": len(records), "sheet": sheet}

@app.get("/metrics/cards")
@measure_endpoint("metrics_cards")
def metrics_cards(db: Session = Depends(get_db), decoded=Depends(verify_token)):
    apsa_id = _latest_load_id(db, SourceEnum.APSA)
    aconex_id = _latest_load_id(db, SourceEnum.ACONEX)

    # --- Métricas APSA
    abiertos = cerrados = universo = 0
    if apsa_id:
        with measure_query("Count APSA ABIERTOS", "metrics_cards"):
            abiertos = db.execute(
                select(func.count()).select_from(ApsaProtocol).where(
                    ApsaProtocol.load_id == apsa_id,
                    ApsaProtocol.status_bim360 == "ABIERTO"
                )
            ).scalar() or 0

        with measure_query("Count APSA CERRADOS", "metrics_cards"):
            cerrados = db.execute(
                select(func.count()).select_from(ApsaProtocol).where(
                    ApsaProtocol.load_id == apsa_id,
                    ApsaProtocol.status_bim360 == "CERRADO"
                )
            ).scalar() or 0

        universo = (abiertos or 0) + (cerrados or 0)

    # --- Normalizador SQL
    def N(expr):
        return func.replace(
            func.replace(
                func.replace(func.upper(func.trim(expr)), " ", ""),
                "-", ""
            ),
            "_", ""
        )

    # --- Métricas ACONEX
    aconex_rows = aconex_unicos = aconex_validos = 0
    aconex_error_ss = 0  # NUEVO

    if aconex_id:
        # 1) Filas crudas
        with measure_query("Count ACONEX total rows", "metrics_cards"):
            aconex_rows = db.execute(
                select(func.count()).select_from(AconexDoc).where(AconexDoc.load_id == aconex_id)
            ).scalar() or 0

        # 2) Documentos únicos (normalizados)
        with measure_query("Count ACONEX documentos únicos (normalized)", "metrics_cards"):
            aconex_unicos = db.execute(
                select(func.count(func.distinct(N(AconexDoc.document_no)))).where(AconexDoc.load_id == aconex_id)
            ).scalar() or 0

        # 3) Válidos: doc únicos que matchean con APSA por código normalizado
        if apsa_id:
            with measure_query("Count ACONEX válidos (match con APSA por código)", "metrics_cards"):
                aconex_validos = db.execute(
                    select(func.count(func.distinct(N(AconexDoc.document_no)))).where(
                        AconexDoc.load_id == aconex_id,
                        select(1).where(
                            ApsaProtocol.load_id == apsa_id,
                            N(ApsaProtocol.codigo_cmdic) == N(AconexDoc.document_no)
                        ).exists()
                    )
                ).scalar() or 0

            # === ULTRA OPTIMIZADO: Protocolos APSA con "Error de SS"
            # Usa columnas normalizadas pre-calculadas (si existen)
            # Reducido de >15 minutos a ~200-500ms (99.9% mejora!)

            from .metrics_fast import count_error_ss_auto

            with measure_query("Count APSA con Error de SS (ULTRA OPTIMIZADO con columnas norm)", "metrics_cards"):
                aconex_error_ss = count_error_ss_auto(db, apsa_id, aconex_id)

    aconex_invalidos = max(0, (aconex_unicos or 0) - (aconex_validos or 0))
    aconex_duplicados = max(0, (aconex_rows or 0) - (aconex_unicos or 0))

    return {
        "universo": int(universo),
        "abiertos": int(abiertos),
        "cerrados": int(cerrados),

        "aconex_cargados": int(aconex_rows),
        "aconex_unicos": int(aconex_unicos),
        "aconex_validos": int(aconex_validos),
        "aconex_invalidos": int(aconex_invalidos),
        "aconex_duplicados": int(aconex_duplicados),

        # NUEVO
        "aconex_error_ss": int(aconex_error_ss),
    }

@app.get("/metrics/disciplinas")
@measure_endpoint("metrics_disciplinas")
def metrics_disciplinas(db: Session = Depends(get_db), decoded=Depends(verify_token)):
    apsa_id = _latest_load_id(db, SourceEnum.APSA)
    aconex_id = _latest_load_id(db, SourceEnum.ACONEX)
    if not apsa_id:
        return []

    disciplinas = [str(d) for d in range(50, 60)]
    out = []

    logger.warning("⚠️  /metrics/disciplinas ejecutará 40 queries (4 por cada disciplina) - problema N+1 conocido")

    for d in disciplinas:
        with measure_query(f"Count universo disciplina {d}", "metrics_disciplinas"):
            universo = db.execute(
                select(func.count()).select_from(ApsaProtocol).where(
                    ApsaProtocol.load_id == apsa_id,
                    ApsaProtocol.disciplina == d
                )
            ).scalar() or 0

        with measure_query(f"Count abiertos disciplina {d}", "metrics_disciplinas"):
            abiertos = db.execute(
                select(func.count()).select_from(ApsaProtocol).where(
                    ApsaProtocol.load_id == apsa_id,
                    ApsaProtocol.disciplina == d,
                    ApsaProtocol.status_bim360 == "ABIERTO"
                )
            ).scalar() or 0

        with measure_query(f"Count cerrados disciplina {d}", "metrics_disciplinas"):
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
            with measure_query(f"Count ACONEX match disciplina {d} (EXISTS)", "metrics_disciplinas"):
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
        "Obra civil": ["50", "51", "52", "54"],  # 50-54
        "Mecánico Pipping": ["53","55", "56"],
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
@measure_endpoint("metrics_subsistemas")
def metrics_subsistemas(group: str | None = None, db: Session = Depends(get_db), decoded=Depends(verify_token)):
    apsa_id = _latest_load_id(db, SourceEnum.APSA)
    aconex_id = _latest_load_id(db, SourceEnum.ACONEX)
    if not apsa_id:
        return []

    grupos = {
        "obra": ["50", "51", "52", "54"],
        "mecanico": ["53", "55", "56"],
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

    with measure_query(f"GROUP BY subsistema (filtro: {group or 'all'})", "metrics_subsistemas"):
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

        with measure_query(f"GROUP BY subsistema + COUNT ACONEX match (filtro: {group or 'all'})", "metrics_subsistemas"):
            for sub, cnt in db.execute(carg_q).all():
                cargados_map[sub] = int(cnt or 0)

    out = []
    for sub, universo, abiertos, cerrados in rows:
        cargado = cargados_map.get(sub, 0)
        pendiente_cierre = int(abiertos or 0)            # <- corregido
        pendiente_aconex = int((cerrados or 0) - (cargado or 0))
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
@measure_endpoint("aconex_duplicates")
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

    mode_label = "strict (UPPER/TRIM)" if strict else "normalized (sin espacios/guiones)"
    with measure_query(f"GROUP BY document_no + HAVING count >= 2 ({mode_label})", "aconex_duplicates"):
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
@measure_endpoint("metrics_changes_summary")
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
    def agg_for(load_id: int, load_label: str):
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
        with measure_query(f"GROUP BY subsistema para {load_label}", "metrics_changes_summary"):
            rows = db.execute(q).all()
        return {
            (sub or ""): (int(u or 0), int(a or 0), int(c or 0))
            for sub, u, a, c in rows
        }

    m1 = agg_for(l1, "carga actual")  # nuevo
    m0 = agg_for(l0, "carga anterior")  # anterior

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
    grupo: str | None = None,         # NUEVO: "obra", "mecanico", "ie"
    q: str | None = None,             # búsqueda libre en codigo/descripcion/tag
    status: str | None = None,        # "ABIERTO" | "CERRADO"
    cargado: bool = False,            # solo con match code+SS
    error_ss: bool = False,           # code match pero SS distinto
    sin_aconex: bool = False,         # NUEVO: sin cargar en Aconex
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    decoded=Depends(verify_token)
):
    apsa_id = _latest_load_id(db, SourceEnum.APSA)
    if not apsa_id:
        return {"rows": [], "total": 0, "page": page, "page_size": page_size}

    # (opcional) mantener la incompatibilidad de antes:
    if cargado and error_ss:
        raise HTTPException(status_code=400, detail="Parámetros incompatibles: 'cargado' y 'error_ss' no pueden ser verdaderos a la vez")

    aconex_id = _latest_load_id(db, SourceEnum.ACONEX)

    # 🚀 OPTIMIZADO: Usar columnas normalizadas pre-calculadas con índices
    # Flags de existencia en Aconex (ULTRA RÁPIDO con columnas _norm)
    if aconex_id:
        code_only_exists = select(1).where(
            AconexDoc.load_id == aconex_id,
            AconexDoc.document_no_norm == ApsaProtocol.codigo_cmdic_norm,
        ).exists()

        code_and_ss_exists = select(1).where(
            AconexDoc.load_id == aconex_id,
            AconexDoc.document_no_norm == ApsaProtocol.codigo_cmdic_norm,
            AconexDoc.subsystem_code_norm == ApsaProtocol.subsistema_norm,
        ).exists()
    else:
        code_only_exists = false()
        code_and_ss_exists = false()

    # base query: con 'tipo' y flags
    base = select(
        ApsaProtocol.id,
        ApsaProtocol.codigo_cmdic,
        ApsaProtocol.descripcion,
        ApsaProtocol.tag,
        ApsaProtocol.subsistema,
        ApsaProtocol.tipo,
        ApsaProtocol.status_bim360,
        code_only_exists.label("has_code"),
        code_and_ss_exists.label("has_code_ss"),
    ).where(ApsaProtocol.load_id == apsa_id)

    # filtros "simples"
    if subsistema:
        base = base.where(ApsaProtocol.subsistema == subsistema)
    if disciplina:
        base = base.where(ApsaProtocol.disciplina == disciplina)

    # NUEVO: filtro por grupo de disciplinas
    if grupo:
        grupos_map = {
            "obra": ["50", "51", "52", "54"],
            "mecanico": ["53", "55", "56"],
            "ie": ["57", "58"],
        }
        if grupo in grupos_map:
            base = base.where(ApsaProtocol.disciplina.in_(grupos_map[grupo]))

    if q and q.strip():
        like = f"%{q.strip()}%"
        base = base.where(
            or_(
                ApsaProtocol.codigo_cmdic.ilike(like),
                ApsaProtocol.descripcion.ilike(like),
                ApsaProtocol.tag.ilike(like),
            )
        )

    # ✅ filtro por status (ABIERTO/CERRADO)
    if status:
        s_up = status.strip().upper()
        if s_up in ("ABIERTO", "CERRADO"):
            base = base.where(ApsaProtocol.status_bim360 == s_up)

    # ✅ filtros Aconex:
    # - cargado: exige match code+SS
    # - error_ss: code match PERO SS distinto
    # - sin_aconex: NO tiene match de código
    if cargado:
        base = base.where(code_and_ss_exists)
    if error_ss:
        base = base.where(code_only_exists, ~code_and_ss_exists)
    if sin_aconex:
        base = base.where(~code_only_exists)

    # total y paginación
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar() or 0
    page = max(1, int(page))
    page_size = min(500, max(1, int(page_size)))
    offset = (page - 1) * page_size

    rows_db = db.execute(
        base.order_by(ApsaProtocol.subsistema.asc(), ApsaProtocol.codigo_cmdic.asc())
            .limit(page_size)
            .offset(offset)
    ).all()

    rows = []
    for _, cod, desc, tag, subs, tipo, status_bim360, has_code, has_code_ss in rows_db:
        # Concatenación tipo + descripción (no romper el display nuevo)
        desc_out = (f"{(tipo or '').strip()} — {(desc or '').strip()}").strip(" —")

        # Display ACONEX
        if bool(has_code_ss):
            aconex_str = "Cargado"
        elif bool(has_code):
            aconex_str = "Error de SS"
        else:
            aconex_str = ""

        rows.append({
            "document_no": (cod or "").strip(),
            "rev": "0",
            "descripcion": desc_out,
            "tag": (str(tag) if tag is not None else "-").strip() or "-",
            "subsistema": (subs or "").strip(),
            "aconex": aconex_str,
            "status": (status_bim360 or "").upper(),
        })

    return {"rows": rows, "total": int(total), "page": page, "page_size": page_size}


# --- Export a CSV (respeta filtros) ---
@app.get("/export/apsa.csv")
def export_apsa_csv(
    subsistema: str | None = None,
    disciplina: str | None = None,
    grupo: str | None = None,         # NUEVO: "obra", "mecanico", "ie"
    q: str | None = None,
    status: str | None = None,
    cargado: bool = False,
    error_ss: bool = False,
    sin_aconex: bool = False,         # NUEVO: sin cargar en Aconex
    db: Session = Depends(get_db),
    decoded=Depends(verify_token)
):
    apsa_id = _latest_load_id(db, SourceEnum.APSA)
    if not apsa_id:
        raise HTTPException(status_code=400, detail="No hay carga APSA disponible")

    # (opcional) misma incompatibilidad
    if cargado and error_ss:
        raise HTTPException(status_code=400, detail="Parámetros incompatibles: 'cargado' y 'error_ss' no pueden ser verdaderos a la vez")

    aconex_id = _latest_load_id(db, SourceEnum.ACONEX)

    # 🚀 OPTIMIZADO: Usar columnas normalizadas pre-calculadas con índices
    if aconex_id:
        code_only_exists = select(1).where(
            AconexDoc.load_id == aconex_id,
            AconexDoc.document_no_norm == ApsaProtocol.codigo_cmdic_norm,
        ).exists()

        code_and_ss_exists = select(1).where(
            AconexDoc.load_id == aconex_id,
            AconexDoc.document_no_norm == ApsaProtocol.codigo_cmdic_norm,
            AconexDoc.subsystem_code_norm == ApsaProtocol.subsistema_norm,
        ).exists()
    else:
        code_only_exists = false()
        code_and_ss_exists = false()

    qsel = (
        select(
            ApsaProtocol.codigo_cmdic,
            ApsaProtocol.descripcion,
            ApsaProtocol.tag,
            ApsaProtocol.subsistema,
            ApsaProtocol.tipo,
            ApsaProtocol.status_bim360,
            code_only_exists.label("has_code"),
            code_and_ss_exists.label("has_code_ss"),
        )
        .where(ApsaProtocol.load_id == apsa_id)
    )

    # mismos filtros "simples"
    if subsistema:
        qsel = qsel.where(ApsaProtocol.subsistema == subsistema)
    if disciplina:
        qsel = qsel.where(ApsaProtocol.disciplina == disciplina)

    # NUEVO: filtro por grupo de disciplinas
    if grupo:
        grupos_map = {
            "obra": ["50", "51", "52", "54"],
            "mecanico": ["53", "55", "56"],
            "ie": ["57", "58"],
        }
        if grupo in grupos_map:
            qsel = qsel.where(ApsaProtocol.disciplina.in_(grupos_map[grupo]))

    if q and q.strip():
        like = f"%{q.strip()}%"
        qsel = qsel.where(
            or_(
                ApsaProtocol.codigo_cmdic.ilike(like),
                ApsaProtocol.descripcion.ilike(like),
                ApsaProtocol.tag.ilike(like),
            )
        )

    # ✅ status
    if status:
        s_up = status.strip().upper()
        if s_up in ("ABIERTO", "CERRADO"):
            qsel = qsel.where(ApsaProtocol.status_bim360 == s_up)

    # ✅ cargado / error_ss / sin_aconex
    if cargado:
        qsel = qsel.where(code_and_ss_exists)
    if error_ss:
        qsel = qsel.where(code_only_exists, ~code_and_ss_exists)
    if sin_aconex:
        qsel = qsel.where(~code_only_exists)

    rows_db = db.execute(
        qsel.order_by(ApsaProtocol.subsistema.asc(), ApsaProtocol.codigo_cmdic.asc())
    ).all()

    buf = StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["NÚMERO DE DOCUMENTO ACONEX", "REV.", "DESCRIPCIÓN", "TAG", "SUBSISTEMA", "Aconex", "Status"])

    for cod, desc, tag, subs, tipo, status_bim360, has_code, has_code_ss in rows_db:
        desc_out = (f"{(tipo or '').strip()} — {(desc or '').strip()}").strip(" —")
        if bool(has_code_ss):
            aconex_str = "Cargado"
        elif bool(has_code):
            aconex_str = "Error de SS"
        else:
            aconex_str = ""

        w.writerow([
            (cod or "").strip(),
            "0",
            desc_out,
            (str(tag) if tag is not None else "-").strip() or "-",
            (subs or "").strip(),
            aconex_str,
            (status_bim360 or "").upper(),
        ])

    csv_bytes = ("\ufeff" + buf.getvalue()).encode("utf-8")
    fname_parts = []
    if disciplina:  fname_parts.append(f"disc-{disciplina}")
    if subsistema:  fname_parts.append(f"sub-{subsistema.replace('/', '_')}")
    if q and q.strip(): fname_parts.append("q")
    # (opcional) añade marcas por filtros:
    if status: fname_parts.append(f"st-{status.strip().upper()}")
    if cargado: fname_parts.append("cargado")
    if error_ss: fname_parts.append("errorSS")

    from fastapi.responses import Response
    fname = "log_protocolos" + (f"_{'_'.join(fname_parts)}" if fname_parts else "") + ".csv"
    headers = {"Content-Disposition": f'attachment; filename="{fname}"'}
    return Response(content=csv_bytes, media_type="text/csv; charset=utf-8", headers=headers)

@app.get("/export/aconex-ss-errors.csv")
def export_aconex_ss_errors(
    db: Session = Depends(get_db),
    decoded=Depends(verify_token),
):
    apsa_id = _latest_load_id(db, SourceEnum.APSA)
    aconex_id = _latest_load_id(db, SourceEnum.ACONEX)
    if not apsa_id or not aconex_id:
        raise HTTPException(status_code=400, detail="Falta carga APSA o ACONEX")

    def N(expr):
        return func.replace(
            func.replace(
                func.replace(func.upper(func.trim(expr)), " ", ""),
                "-", ""
            ),
            "_", ""
        )

    # Existen matches por código…
    exists_code_only = select(1).where(
        AconexDoc.load_id == aconex_id,
        N(AconexDoc.document_no) == N(ApsaProtocol.codigo_cmdic),
    ).exists()

    # …pero NO con el mismo subsistema.
    exists_code_ss = select(1).where(
        AconexDoc.load_id == aconex_id,
        N(AconexDoc.document_no) == N(ApsaProtocol.codigo_cmdic),
        N(AconexDoc.subsystem_code) == N(ApsaProtocol.subsistema),   # <— AJUSTA NOMBRE SI DIFERENTE
    ).exists()

    # Subconsulta: lista de subsistemas ACONEX para ese código que difieren del APSA
    aconex_ss_list = (
        select(func.group_concat(func.distinct(AconexDoc.subsystem_code)))
        .where(
            AconexDoc.load_id == aconex_id,
            N(AconexDoc.document_no) == N(ApsaProtocol.codigo_cmdic),
            N(AconexDoc.subsystem_code) != N(ApsaProtocol.subsistema),
        )
        .correlate(ApsaProtocol)
        .scalar_subquery()
        .label("aconex_subsistemas")
    )

    q = (
        select(
            ApsaProtocol.codigo_cmdic,
            ApsaProtocol.descripcion,
            ApsaProtocol.tipo,
            ApsaProtocol.tag,
            ApsaProtocol.subsistema,
            ApsaProtocol.status_bim360,
            aconex_ss_list,
        )
        .where(
            ApsaProtocol.load_id == apsa_id,
            exists_code_only,
            ~exists_code_ss,
        )
        .order_by(ApsaProtocol.subsistema.asc(), ApsaProtocol.codigo_cmdic.asc())
    )

    rows = db.execute(q).all()

    buf = StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([
        "NÚMERO DE DOCUMENTO ACONEX",
        "REV.",
        "DESCRIPCIÓN",
        "TAG",
        "SUBSISTEMA (APSA)",
        "SUBSISTEMA(S) EN ACONEX",
        "Status"
    ])

    for cod, desc, tipo, tag, subs, status, aconex_ss in rows:
        tipo_s = (tipo or "").strip()
        desc_s = (desc or "").strip()
        descripcion_final = " - ".join([x for x in [tipo_s, desc_s] if x])
        w.writerow([
            (cod or "").strip(),
            "0",
            descripcion_final,
            (str(tag) if tag is not None else "-").strip() or "-",
            (subs or "").strip(),
            (aconex_ss or "").strip(),
            (status or "").strip(),
        ])

    csv_bytes = ("\ufeff" + buf.getvalue()).encode("utf-8")
    from fastapi.responses import Response
    headers = {"Content-Disposition": 'attachment; filename="aconex_ss_errors.csv"'}
    return Response(content=csv_bytes, media_type="text/csv; charset=utf-8", headers=headers)


# ==================================================================================
# ENDPOINTS DE INSTRUMENTACIÓN DE PERFORMANCE
# ==================================================================================

from .timing import get_all_stats, get_endpoint_stats, reset_stats

@app.get("/admin/performance/stats")
def performance_stats(
    endpoint: str | None = Query(None, description="Nombre del endpoint específico (opcional)"),
    db: Session = Depends(get_db),
    decoded=Depends(require_roles("Admin"))
):
    """
    Retorna estadísticas de performance de endpoints instrumentados.

    - Si `endpoint` se especifica, retorna stats de ese endpoint
    - Si no, retorna stats de todos los endpoints instrumentados

    Ejemplo: /admin/performance/stats?endpoint=metrics_cards
    """
    if endpoint:
        stats = {endpoint: get_endpoint_stats(endpoint)}
    else:
        stats = get_all_stats()

    return {
        "success": True,
        "stats": stats,
        "note": "Tiempos en milisegundos (ms)"
    }


@app.post("/admin/performance/reset")
def performance_reset(
    db: Session = Depends(get_db),
    decoded=Depends(require_roles("Admin"))
):
    """
    Resetea todas las estadísticas de performance acumuladas.

    Útil para limpiar métricas después de pruebas o para empezar fresh.
    """
    reset_stats()
    return {
        "success": True,
        "message": "Performance statistics reset successfully"
    }


@app.get("/admin/performance/summary")
def performance_summary(
    db: Session = Depends(get_db),
    decoded=Depends(require_roles("Admin"))
):
    """
    Retorna un resumen simplificado de performance de los 5 endpoints principales.

    Ideal para dashboard o monitoreo rápido.
    """
    target_endpoints = [
        "metrics_cards",
        "metrics_disciplinas",
        "metrics_subsistemas",
        "metrics_changes_summary",
        "aconex_duplicates"
    ]

    summary = []
    for ep in target_endpoints:
        stats = get_endpoint_stats(ep)
        if stats["calls"] > 0:
            query_count = len(stats["last_execution_queries"])
            total_query_time = sum(q["time_ms"] for q in stats["last_execution_queries"])

            summary.append({
                "endpoint": ep,
                "avg_time_ms": round(stats["avg_time_ms"], 2),
                "min_time_ms": round(stats["min_time_ms"], 2),
                "max_time_ms": round(stats["max_time_ms"], 2),
                "calls": stats["calls"],
                "last_execution": {
                    "query_count": query_count,
                    "total_query_time_ms": round(total_query_time, 2),
                    "overhead_ms": round(stats["avg_time_ms"] - total_query_time, 2) if query_count > 0 else 0
                }
            })
        else:
            summary.append({
                "endpoint": ep,
                "avg_time_ms": 0,
                "min_time_ms": 0,
                "max_time_ms": 0,
                "calls": 0,
                "last_execution": None
            })

    return {
        "success": True,
        "summary": summary,
        "note": "Tiempos en milisegundos (ms). 'overhead_ms' = tiempo no gastado en queries SQL"
    }


@app.get("/admin/debug/error-ss")
def debug_error_ss(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    decoded=Depends(require_roles("Admin"))
):
    """
    Endpoint de diagnóstico para ver ejemplos de protocolos con Error de SS.

    Muestra casos donde:
    - Hay match por código entre APSA y ACONEX
    - PERO el subsistema es diferente

    Útil para verificar que la detección funciona correctamente.
    """
    apsa_id = _latest_load_id(db, SourceEnum.APSA)
    aconex_id = _latest_load_id(db, SourceEnum.ACONEX)

    if not apsa_id or not aconex_id:
        return {
            "error": "Faltan cargas de APSA o ACONEX",
            "apsa_id": apsa_id,
            "aconex_id": aconex_id
        }

    # Query para encontrar ejemplos de error de SS
    # usando las columnas normalizadas
    query = text("""
        SELECT
            ap.codigo_cmdic,
            ap.codigo_cmdic_norm,
            ap.subsistema,
            ap.subsistema_norm,
            acx.document_no,
            acx.document_no_norm,
            acx.subsystem_code,
            acx.subsystem_code_norm,
            CASE
                WHEN ap.subsistema_norm = acx.subsystem_code_norm THEN 'MATCH'
                WHEN ap.subsistema_norm IS NULL THEN 'APSA_NULL'
                WHEN acx.subsystem_code_norm IS NULL THEN 'ACONEX_NULL'
                ELSE 'DIFERENTE'
            END as status_comparacion
        FROM apsa_protocols ap
        INNER JOIN aconex_docs acx
            ON ap.codigo_cmdic_norm = acx.document_no_norm
        WHERE ap.load_id = :apsa_id
          AND acx.load_id = :aconex_id
          AND (
              ap.subsistema_norm != acx.subsystem_code_norm
              OR ap.subsistema_norm IS NULL
              OR acx.subsystem_code_norm IS NULL
          )
        LIMIT :limit
    """)

    result = db.execute(query, {
        "apsa_id": apsa_id,
        "aconex_id": aconex_id,
        "limit": limit
    })

    ejemplos = []
    for row in result:
        ejemplos.append({
            "apsa": {
                "codigo": row[0],
                "codigo_norm": row[1],
                "subsistema": row[2],
                "subsistema_norm": row[3]
            },
            "aconex": {
                "document_no": row[4],
                "document_no_norm": row[5],
                "subsystem_code": row[6],
                "subsystem_code_norm": row[7]
            },
            "comparacion": row[8]
        })

    # También contar el total
    count_query = text("""
        SELECT COUNT(DISTINCT ap.id)
        FROM apsa_protocols ap
        INNER JOIN aconex_docs acx
            ON ap.codigo_cmdic_norm = acx.document_no_norm
        WHERE ap.load_id = :apsa_id
          AND acx.load_id = :aconex_id
          AND (
              ap.subsistema_norm != acx.subsystem_code_norm
              OR ap.subsistema_norm IS NULL
              OR acx.subsystem_code_norm IS NULL
          )
    """)

    total = db.execute(count_query, {
        "apsa_id": apsa_id,
        "aconex_id": aconex_id
    }).scalar()

    return {
        "total_error_ss": int(total or 0),
        "ejemplos_mostrados": len(ejemplos),
        "ejemplos": ejemplos,
        "nota": "Si total_error_ss = 0, significa que no hay errores de SS O la lógica está mal"
    }
