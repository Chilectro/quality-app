"""
Versiones optimizadas de queries de métricas.
Estas funciones reemplazan queries lentas con subconsultas correlacionadas
por versiones optimizadas con JOINs.
"""
from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.orm import Session
from .models.apsa_protocol import ApsaProtocol
from .models.aconex_doc import AconexDoc


def _norm_sql(expr):
    """Normalización SQL: UPPER(TRIM(REPLACE(REPLACE(REPLACE(...)))).

    Nota: Esta función es COSTOSA en runtime. Idealmente debería usarse
    una columna pre-calculada con índice.
    """
    return func.replace(
        func.replace(
            func.replace(func.upper(func.trim(expr)), " ", ""),
            "-", ""
        ),
        "_", ""
    )


def count_error_ss_optimized(db: Session, apsa_load_id: int, aconex_load_id: int) -> int:
    """
    Cuenta protocolos APSA con "Error de SS" (subsistema).

    Criterio: Existe match por código (normalizado) con ACONEX,
              PERO NO existe match por código + subsistema.

    Versión OPTIMIZADA con LEFT JOIN en lugar de subconsultas correlacionadas.

    Performance esperada:
    - Antes: >15 minutos (subconsultas correlacionadas)
    - Después: 1-5 segundos (LEFT JOIN con índices)

    Args:
        db: Sesión de base de datos
        apsa_load_id: ID de la carga APSA
        aconex_load_id: ID de la carga ACONEX

    Returns:
        int: Cantidad de protocolos APSA con error de SS
    """

    # Subconsulta: ACONEX docs agrupados por código normalizado
    # Para cada código, agrupa los subsistemas distintos que tiene en ACONEX
    aconex_by_code = (
        select(
            _norm_sql(AconexDoc.document_no).label("doc_norm"),
            func.array_agg(func.distinct(_norm_sql(AconexDoc.subsystem_code))).label("subsistemas_aconex")
        )
        .where(AconexDoc.load_id == aconex_load_id)
        .group_by(_norm_sql(AconexDoc.document_no))
        .subquery()
    )

    # Query principal: APSA LEFT JOIN con ACONEX agrupado
    result = db.execute(
        select(func.count())
        .select_from(ApsaProtocol)
        .outerjoin(
            aconex_by_code,
            _norm_sql(ApsaProtocol.codigo_cmdic) == aconex_by_code.c.doc_norm
        )
        .where(
            ApsaProtocol.load_id == apsa_load_id,
            # Existe match por código (aconex_by_code no es NULL)
            aconex_by_code.c.doc_norm.isnot(None),
            # PERO el subsistema de APSA NO está en la lista de subsistemas de ACONEX
            # Usamos NOT (subsistema_norm = ANY(subsistemas_aconex))
            ~func.coalesce(
                _norm_sql(ApsaProtocol.subsistema) == func.any_(aconex_by_code.c.subsistemas_aconex),
                False
            )
        )
    ).scalar()

    return int(result or 0)


def count_error_ss_simple(db: Session, apsa_load_id: int, aconex_load_id: int) -> int:
    """
    Versión alternativa más simple usando CTE.

    Esta versión puede ser más legible y potencialmente más rápida
    dependiendo del optimizador de SQL de tu base de datos.
    """
    from sqlalchemy import text

    # Query usando SQL raw con CTE (Common Table Expression)
    # Más legible y el optimizador puede hacer mejor trabajo
    query = text("""
        WITH aconex_matches AS (
            -- Paso 1: Encontrar TODOS los matches por código
            SELECT DISTINCT
                UPPER(TRIM(REPLACE(REPLACE(REPLACE(ap.codigo_cmdic, ' ', ''), '-', ''), '_', ''))) as codigo_norm,
                UPPER(TRIM(REPLACE(REPLACE(REPLACE(ap.subsistema, ' ', ''), '-', ''), '_', ''))) as subs_apsa_norm,
                UPPER(TRIM(REPLACE(REPLACE(REPLACE(acx.subsystem_code, ' ', ''), '-', ''), '_', ''))) as subs_aconex_norm
            FROM apsa_protocols ap
            INNER JOIN aconex_docs acx
                ON UPPER(TRIM(REPLACE(REPLACE(REPLACE(acx.document_no, ' ', ''), '-', ''), '_', ''))) =
                   UPPER(TRIM(REPLACE(REPLACE(REPLACE(ap.codigo_cmdic, ' ', ''), '-', ''), '_', '')))
            WHERE ap.load_id = :apsa_id
              AND acx.load_id = :aconex_id
        )
        SELECT COUNT(DISTINCT am.codigo_norm)
        FROM aconex_matches am
        WHERE am.subs_apsa_norm != am.subs_aconex_norm
           OR am.subs_aconex_norm IS NULL
           OR am.subs_apsa_norm IS NULL
    """)

    result = db.execute(query, {"apsa_id": apsa_load_id, "aconex_id": aconex_load_id}).scalar()
    return int(result or 0)


def count_error_ss_with_temp_columns(db: Session, apsa_load_id: int, aconex_load_id: int) -> int:
    """
    Versión ÓPTIMA usando columnas pre-calculadas.

    REQUISITO: Debe haber columnas 'codigo_cmdic_norm' y 'subsistema_norm'
               en apsa_protocols, y 'document_no_norm' y 'subsystem_code_norm'
               en aconex_docs.

    Performance esperada: <500ms incluso con 100k+ registros

    Esta es la versión que deberías usar después de:
    1. Agregar las columnas normalizadas
    2. Crear índices en ellas
    3. Poblar los valores existentes
    """
    # Subconsulta: ACONEX agrupado por código normalizado
    aconex_by_code = (
        select(
            AconexDoc.document_no_norm.label("doc_norm"),
            func.array_agg(func.distinct(AconexDoc.subsystem_code_norm)).label("subsistemas_aconex")
        )
        .where(
            AconexDoc.load_id == aconex_load_id,
            AconexDoc.document_no_norm.isnot(None)
        )
        .group_by(AconexDoc.document_no_norm)
        .subquery()
    )

    # Query principal: JOIN usando columnas indexadas
    result = db.execute(
        select(func.count())
        .select_from(ApsaProtocol)
        .outerjoin(
            aconex_by_code,
            ApsaProtocol.codigo_cmdic_norm == aconex_by_code.c.doc_norm
        )
        .where(
            ApsaProtocol.load_id == apsa_load_id,
            aconex_by_code.c.doc_norm.isnot(None),  # Hay match por código
            ~func.coalesce(
                ApsaProtocol.subsistema_norm == func.any_(aconex_by_code.c.subsistemas_aconex),
                False
            )
        )
    ).scalar()

    return int(result or 0)


# ==============================================================================
# EJEMPLO DE USO:
# ==============================================================================
"""
# En main.py, dentro de /metrics/cards:

from .metrics_optimized import count_error_ss_optimized

# Reemplazar el bloque EXISTS problemático por:
if apsa_id and aconex_id:
    with measure_query("Count APSA con Error de SS (optimizado con LEFT JOIN)", "metrics_cards"):
        aconex_error_ss = count_error_ss_optimized(db, apsa_id, aconex_id)
else:
    aconex_error_ss = 0
"""
