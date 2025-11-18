# 🚂 Railway - Comandos Útiles

Comandos específicos para trabajar con Railway (tu base de datos en producción).

---

## 📦 Instalación Railway CLI

```bash
# Windows (PowerShell como admin)
npm install -g @railway/cli

# Mac/Linux
npm install -g @railway/cli

# Verificar instalación
railway --version
```

---

## 🔐 Login y Configuración

```bash
# Login en Railway
railway login

# Listar tus proyectos
railway list

# Linkear al proyecto actual (ejecutar en la carpeta del proyecto)
cd C:\AppServ\www\quality-app
railway link

# Verificar que estás conectado al proyecto correcto
railway status
```

---

## 💾 Backups

### Crear Backup

```bash
# Opción 1: Dump directo (MÁS FÁCIL)
railway run pg_dump > backups/backup_$(date +%Y%m%d_%H%M%S).sql

# Opción 2: Dump con compresión
railway run pg_dump | gzip > backups/backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Windows (PowerShell):
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
railway run pg_dump > backups/backup_$timestamp.sql
```

### Restaurar Backup

```bash
# ⚠️ CUIDADO: Esto sobrescribe la base de datos actual

# Desde archivo .sql
railway run psql < backups/backup_20241118_120000.sql

# Desde archivo .sql.gz
gunzip -c backups/backup_20241118_120000.sql.gz | railway run psql
```

---

## 🔍 Verificación y Debugging

### Conectarse a PostgreSQL interactivo

```bash
# Abrir psql en Railway
railway run psql

# Comandos útiles dentro de psql:
# \dt              - Listar todas las tablas
# \d apsa_protocols - Describir tabla apsa_protocols
# \di              - Listar índices
# \q               - Salir
```

### Verificar columnas normalizadas

```bash
# Verificar que existen las columnas
railway run psql -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'apsa_protocols' AND column_name LIKE '%_norm';"

# Verificar que tienen datos
railway run psql -c "SELECT COUNT(*) as total, COUNT(codigo_cmdic_norm) as norm FROM apsa_protocols;"
```

### Ver logs en tiempo real

```bash
# Ver logs del servicio backend
railway logs

# Ver logs con follow (stream continuo)
railway logs --follow
```

---

## 🛠️ Ejecutar Scripts en Producción

### Ejecutar script de columnas normalizadas

```bash
# Opción 1: Con Railway CLI (recomendado)
railway run python backend/scripts/add_normalized_columns.py

# Opción 2: Con variables de entorno
railway run python -c "from backend.app.config import get_settings; print(get_settings().DATABASE_URL)"
```

### Verificar que producción está lista

```bash
railway run python backend/scripts/verify_production_ready.py
```

---

## 📊 Consultas Útiles

### Estadísticas de la base de datos

```bash
# Contar registros en cada tabla
railway run psql -c "
SELECT
  'apsa_protocols' as tabla, COUNT(*) as registros FROM apsa_protocols
UNION ALL
SELECT 'aconex_docs', COUNT(*) FROM aconex_docs
UNION ALL
SELECT 'users', COUNT(*) FROM users
UNION ALL
SELECT 'loads', COUNT(*) FROM loads;
"
```

### Ver tamaño de la base de datos

```bash
railway run psql -c "
SELECT
  pg_size_pretty(pg_database_size(current_database())) as tamaño_total,
  current_database() as base_datos;
"
```

### Ver índices en apsa_protocols

```bash
railway run psql -c "\d apsa_protocols"
```

---

## 🔧 Variables de Entorno

### Ver variables configuradas

```bash
# Listar todas las variables de entorno
railway variables

# Ver valor de una variable específica
railway variables get DATABASE_URL
```

### Setear variables (si es necesario)

```bash
# Setear una variable
railway variables set APP_SECRET=tu_nuevo_secret

# Borrar una variable
railway variables delete VARIABLE_NAME
```

---

## 🚀 Deployment

### Trigger manual deployment (si Railway está conectado a GitHub)

```bash
# Railway auto-deploys cuando haces push a GitHub
# Pero si quieres forzar un redeploy:

# Ver deployments recientes
railway deployments

# Redeploy el último deployment
railway up
```

---

## 🆘 Troubleshooting

### "No project linked"

```bash
railway link
# Selecciona tu proyecto de la lista
```

### "Database connection refused"

```bash
# Verifica que estás en el proyecto correcto
railway status

# Verifica que la base de datos está corriendo
railway ps

# Revisa los logs
railway logs
```

### "pg_dump: command not found"

```bash
# Instala PostgreSQL client en tu máquina local:
# Windows: https://www.postgresql.org/download/windows/
# Mac: brew install postgresql
# Linux: sudo apt-get install postgresql-client
```

---

## 📝 Workflow Recomendado para Deployment

```bash
# 1. Login y link
railway login
railway link

# 2. Crear backup ANTES de cualquier cambio
railway run pg_dump > backups/backup_pre_deployment_$(date +%Y%m%d_%H%M%S).sql

# 3. Verificar que producción está lista
railway run python backend/scripts/verify_production_ready.py

# 4. Si necesitas ejecutar migraciones
railway run python backend/scripts/add_normalized_columns.py

# 5. Verificar nuevamente
railway run python backend/scripts/verify_production_ready.py

# 6. Hacer deployment (push a GitHub)
git push origin main

# 7. Monitorear logs
railway logs --follow
```

---

## 🔗 Recursos

- **Railway Docs:** https://docs.railway.app
- **Railway CLI Docs:** https://docs.railway.app/develop/cli
- **Dashboard Railway:** https://railway.app/dashboard

---

## 💡 Tips

1. **Siempre crea backup antes de cambios importantes**
2. **Usa `railway run` para ejecutar comandos en el contexto de Railway**
3. **Los logs son tu mejor amigo para debugging**
4. **Railway auto-deploys desde GitHub - no necesitas comandos especiales**
5. **Puedes conectarte directamente con psql para queries ad-hoc**

---

**¡Éxito con Railway! 🚂**
