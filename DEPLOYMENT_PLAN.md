# 🚀 Plan de Deployment Seguro a Producción

## ⚠️ IMPORTANTE: LEE TODO ANTES DE EMPEZAR

Este documento te guiará paso a paso para levantar la nueva versión a producción sin romper nada.

---

## 📋 Pre-requisitos

### Accesos necesarios:
- [ ] Acceso a Railway (base de datos)
- [ ] Acceso a Render (backend + frontend)
- [ ] Acceso a GitHub (repositorio)
- [ ] Acceso al proyecto local actualizado

---

## 🛡️ FASE 1: BACKUP Y PREPARACIÓN (CRÍTICO)

### 1.1 Backup de Base de Datos en Railway

**⚠️ ESTO ES LO MÁS IMPORTANTE - NO SALTARSE**

1. Ve a Railway → Tu proyecto → PostgreSQL
2. Ve a la pestaña "Data" o "Backups"
3. Crea un backup manual:
   - Si Railway tiene opción "Create Backup" → úsala
   - Si no, descarga un dump manual:

```bash
# Opción A: Desde Railway CLI (recomendado)
railway login
railway link
railway run pg_dump > backup_pre_deployment_$(date +%Y%m%d_%H%M%S).sql

# Opción B: Desde tu máquina local (necesitas URL de conexión)
# Ve a Railway → PostgreSQL → Connect → Copy Database URL
# Luego ejecuta:
pg_dump "postgresql://usuario:password@host:puerto/database" > backup_pre_deployment_$(date +%Y%m%d_%H%M%S).sql
```

4. **Verifica que el backup se creó correctamente:**
   - Revisa el tamaño del archivo (debe ser varios MB)
   - Guárdalo en un lugar seguro (fuera del proyecto)

✅ **Checkpoint:** Tienes backup completo guardado en lugar seguro

---

### 1.2 Verificar Columnas Normalizadas en Producción

**CRÍTICO:** Las columnas `codigo_cmdic_norm`, `subsistema_norm`, etc. deben existir en producción.

**¿Ya ejecutaste el script `add_normalized_columns.py` en producción?**

- [ ] SÍ → Continúa al siguiente paso
- [ ] NO → Debes ejecutarlo ANTES de hacer deployment

**Si NO:**

```bash
# Opción A: Ejecutar desde Railway CLI
railway login
railway link
railway run python scripts/add_normalized_columns.py

# Opción B: Ejecutar localmente apuntando a Railway
# 1. Copia la DATABASE_URL de Railway
# 2. Crea un .env temporal:
DATABASE_URL=postgresql://usuario:password@host:puerto/database
# 3. Ejecuta:
python scripts/add_normalized_columns.py
```

✅ **Checkpoint:** Columnas normalizadas existen en producción

---

### 1.3 Verificar Variables de Entorno

**Backend (Render):**

Ve a Render → Tu servicio backend → Environment

Verifica que existan estas variables:

```
DATABASE_URL=postgresql://...  (de Railway)
APP_SECRET=tu_secret_aqui
AUTH_PROVIDER=local
API_ISSUER=quality.local
API_AUDIENCE=quality.api
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7
```

**Frontend (Render):**

Ve a Render → Tu servicio frontend → Environment

Verifica que exista:

```
VITE_API_URL=https://tu-backend.onrender.com
```

✅ **Checkpoint:** Variables de entorno configuradas correctamente

---

## 🔄 FASE 2: PREPARAR CÓDIGO PARA DEPLOYMENT

### 2.1 Revisar cambios locales

```bash
cd C:\AppServ\www\quality-app
git status
```

**Verifica que tengas estos cambios:**
- ✅ `backend/app/security.py` - Parámetros Argon2 optimizados + re-hash
- ✅ `backend/app/main.py` - Re-hash progresivo en login + queries optimizadas
- ✅ `frontend/src/pages/Dashboard.tsx` - Colores suavizados
- ✅ `frontend/src/pages/LogProtocolos.tsx` - Diseño mejorado
- ✅ `frontend/src/App.tsx` - Full width para LogProtocolos

### 2.2 Crear branch de release (RECOMENDADO)

