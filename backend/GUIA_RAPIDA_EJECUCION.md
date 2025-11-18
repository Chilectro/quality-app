# 🚀 Guía Rápida de Ejecución

## ⚠️ ERROR COMÚN: "pydantic_core._pydantic_core.ValidationError"

Si ves este error al ejecutar los scripts:
```
pydantic_core._pydantic_core.ValidationError
```

**Causa:** Estás ejecutando desde el directorio incorrecto o faltan variables en `.env`.

---

## ✅ SOLUCIÓN:

### 1. Cambiar al directorio correcto

```powershell
# Desde PowerShell
cd C:\AppServ\www\quality-app\backend

# Verificar que estás en el directorio correcto:
pwd
# Debe mostrar: C:\AppServ\www\quality-app\backend
```

### 2. Verificar que .env existe y está completo

```powershell
# Ver contenido de .env
cat .env
```

**Debe contener AL MENOS:**
```
DB_USER=tu_usuario
DB_PASSWORD=tu_password
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=quality_db
APP_SECRET=cualquier_secreto_aleatorio
```

Si falta alguna variable o el archivo no existe:
```powershell
# Copiar el ejemplo
cp .env.example .env

# Editar con tus datos
notepad .env
```

---

## 📋 ORDEN DE EJECUCIÓN CORRECTO

### Desde el directorio backend:

```powershell
# 1. Verificar conexión
python scripts/verify_connection.py

# 2. Agregar columnas normalizadas (SOLUCIÓN DEFINITIVA)
python scripts/add_normalized_columns.py

# 3. (Opcional) Agregar índices básicos
python scripts/add_indexes.py
```

---

## ⚠️ ERRORES COMUNES:

### Error: "No module named 'app'"

**Causa:** Ejecutando desde directorio incorrecto

**Solución:**
```powershell
cd C:\AppServ\www\quality-app\backend
python scripts/verify_connection.py
```

### Error: "Field required" o "ValidationError"

**Causa:** Faltan variables en .env

**Solución:** Edita `.env` y agrega las variables faltantes

### Error: "Access denied"

**Causa:** Usuario de MySQL sin permisos de ALTER TABLE

**Solución:** Ejecutar SQL manual como admin o dar permisos:
```sql
GRANT ALL PRIVILEGES ON quality_db.* TO 'tu_usuario'@'localhost';
FLUSH PRIVILEGES;
```

---

## 🎯 OBJETIVO: Solucionar "Error de SS" lento

**Problema:** `/metrics/cards` tarda >15 minutos

**Solución:** Ejecutar `add_normalized_columns.py`

**Resultado esperado:** De >15 min a 1-3 segundos

---

## 📞 Si sigue fallando:

1. **Verifica que MySQL esté corriendo:**
   ```powershell
   # Desde servicios de Windows
   Get-Service MySQL*
   ```

2. **Prueba conectarte manualmente:**
   ```powershell
   mysql -u tu_usuario -p quality_db
   ```

3. **Revisa los logs completos:**
   Copia el error completo y compártelo para ayuda específica.

---

## ✅ Checklist Final:

- [ ] Estoy en el directorio `backend` (verificar con `pwd`)
- [ ] El archivo `.env` existe (verificar con `ls .env`)
- [ ] El archivo `.env` tiene todas las variables requeridas
- [ ] MySQL está corriendo
- [ ] Puedo conectarme a MySQL con las credenciales del `.env`
- [ ] Ejecuto: `python scripts/verify_connection.py`
- [ ] Si funciona, ejecuto: `python scripts/add_normalized_columns.py`

---

**Última actualización:** 2025-11-17
