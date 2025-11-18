"""
Script para verificar la conexión a la base de datos antes de agregar índices.

IMPORTANTE: Ejecutar desde el directorio backend:
  cd C:\AppServ\www\quality-app\backend
  python scripts/verify_connection.py

NO ejecutar desde backend\scripts
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

# Verificar que .env existe
env_file = os.path.join(backend_dir, '.env')
if not os.path.exists(env_file):
    logger.error(f"❌ Archivo .env NO encontrado en: {env_file}")
    logger.error("\n💡 Solución:")
    logger.error("   1. Copia .env.example a .env")
    logger.error("   2. Edita .env con tus credenciales de MySQL")
    sys.exit(1)

logger.info(f"✅ Archivo .env encontrado: {env_file}")
logger.info(f"📂 Directorio de trabajo: {os.getcwd()}")

# Ahora sí importar
try:
    from app.db import engine
    from sqlalchemy import text
except Exception as e:
    logger.error(f"\n❌ Error importando módulos: {str(e)}")
    logger.error("\n💡 Posibles causas:")
    logger.error("   1. Faltan variables en .env (DB_USER, DB_PASSWORD, DB_NAME)")
    logger.error("   2. El archivo .env tiene formato incorrecto")
    logger.error("   3. Falta instalar dependencias: pip install -r requirements.txt")
    logger.error("\n📝 Variables requeridas en .env:")
    logger.error("   DB_USER=tu_usuario")
    logger.error("   DB_PASSWORD=tu_password")
    logger.error("   DB_HOST=127.0.0.1")
    logger.error("   DB_PORT=3306")
    logger.error("   DB_NAME=quality_db")
    logger.error("   APP_SECRET=tu_secreto_cualquiera")
    sys.exit(1)


def verify_connection():
    """Verifica la conexión a MySQL y muestra información de las tablas."""

    logger.info("="*80)
    logger.info("🔍 VERIFICANDO CONEXIÓN A BASE DE DATOS")
    logger.info("="*80)

    try:
        with engine.connect() as connection:
            # 1. Verificar conexión básica
            logger.info("\n✅ Conexión exitosa a MySQL")

            # 2. Verificar versión de MySQL
            result = connection.execute(text("SELECT VERSION()"))
            version = result.scalar()
            logger.info(f"📊 Versión de MySQL: {version}")

            # 3. Verificar base de datos actual
            result = connection.execute(text("SELECT DATABASE()"))
            db_name = result.scalar()
            logger.info(f"🗄️  Base de datos: {db_name}")

            # 4. Verificar que las tablas existen
            logger.info("\n📋 Verificando tablas necesarias...")

            tables = ['apsa_protocols', 'aconex_docs', 'loads']
            for table in tables:
                result = connection.execute(text(
                    f"SELECT COUNT(*) FROM information_schema.TABLES "
                    f"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table"
                ), {"table": table})

                if result.scalar() > 0:
                    # Contar registros
                    count = connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                    logger.info(f"  ✅ {table}: {count:,} registros")
                else:
                    logger.error(f"  ❌ {table}: NO ENCONTRADA")
                    return False

            # 5. Verificar índices actuales
            logger.info("\n📊 Índices actuales en apsa_protocols:")
            result = connection.execute(text(
                "SELECT INDEX_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) as COLUMNS "
                "FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'apsa_protocols' "
                "GROUP BY INDEX_NAME"
            ))

            for row in result:
                prefix = "  🆕" if row[0].startswith('idx_') else "  📍"
                logger.info(f"{prefix} {row[0]}: {row[1]}")

            logger.info("\n📊 Índices actuales en aconex_docs:")
            result = connection.execute(text(
                "SELECT INDEX_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) as COLUMNS "
                "FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'aconex_docs' "
                "GROUP BY INDEX_NAME"
            ))

            for row in result:
                prefix = "  🆕" if row[0].startswith('idx_') else "  📍"
                logger.info(f"{prefix} {row[0]}: {row[1]}")

            # 6. Verificar permisos
            logger.info("\n🔐 Verificando permisos de usuario...")
            try:
                connection.execute(text("SHOW GRANTS"))
                logger.info("  ✅ Usuario tiene permisos para ver grants")
            except Exception:
                logger.warning("  ⚠️  No se pudieron verificar permisos (puede ser normal)")

            logger.info("\n" + "="*80)
            logger.info("✅ VERIFICACIÓN COMPLETADA - TODO OK")
            logger.info("="*80)
            logger.info("\n💡 Siguiente paso:")
            logger.info("   python scripts/add_indexes.py")
            logger.info("")

            return True

    except Exception as e:
        logger.error(f"\n❌ ERROR DE CONEXIÓN: {str(e)}")
        logger.error("\n🔧 Posibles soluciones:")
        logger.error("   1. Verifica que MySQL esté corriendo")
        logger.error("   2. Verifica las credenciales en .env")
        logger.error("   3. Verifica que la base de datos exista")
        logger.error("   4. Ejecuta: pip install pymysql")
        return False


if __name__ == "__main__":
    try:
        success = verify_connection()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"\n❌ Error fatal: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