```bash
# Crea un branch de respaldo por si acaso
git branch backup-pre-production

# Crea un branch para release
git checkout -b release-v1.0

# Verifica que estás en el branch correcto
git branch
```

✅ **Checkpoint:** Código revisado y branch creado

---

## 🚀 FASE 3: DEPLOYMENT

### 3.1 Commit y Push

```bash
# Agrega todos los cambios
git add .

# Commit con mensaje descriptivo
git commit -m "feat: Optimizaciones de rendimiento y mejoras visuales

- Optimizar parámetros Argon2 para login más rápido (5-10x mejora)
- Implementar re-hash progresivo de contraseñas
- Optimizar queries con columnas normalizadas
- Mejorar diseño Dashboard con colores suaves
- Diseño completo LogProtocolos con filtros verticales
- Soporte full-width para LogProtocolos

🤖 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>"

# Push al repositorio
git push origin release-v1.0
```

### 3.2 Deployment en Render - BACKEND PRIMERO

**⚠️ IMPORTANTE: Despliega BACKEND primero, luego FRONTEND**

1. **Ve a Render → Tu servicio Backend**
2. Ve a "Settings" → "Build & Deploy"
3. Cambia el branch a `release-v1.0` (o el que uses)
4. **Opción Manual (RECOMENDADO para primera vez):**
   - Ve a "Manual Deploy"
   - Selecciona el branch `release-v1.0`
   - Click "Deploy latest commit"
   - **NO CIERRES LA VENTANA - Observa los logs**

5. **Monitorea el deployment:**
   - Observa los logs en tiempo real
   - Busca errores (líneas rojas)
   - Espera a ver "Your service is live 🎉"

6. **Verifica que el backend funciona:**
   - Abre: `https://tu-backend.onrender.com/health`
   - Debe responder: `{"status": "ok"}`
   - Prueba login: `https://tu-backend.onrender.com/docs` → `/auth/login`

✅ **Checkpoint:** Backend desplegado y funcionando

**⚠️ SI ALGO FALLA EN BACKEND:**
```bash
# ROLLBACK INMEDIATO:
# 1. Ve a Render → Backend → Manual Deploy
# 2. Selecciona el commit anterior (antes de tus cambios)
# 3. Deploy
# 4. Revisa los logs para ver qué falló
```

### 3.3 Deployment en Render - FRONTEND

**Solo si el backend funciona correctamente:**

1. **Ve a Render → Tu servicio Frontend**
2. Repite el proceso del backend:
   - Settings → Build & Deploy
   - Manual Deploy → branch `release-v1.0`
   - Click "Deploy latest commit"
   - **Observa los logs**

3. **Verifica que el frontend funciona:**
   - Abre tu URL de frontend: `https://tu-frontend.onrender.com`
   - Debe cargar la página de login
   - Intenta hacer login
   - Verifica que el Dashboard carga

✅ **Checkpoint:** Frontend desplegado y funcionando

---

## ✅ FASE 4: TESTING EN PRODUCCIÓN

### 4.1 Tests Críticos

**Ejecuta estas pruebas EN ORDEN:**

1. **Login:**
   - [ ] Login con usuario existente funciona
   - [ ] Login es rápido (< 1 segundo)
   - [ ] Redirecciona al Dashboard correctamente

2. **Dashboard:**
   - [ ] Carga las métricas principales
   - [ ] Los colores se ven suaves (no chillones)
   - [ ] Las progress bars funcionan
   - [ ] Los tabs de subsistemas funcionan (Obra, Mecánico, I&E, General)
   - [ ] Las descargas CSV funcionan

3. **Log Protocolos:**
   - [ ] La página carga en full-width
   - [ ] Los filtros verticales funcionan
   - [ ] La búsqueda es rápida (< 5 segundos)
   - [ ] Export a Excel funciona
   - [ ] Filtros nuevos funcionan (Grupo Disciplinas, Sin Aconex)

4. **Uploads (CRÍTICO):**
   - [ ] Subir Excel APSA funciona
   - [ ] Es más rápido que antes (debe ser < 2 minutos)
   - [ ] Subir Excel Aconex funciona
   - [ ] Es más rápido que antes

