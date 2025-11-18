"""
Script para agregar columnas normalizadas y sus índices.

SOLUCIÓN DEFINITIVA para el problema de "Error de SS" lento.

IMPORTANTE: Ejecutar desde el directorio backend:
  cd C:\AppServ\www\quality-app\backend
  python scripts/add_normalized_columns.py

Este script:
1. Agrega columnas GENERATED (auto-calculadas) con valores normalizados
2. Crea índices en estas columnas
3. Verifica que todo funcionó correctamente

Tiempo estimado:
- Base pequeña (<10k): 30 segundos
- Base mediana (10-100k): 2-5 minutos
- Base grande (>100k): 5-15 minutos
"""
import sys
import os

# Asegurar que estamos en el directorio correcto
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Verificar .env
env_file = os.path.join(backend_dir, '.env')
if not os.path.exists(env_file):
    logger.error(f"❌ Archivo .env NO encontrado")
    logger.error("💡 Ejecuta primero: python scripts/verify_connection.py")
    sys.exit(1)

# Importar módulos
try:
    from app.db import engine
    from sqlalchemy import text
except Exception as e:
    logger.error(f"❌ Error de configuración: {str(e)}")
    logger.error("💡 Ejecuta primero: python scripts/verify_connection.py")
    sys.exit(1)


def column_exists(connection, table_name: str, column_name: str) -> bool:
    """Verifica si una columna ya existe."""
    try:
        result = connection.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "  AND TABLE_NAME = :table "
            "  AND COLUMN_NAME = :column"
        ), {"table": table_name, "column": column_name})
        return result.scalar() > 0
    except Exception:
        return False


