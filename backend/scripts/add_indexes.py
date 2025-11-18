"""
Script para agregar índices de performance a la base de datos.

IMPORTANTE: Ejecutar desde el directorio backend:
  cd C:\AppServ\www\quality-app\backend
  python scripts/add_indexes.py

Este script agrega índices que mejoran significativamente el performance
de los endpoints /metrics/* y /aconex/*.
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
    from sqlalchemy import text, inspect
except Exception as e:
    logger.error(f"❌ Error de configuración: {str(e)}")
    logger.error("💡 Ejecuta primero: python scripts/verify_connection.py")
    sys.exit(1)


def index_exists(connection, table_name: str, index_name: str) -> bool:
    """Verifica si un índice ya existe (compatible con MySQL)."""
    try:
        # Método 1: Usar inspector de SQLAlchemy
        inspector = inspect(connection)
        indexes = inspector.get_indexes(table_name)
        return any(idx['name'] == index_name for idx in indexes)
    except Exception as e:
        # Método 2: Query directa a MySQL (fallback)
        logger.debug(f"Inspector failed, using direct query: {e}")
        try:
            result = connection.execute(text(
                f"SHOW INDEX FROM {table_name} WHERE Key_name = :index_name"
            ), {"index_name": index_name})
            return result.fetchone() is not None
        except Exception:
            return False


def create_index_safe(connection, sql: str, index_name: str, table_name: str):
    """Crea un índice solo si no existe (compatible con MySQL)."""
    try:
        if index_exists(connection, table_name, index_name):
            logger.info(f"✓ Índice {index_name} ya existe en {table_name}")
            return True

        logger.info(f"⏳ Creando índice {index_name} en {table_name}...")
        connection.execute(text(sql))
        connection.commit()
        logger.info(f"✅ Índice {index_name} creado exitosamente")
        return True

    except Exception as e:
        error_msg = str(e).lower()
        # MySQL error 1061: Duplicate key name
        if "duplicate key name" in error_msg or "1061" in error_msg:
            logger.info(f"✓ Índice {index_name} ya existe (detectado por error)")
            return True
        logger.error(f"❌ Error creando índice {index_name}: {str(e)}")
        connection.rollback()
        return False


def add_performance_indexes():
    """Agrega todos los índices de performance."""

    indexes = [
        # =========================================================================
        # ÍNDICES BÁSICOS EN COLUMNAS DE JOIN
        # =========================================================================
        {
            "name": "idx_apsa_codigo_cmdic",
            "table": "apsa_protocols",
            "sql": "CREATE INDEX idx_apsa_codigo_cmdic ON apsa_protocols(codigo_cmdic)",
            "description": "Índice en codigo_cmdic para JOINs con ACONEX"
        },
        {
            "name": "idx_aconex_document_no",
            "table": "aconex_docs",
            "sql": "CREATE INDEX idx_aconex_document_no ON aconex_docs(document_no)",
            "description": "Índice en document_no para JOINs con APSA"
        },

        # =========================================================================
        # ÍNDICES COMPUESTOS PARA QUERIES FRECUENTES
        # =========================================================================
        {
            "name": "idx_apsa_load_disc",
            "table": "apsa_protocols",
            "sql": "CREATE INDEX idx_apsa_load_disc ON apsa_protocols(load_id, disciplina)",
            "description": "Índice compuesto para queries por load_id + disciplina"
        },
        {
            "name": "idx_apsa_load_subs",
            "table": "apsa_protocols",
            "sql": "CREATE INDEX idx_apsa_load_subs ON apsa_protocols(load_id, subsistema)",
            "description": "Índice compuesto para queries por load_id + subsistema"
        },
        {
            "name": "idx_aconex_load_doc",
            "table": "aconex_docs",
            "sql": "CREATE INDEX idx_aconex_load_doc ON aconex_docs(load_id, document_no)",
            "description": "Índice compuesto para queries por load_id + document_no"
        },
        {
            "name": "idx_aconex_load_sub",
            "table": "aconex_docs",
            "sql": "CREATE INDEX idx_aconex_load_sub ON aconex_docs(load_id, subsystem_code)",
            "description": "Índice compuesto para queries por load_id + subsystem_code"
        },

        # =========================================================================
        # ÍNDICES COMPUESTOS CON STATUS (para métricas)
        # =========================================================================
        {
            "name": "idx_apsa_load_disc_status",
            "table": "apsa_protocols",
            "sql": "CREATE INDEX idx_apsa_load_disc_status ON apsa_protocols(load_id, disciplina, status_bim360)",
            "description": "Índice para métricas por disciplina + status"
        },
        {
            "name": "idx_apsa_load_subs_status",
            "table": "apsa_protocols",
            "sql": "CREATE INDEX idx_apsa_load_subs_status ON apsa_protocols(load_id, subsistema, status_bim360)",
            "description": "Índice para métricas por subsistema + status"
        },
    ]

    logger.info("="*80)
    logger.info("🚀 AGREGANDO ÍNDICES DE PERFORMANCE")
    logger.info("="*80)

    with engine.connect() as connection:
        success_count = 0
        skip_count = 0
        error_count = 0

        for idx in indexes:
            logger.info(f"\n📊 {idx['description']}")

            if index_exists(connection, idx['table'], idx['name']):
                logger.info(f"✓ {idx['name']} ya existe, omitiendo...")
                skip_count += 1
            else:
                if create_index_safe(connection, idx['sql'], idx['name'], idx['table']):
                    success_count += 1
                else:
                    error_count += 1

    logger.info("\n" + "="*80)
    logger.info("📊 RESUMEN")
    logger.info("="*80)
    logger.info(f"✅ Creados: {success_count}")
    logger.info(f"⏭️  Omitidos (ya existían): {skip_count}")
    logger.info(f"❌ Errores: {error_count}")
    logger.info(f"📝 Total procesado: {len(indexes)}")
    logger.info("="*80)

    if error_count > 0:
        logger.warning("\n⚠️ Algunos índices no se crearon. Revisa los errores arriba.")
        return False

    logger.info("\n✅ Índices de performance agregados exitosamente!")
    logger.info("\n💡 Próximo paso: Ejecuta los endpoints y compara los tiempos")
    logger.info("   GET /admin/performance/summary")
    return True


if __name__ == "__main__":
    try:
        success = add_performance_indexes()
        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"\n❌ Error fatal: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