5. **Usuarios Admin:**
   - [ ] Página de usuarios funciona
   - [ ] Crear nuevo usuario funciona

### 4.2 Monitoreo Post-Deployment

**Durante las próximas 2-4 horas:**

1. **Revisa logs de Render:**
   - Backend: Busca errores (500, crashes)
   - Frontend: Busca errores de compilación

2. **Monitorea Railway:**
   - Revisa conexiones activas
   - Revisa uso de CPU/RAM
   - Busca queries lentas

3. **Prueba login de varios usuarios:**
   - Confirma que el re-hash progresivo funciona
   - Verifica que el segundo login es más rápido

---

## 🔙 PLAN DE ROLLBACK (Si algo sale mal)

### Si el Backend falla:

```bash
# Opción 1: Rollback en Render
# 1. Render → Backend → Manual Deploy
# 2. Selecciona el commit anterior
# 3. Deploy

# Opción 2: Desde Git
git checkout main  # o el branch anterior
git push origin main --force  # Solo si es urgente
```

### Si la Base de Datos se corrompe:

```bash
# Opción 1: Restaurar desde Railway Backup
# 1. Railway → PostgreSQL → Backups
# 2. Restore backup

# Opción 2: Restaurar desde tu backup local
railway run psql < backup_pre_deployment_YYYYMMDD_HHMMSS.sql
```

### Si el Frontend falla:

```bash
# Mismo proceso que backend
# Render → Frontend → Manual Deploy → commit anterior
```

---

## 📞 CHECKLIST FINAL PRE-DEPLOYMENT

Antes de hacer push, verifica:

- [ ] Backup de base de datos creado y guardado
- [ ] Columnas normalizadas existen en producción
- [ ] Variables de entorno configuradas en Render
- [ ] Código revisado localmente
- [ ] Branch de backup creado (`backup-pre-production`)
- [ ] Plan de rollback entendido
- [ ] Horario de deployment elegido (evita horas pico)

---

## ⏰ RECOMENDACIONES DE TIMING

**Mejor momento para deployment:**
- ✅ Fuera de horas laborales (menos usuarios)
- ✅ Día entre semana (no viernes - por si hay que arreglar algo)
- ✅ Cuando tengas 2-3 horas libres para monitorear

**Evitar:**
- ❌ Viernes tarde (si algo falla, te quedas el fin de semana)
- ❌ Horario pico de usuarios
- ❌ Cuando estés apurado

---

## 📝 NOTAS IMPORTANTES

1. **Render auto-deploys:** Si tienes auto-deploy activado en Render, apenas hagas push a `main` (o tu branch configurado), se desplegará automáticamente. Considera desactivarlo temporalmente para control manual.

2. **Railway no se toca:** La base de datos NO necesita deployment, solo el script de columnas normalizadas (si no lo ejecutaste ya).

3. **Orden importa:** SIEMPRE backend primero, luego frontend.

4. **Los usuarios no se afectarán:** El re-hash es transparente, el login será más rápido desde el primer intento.

---

## ✅ CHECKLIST POST-DEPLOYMENT

Después de desplegar con éxito:

- [ ] Todos los tests pasaron
- [ ] Usuarios pueden hacer login
- [ ] Dashboard carga correctamente
- [ ] LogProtocolos funciona
- [ ] Uploads son más rápidos
- [ ] No hay errores en logs de Render
- [ ] No hay errores en Railway
- [ ] Performance mejoró (login más rápido, queries más rápidas)

**Si todo está ✅, puedes:**
```bash
# Merge a main si usaste release branch
git checkout main
git merge release-v1.0
git push origin main

# Borra el branch de backup después de 1 semana
# git branch -d backup-pre-production
```

---

## 🆘 CONTACTOS DE EMERGENCIA

Si algo sale muy mal:

1. **Rollback inmediato** (ver sección anterior)
2. **Restaurar backup de Railway**
3. **Revisar logs de Render** para identificar el problema
4. **No entres en pánico** - tienes backup de todo

---

**¡Éxito con el deployment! 🚀**

Recuerda: Es mejor ir despacio y seguro que rápido y romper todo.
