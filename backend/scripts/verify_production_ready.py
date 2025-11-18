"""
Script de verificación pre-deployment
Verifica que la base de datos en producción está lista para el deployment
"""
import sys
import os

# Agregar el directorio parent al path para imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine, text, inspect
from app.config import get_settings

def verify_production_ready():
    """Verifica que la base de datos está lista para deployment"""

    settings = get_settings()

    print("🔍 Verificando estado de la base de datos...")
    print(f"📍 Conectando a: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'localhost'}")

    try:
        engine = create_engine(settings.DATABASE_URL)

        with engine.connect() as conn:
            # Verificar conexión
            print("✅ Conexión exitosa a la base de datos")

            # Verificar tablas principales
            inspector = inspect(engine)
            tables = inspector.get_table_names()

            required_tables = ['apsa_protocols', 'aconex_docs', 'users', 'loads']
            missing_tables = [t for t in required_tables if t not in tables]

            if missing_tables:
                print(f"❌ ERROR: Faltan tablas: {missing_tables}")
                return False

            print(f"✅ Todas las tablas principales existen ({len(tables)} tablas encontradas)")

            # Verificar columnas normalizadas en apsa_protocols
            apsa_columns = [col['name'] for col in inspector.get_columns('apsa_protocols')]

            normalized_apsa = ['codigo_cmdic_norm', 'subsistema_norm']
            missing_apsa = [c for c in normalized_apsa if c not in apsa_columns]

            if missing_apsa:
                print(f"❌ ERROR: Faltan columnas en apsa_protocols: {missing_apsa}")
                print("   → Ejecuta: python backend/scripts/add_normalized_columns.py")
                return False

            print(f"✅ Columnas normalizadas en apsa_protocols: OK")

            # Verificar columnas normalizadas en aconex_docs
            aconex_columns = [col['name'] for col in inspector.get_columns('aconex_docs')]

            normalized_aconex = ['document_no_norm', 'subsystem_norm']
            missing_aconex = [c for c in normalized_aconex if c not in aconex_columns]

            if missing_aconex:
                print(f"❌ ERROR: Faltan columnas en aconex_docs: {missing_aconex}")
                print("   → Ejecuta: python backend/scripts/add_normalized_columns.py")
                return False

            print(f"✅ Columnas normalizadas en aconex_docs: OK")

            # Verificar índices
            apsa_indexes = [idx['name'] for idx in inspector.get_indexes('apsa_protocols')]
            required_apsa_indexes = ['ix_apsa_protocols_codigo_cmdic_norm', 'ix_apsa_protocols_subsistema_norm']

            missing_indexes = [idx for idx in required_apsa_indexes if idx not in apsa_indexes]
            if missing_indexes:
                print(f"⚠️  ADVERTENCIA: Faltan índices en apsa_protocols: {missing_indexes}")
                print("   → Esto afectará el rendimiento pero no romperá la app")
            else:
                print("✅ Índices en apsa_protocols: OK")

            # Contar registros
            result = conn.execute(text("SELECT COUNT(*) FROM apsa_protocols"))
            apsa_count = result.scalar()

            result = conn.execute(text("SELECT COUNT(*) FROM aconex_docs"))
            aconex_count = result.scalar()

            result = conn.execute(text("SELECT COUNT(*) FROM users"))
            users_count = result.scalar()

            print(f"\n📊 Estadísticas:")
            print(f"   - Protocolos APSA: {apsa_count:,}")
            print(f"   - Documentos Aconex: {aconex_count:,}")
            print(f"   - Usuarios: {users_count}")

            # Verificar columnas normalizadas tienen datos
            if apsa_count > 0:
                result = conn.execute(text(
                    "SELECT COUNT(*) FROM apsa_protocols WHERE codigo_cmdic_norm IS NOT NULL"
                ))
                norm_count = result.scalar()

                if norm_count == 0:
                    print(f"❌ ERROR: Las columnas normalizadas están vacías")
                    print("   → Ejecuta: python backend/scripts/add_normalized_columns.py")
                    return False

                percentage = (norm_count / apsa_count) * 100
                print(f"✅ Columnas normalizadas populadas: {percentage:.1f}% ({norm_count:,}/{apsa_count:,})")

            print("\n" + "="*60)
            print("✅ ¡Base de datos lista para deployment!")
            print("="*60)
            return True

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print("\n💡 Posibles soluciones:")
        print("   1. Verifica que DATABASE_URL esté configurado correctamente")
        print("   2. Verifica que puedes conectarte a Railway")
        print("   3. Ejecuta: python backend/scripts/add_normalized_columns.py")
        return False

if __name__ == "__main__":
    print("="*60)
    print("🚀 VERIFICACIÓN PRE-DEPLOYMENT")
    print("="*60)
    print()

    success = verify_production_ready()

    if success:
        print("\n✅ Puedes proceder con el deployment de forma segura")
        sys.exit(0)
    else:
        print("\n❌ NO desplegues hasta resolver los problemas anteriores")
        sys.exit(1)