def add_normalized_columns():
    """Agrega columnas normalizadas y sus índices."""

    logger.info("="*80)
    logger.info("🚀 AGREGANDO COLUMNAS NORMALIZADAS")
    logger.info("="*80)
    logger.info("")
    logger.info("⚠️  ADVERTENCIA: Este proceso puede tardar varios minutos")
    logger.info("   NO interrumpas el proceso una vez iniciado")
    logger.info("")

    with engine.connect() as connection:
        # ==================================================================
        # PASO 1: Agregar columnas normalizadas en apsa_protocols
        # ==================================================================
        logger.info("📊 PASO 1: Columnas normalizadas en apsa_protocols")
        logger.info("-" * 80)

        columns_apsa = [
            ("codigo_cmdic_norm", "VARCHAR(120)"),
            ("subsistema_norm", "VARCHAR(60)")
        ]

        for col_name, col_type in columns_apsa:
            if column_exists(connection, "apsa_protocols", col_name):
                logger.info(f"  ✓ {col_name} ya existe, omitiendo...")
                continue

            logger.info(f"  ⏳ Creando columna {col_name}...")

            # Obtener el nombre de la columna original
            original_col = col_name.replace("_norm", "")

            sql = f"""
            ALTER TABLE apsa_protocols
            ADD COLUMN {col_name} {col_type}
            GENERATED ALWAYS AS (
                UPPER(TRIM(REPLACE(REPLACE(REPLACE({original_col}, ' ', ''), '-', ''), '_', '')))
            ) STORED
            """

            try:
                connection.execute(text(sql))
                connection.commit()
                logger.info(f"  ✅ {col_name} creada exitosamente")
            except Exception as e:
                if "duplicate column name" in str(e).lower():
                    logger.info(f"  ✓ {col_name} ya existe (detectado por error)")
                else:
                    logger.error(f"  ❌ Error: {str(e)}")
                    connection.rollback()
                    return False

        # ==================================================================
        # PASO 2: Agregar columnas normalizadas en aconex_docs
        # ==================================================================
        logger.info("\n📊 PASO 2: Columnas normalizadas en aconex_docs")
        logger.info("-" * 80)

        columns_aconex = [
            ("document_no_norm", "VARCHAR(120)"),
            ("subsystem_code_norm", "VARCHAR(60)")
        ]

        for col_name, col_type in columns_aconex:
            if column_exists(connection, "aconex_docs", col_name):
                logger.info(f"  ✓ {col_name} ya existe, omitiendo...")
                continue

            logger.info(f"  ⏳ Creando columna {col_name}...")

            # Obtener el nombre de la columna original
            original_col = col_name.replace("_norm", "")

            sql = f"""
            ALTER TABLE aconex_docs
            ADD COLUMN {col_name} {col_type}
            GENERATED ALWAYS AS (
                UPPER(TRIM(REPLACE(REPLACE(REPLACE({original_col}, ' ', ''), '-', ''), '_', '')))
            ) STORED
            """

            try:
                connection.execute(text(sql))
                connection.commit()
                logger.info(f"  ✅ {col_name} creada exitosamente")
            except Exception as e:
                if "duplicate column name" in str(e).lower():
                    logger.info(f"  ✓ {col_name} ya existe (detectado por error)")
                else:
                    logger.error(f"  ❌ Error: {str(e)}")
                    connection.rollback()
                    return False

        # ==================================================================
        # PASO 3: Crear índices en columnas normalizadas
        # ==================================================================
        logger.info("\n📊 PASO 3: Índices en columnas normalizadas")
        logger.info("-" * 80)

        from scripts.add_indexes import index_exists, create_index_safe

        indexes = [
            # APSA
            {
                "name": "idx_apsa_codigo_norm",
                "table": "apsa_protocols",
                "sql": "CREATE INDEX idx_apsa_codigo_norm ON apsa_protocols(codigo_cmdic_norm)",
                "description": "Índice en codigo_cmdic normalizado"
            },
            {
                "name": "idx_apsa_subsistema_norm",
                "table": "apsa_protocols",
                "sql": "CREATE INDEX idx_apsa_subsistema_norm ON apsa_protocols(subsistema_norm)",
                "description": "Índice en subsistema normalizado"
            },
            {
                "name": "idx_apsa_load_codigo_norm",
                "table": "apsa_protocols",
                "sql": "CREATE INDEX idx_apsa_load_codigo_norm ON apsa_protocols(load_id, codigo_cmdic_norm)",
                "description": "Índice compuesto load_id + codigo_cmdic_norm"
            },
            {
                "name": "idx_apsa_load_subs_norm",
                "table": "apsa_protocols",
                "sql": "CREATE INDEX idx_apsa_load_subs_norm ON apsa_protocols(load_id, subsistema_norm)",
                "description": "Índice compuesto load_id + subsistema_norm"
            },
            # ACONEX
            {
                "name": "idx_aconex_doc_norm",
                "table": "aconex_docs",
                "sql": "CREATE INDEX idx_aconex_doc_norm ON aconex_docs(document_no_norm)",
                "description": "Índice en document_no normalizado"
            },
            {
                "name": "idx_aconex_sub_norm",
                "table": "aconex_docs",
                "sql": "CREATE INDEX idx_aconex_sub_norm ON aconex_docs(subsystem_code_norm)",
                "description": "Índice en subsystem_code normalizado"
            },
            {
                "name": "idx_aconex_load_doc_norm",
                "table": "aconex_docs",
                "sql": "CREATE INDEX idx_aconex_load_doc_norm ON aconex_docs(load_id, document_no_norm)",
                "description": "Índice compuesto load_id + document_no_norm"
            },
            {
                "name": "idx_aconex_load_sub_norm",
                "table": "aconex_docs",
                "sql": "CREATE INDEX idx_aconex_load_sub_norm ON aconex_docs(load_id, subsystem_code_norm)",
                "description": "Índice compuesto load_id + subsystem_code_norm"
            },
        ]

        created = 0
        skipped = 0

        for idx in indexes:
            logger.info(f"\n  📊 {idx['description']}")

            if index_exists(connection, idx['table'], idx['name']):
                logger.info(f"  ✓ {idx['name']} ya existe, omitiendo...")
                skipped += 1
            else:
                if create_index_safe(connection, idx['sql'], idx['name'], idx['table']):
                    created += 1
                else:
                    logger.error(f"  ❌ Error creando {idx['name']}")

        # ==================================================================
        # PASO 4: Verificar
        # ==================================================================
        logger.info("\n📊 PASO 4: Verificación")
        logger.info("-" * 80)

        # Ver columnas creadas
        logger.info("\n  📋 Columnas normalizadas creadas:")
        result = connection.execute(text("""
            SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME IN ('apsa_protocols', 'aconex_docs')
              AND COLUMN_NAME LIKE '%_norm'
            ORDER BY TABLE_NAME, COLUMN_NAME
        """))

        for row in result:
            logger.info(f"    {row[0]}.{row[1]}: {row[2]}")

        # Ver índices creados
        logger.info("\n  📋 Índices creados:")
        result = connection.execute(text("""
            SELECT TABLE_NAME, INDEX_NAME
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME IN ('apsa_protocols', 'aconex_docs')
              AND INDEX_NAME LIKE '%norm%'
            GROUP BY TABLE_NAME, INDEX_NAME
            ORDER BY TABLE_NAME, INDEX_NAME
        """))

        for row in result:
            logger.info(f"    {row[0]}.{row[1]}")

        # Mostrar ejemplos de valores
        logger.info("\n  📋 Ejemplos de valores normalizados:")
        result = connection.execute(text("""
            SELECT
                codigo_cmdic,
                codigo_cmdic_norm,
                subsistema,
                subsistema_norm
            FROM apsa_protocols
            LIMIT 3
        """))

        for i, row in enumerate(result, 1):
            logger.info(f"\n    Ejemplo {i}:")
            logger.info(f"      codigo_cmdic: '{row[0]}' → '{row[1]}'")
            logger.info(f"      subsistema: '{row[2]}' → '{row[3]}'")

    logger.info("\n" + "="*80)
    logger.info("✅ COLUMNAS NORMALIZADAS AGREGADAS EXITOSAMENTE")
    logger.info("="*80)
    logger.info(f"\n📊 Resumen:")
    logger.info(f"  ✅ Índices creados: {created}")
    logger.info(f"  ⏭️  Índices omitidos: {skipped}")
    logger.info("")
    logger.info("💡 Próximo paso:")
    logger.info("   1. Actualizar el código para usar las columnas normalizadas")
    logger.info("   2. Reiniciar el backend")
    logger.info("   3. Probar /metrics/cards (debería ser MUCHO más rápido)")
    logger.info("")

    return True


if __name__ == "__main__":
    try:
        logger.info("\n⚠️  IMPORTANTE:")
        logger.info("   Este script agregará columnas y índices a tus tablas")
        logger.info("   Puede tardar varios minutos dependiendo del tamaño de la BD")
        logger.info("")

        response = input("¿Continuar? (s/n): ")
        if response.lower() not in ['s', 'si', 'y', 'yes']:
            logger.info("Operación cancelada")
            sys.exit(0)

        success = add_normalized_columns()
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"\n❌ Error fatal: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
