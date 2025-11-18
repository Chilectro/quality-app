"""
Script para crear backup de la base de datos
Compatible con Railway y PostgreSQL local
"""
import sys
import os
from datetime import datetime
import subprocess

# Agregar el directorio parent al path para imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import get_settings

def create_backup():
    """Crea un backup de la base de datos usando pg_dump"""

    settings = get_settings()
    database_url = settings.DATABASE_URL

    # Generar nombre del archivo con timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"backup_quality_app_{timestamp}.sql"
    backup_path = os.path.join(os.path.dirname(__file__), "..", "..", "backups", backup_filename)

    # Crear directorio de backups si no existe
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)

    print("="*60)
    print("💾 CREANDO BACKUP DE BASE DE DATOS")
    print("="*60)
    print()
    print(f"📍 Conectando a: {database_url.split('@')[1] if '@' in database_url else 'localhost'}")
    print(f"📁 Archivo de salida: {backup_filename}")
    print()

    try:
        # Verificar que pg_dump está disponible
        try:
            subprocess.run(["pg_dump", "--version"], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("❌ ERROR: pg_dump no encontrado")
            print()
            print("💡 Instala PostgreSQL client:")
            print("   - Windows: https://www.postgresql.org/download/windows/")
            print("   - Mac: brew install postgresql")
            print("   - Linux: sudo apt-get install postgresql-client")
            return False

        # Ejecutar pg_dump
        print("🔄 Creando backup... (esto puede tomar varios minutos)")
        print()

        with open(backup_path, 'w', encoding='utf-8') as f:
            result = subprocess.run(
                ["pg_dump", database_url],
                stdout=f,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )

        # Verificar tamaño del archivo
        file_size = os.path.getsize(backup_path)
        file_size_mb = file_size / (1024 * 1024)

        if file_size < 1024:  # Menos de 1KB probablemente es un error
            print(f"⚠️  ADVERTENCIA: Archivo de backup muy pequeño ({file_size} bytes)")
            print("   Verifica que la base de datos tenga datos")
            return False

        print(f"✅ Backup creado exitosamente!")
        print()
        print(f"📊 Tamaño: {file_size_mb:.2f} MB")
        print(f"📁 Ubicación: {os.path.abspath(backup_path)}")
        print()
        print("="*60)
        print("✅ BACKUP COMPLETADO")
        print("="*60)
        print()
        print("💡 Pasos siguientes:")
        print("   1. Verifica que el archivo existe y tiene buen tamaño")
        print("   2. Guarda una copia en lugar seguro (Google Drive, etc.)")
        print("   3. Procede con el deployment")
        print()
        print("🔙 Para restaurar este backup:")
        print(f'   psql "{database_url}" < {backup_filename}')
        print()

        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ ERROR al crear backup: {e}")
        if e.stderr:
            print(f"Detalles: {e.stderr}")
        print()
        print("💡 Posibles soluciones:")
        print("   1. Verifica que DATABASE_URL es correcto")
        print("   2. Verifica que tienes acceso a la base de datos")
        print("   3. Intenta crear backup manualmente desde Railway UI")
        return False

    except Exception as e:
        print(f"❌ ERROR inesperado: {e}")
        return False

if __name__ == "__main__":
    success = create_backup()
    sys.exit(0 if success else 1)
