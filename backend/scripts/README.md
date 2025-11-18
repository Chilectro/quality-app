# 🛠️ Scripts de Utilidad

Colección de scripts para mantenimiento y deployment de la aplicación.

---

## 📋 Scripts Disponibles

### 1. `verify_production_ready.py`
**Verifica que la base de datos está lista para deployment**

```bash
# Usando tu base de datos local
python backend/scripts/verify_production_ready.py

# Usando Railway (producción)
# 1. Copia DATABASE_URL de Railway
# 2. Crea/edita .env con:
#    DATABASE_URL=postgresql://...
# 3. Ejecuta:
python backend/scripts/verify_production_ready.py
```

**Qué verifica:**
- ✅ Conexión a la base de datos
- ✅ Tablas principales existen
- ✅ Columnas normalizadas existen
- ✅ Columnas normalizadas tienen datos
- ✅ Índices importantes existen

---

### 2. `create_backup.py`
**Crea un backup completo de la base de datos**

```bash
# Backup de producción (Railway)
# 1. Configura DATABASE_URL en .env apuntando a Railway
# 2. Ejecuta:
python backend/scripts/create_backup.py

# El backup se guarda en: backend/../backups/backup_quality_app_YYYYMMDD_HHMMSS.sql
```

**Requisitos:**
- `pg_dump` instalado (viene con PostgreSQL client)

**Resultado:**
- Archivo `.sql` con dump completo de la base de datos
- Listo para restaurar con `psql`

---

### 3. `add_normalized_columns.py`
**Agrega columnas normalizadas a las tablas existentes**

```bash
# IMPORTANTE: Solo ejecutar UNA VEZ en cada base de datos

# Para producción (Railway):
# 1. Configura DATABASE_URL en .env apuntando a Railway
# 2. Ejecuta:
python backend/scripts/add_normalized_columns.py

# Para local:
python backend/scripts/add_normalized_columns.py
```

**Qué hace:**
- Agrega columnas `*_norm` a `apsa_protocols` y `aconex_docs`
- Crea columnas como GENERATED ALWAYS (auto-calcula valores)
- Crea índices para optimización

**⚠️ ADVERTENCIA:**
- Solo ejecutar si las columnas NO existen
- Usa `verify_production_ready.py` primero para verificar

---

## 🚀 Workflow de Deployment

**Orden recomendado antes de hacer deployment:**

```bash
# 1. Crear backup de producción
python backend/scripts/create_backup.py

# 2. Verificar que producción está lista
python backend/scripts/verify_production_ready.py

# 3. Si el script anterior dice que faltan columnas:
python backend/scripts/add_normalized_columns.py

# 4. Verificar nuevamente
python backend/scripts/verify_production_ready.py

# 5. Si todo está ✅, procede con git push
```

---

## 🔧 Configuración

Todos los scripts usan las variables de entorno definidas en `.env`:

```bash
# .env (ejemplo)
DATABASE_URL=postgresql://user:password@host:port/database
APP_SECRET=tu_secret_aqui
# ... otras variables ...
```

**Para apuntar a Railway (producción):**
1. Ve a Railway → PostgreSQL → Connect
2. Copia "Postgres Connection URL"
3. Pégala en `.env` como `DATABASE_URL=...`

---

## 🆘 Troubleshooting

### "pg_dump: command not found"
Instala PostgreSQL client:
- **Windows:** https://www.postgresql.org/download/windows/
- **Mac:** `brew install postgresql`
- **Linux:** `sudo apt-get install postgresql-client`

### "Connection refused"
- Verifica que `DATABASE_URL` es correcto
- Verifica que puedes conectarte a Railway
- Intenta desde Railway CLI: `railway run psql`

### "Columnas ya existen"
- Normal si ya ejecutaste `add_normalized_columns.py` antes
- Usa `verify_production_ready.py` para confirmar que todo está OK

---

## 📚 Más Información

Ver: `DEPLOYMENT_PLAN.md` en la raíz del proyecto para guía completa de deployment.
