# ✅ Checklist de Deployment a Producción

**Imprime o ten esta página abierta durante el deployment**

---

## 📅 Información del Deployment

- **Fecha:** ___________________
- **Hora inicio:** ___________________
- **Persona responsable:** ___________________
- **Versión:** v1.0 (Optimizaciones + Mejoras visuales)

---

## 🎯 PRE-DEPLOYMENT

### Preparación (30 min antes)

- [ ] Leí el `DEPLOYMENT_PLAN.md` completo
- [ ] Tengo 1-2 horas libres para monitorear
- [ ] No es viernes tarde ni horario pico
- [ ] Tengo accesos a Railway, Render y GitHub
- [ ] Branch de respaldo creado: `backup-pre-production`

### Backup de Base de Datos ⚠️ CRÍTICO

- [ ] Backup creado en Railway (UI o CLI)
- [ ] Backup descargado y guardado localmente
- [ ] Tamaño del backup verificado (debe ser varios MB)
- [ ] Copia del backup guardada en lugar seguro (Google Drive, etc.)
- [ ] **Hora del backup:** ___________________

### Verificación de Producción

- [ ] Ejecuté `verify_production_ready.py` apuntando a Railway
- [ ] Script dice: ✅ "Base de datos lista para deployment"
- [ ] Columnas normalizadas existen y tienen datos
- [ ] Índices importantes existen

### Variables de Entorno

**Render - Backend:**
- [ ] `DATABASE_URL` configurado (de Railway)
- [ ] `APP_SECRET` configurado
- [ ] `AUTH_PROVIDER=local`
- [ ] `API_ISSUER=quality.local`
- [ ] `API_AUDIENCE=quality.api`
- [ ] `ACCESS_TOKEN_EXPIRE_MINUTES=60`
- [ ] `REFRESH_TOKEN_EXPIRE_DAYS=7`

**Render - Frontend:**
- [ ] `VITE_API_URL` configurado (apunta a backend en Render)

---

## 🚀 DEPLOYMENT

### Git & GitHub

- [ ] `git status` - Revisar cambios locales
- [ ] `git add .` - Agregar todos los cambios
- [ ] `git commit` - Commit con mensaje descriptivo
- [ ] `git push origin main` - Push a GitHub
- [ ] Commit visible en GitHub

### Render - Backend ⚠️ DESPLEGAR PRIMERO

- [ ] Abrir Render → Backend Service
- [ ] Auto-deploy iniciado (o trigger manual)
- [ ] Logs abiertos y monitoreando
- [ ] Build completó sin errores
- [ ] Deploy completó sin errores
- [ ] Mensaje: "Your service is live 🎉"
- [ ] **Hora deployment:** ___________________

**Verificación Backend:**
- [ ] `https://tu-backend.onrender.com/health` responde `{"status":"ok"}`
- [ ] `https://tu-backend.onrender.com/docs` carga Swagger UI
- [ ] No hay errores en logs de Render

### Render - Frontend ⚠️ DESPLEGAR DESPUÉS

- [ ] Abrir Render → Frontend Service
- [ ] Auto-deploy iniciado (o trigger manual)
- [ ] Logs abiertos y monitoreando
- [ ] Build completó sin errores
- [ ] Deploy completó sin errores
- [ ] Mensaje: "Your service is live 🎉"
- [ ] **Hora deployment:** ___________________

**Verificación Frontend:**
- [ ] `https://tu-frontend.onrender.com` carga
- [ ] Página de login visible
- [ ] No hay errores en console del navegador

---

## ✅ TESTING POST-DEPLOYMENT

### Tests Funcionales Básicos

**Login:**
- [ ] Login con usuario existente funciona
- [ ] Login es rápido (< 1 segundo)
- [ ] Redirecciona a Dashboard correctamente
- [ ] Perfil de usuario se muestra en header

**Dashboard:**
- [ ] Página carga sin errores
- [ ] Métricas principales se muestran
- [ ] Colores se ven suaves (no chillones)
- [ ] Progress bars funcionan
- [ ] Hero section con degradado suave visible
- [ ] Menú de descargas funciona

**Tabs de Subsistemas:**
- [ ] Tab "Obra civil" carga datos
- [ ] Tab "Mecánico Pipping" carga datos
- [ ] Tab "I&E" carga datos
- [ ] Tab "General" carga datos (suma de todos)

**Descargas:**
- [ ] Exportar CSV de grupos funciona
- [ ] Exportar CSV de disciplinas funciona
- [ ] Exportar CSV de subsistemas funciona

**Log Protocolos:**
- [ ] Página carga en full-width (sin padding lateral)
- [ ] Filtros verticales a la izquierda visibles
- [ ] Búsqueda funciona
- [ ] Búsqueda es rápida (< 5 segundos)
- [ ] Filtro "Grupo Disciplinas" funciona
- [ ] Filtro "Sin cargar aconex" funciona
- [ ] Export a Excel funciona
- [ ] Resultados se muestran correctamente

**Admin (solo si eres Admin):**
- [ ] Página de usuarios accesible
- [ ] Listar usuarios funciona
- [ ] Crear nuevo usuario funciona

---

## 🔍 TESTING AVANZADO

### Performance

**Login:**
- [ ] Primer login después de deployment (puede ser lento si hash antiguo)
- [ ] Segundo login del mismo usuario (debe ser rápido < 500ms)
- [ ] Re-hash progresivo funcionando (segundo login más rápido)

**Queries:**
- [ ] Dashboard carga en < 2 segundos
- [ ] Log Protocolos búsqueda < 5 segundos (antes: minutos)
- [ ] Filtros responden rápidamente

**Uploads (si puedes probar):**
- [ ] Upload Excel APSA funciona
- [ ] Upload es más rápido que antes (target: < 2 min)
- [ ] Upload Excel Aconex funciona
- [ ] Upload es más rápido que antes

---

## 📊 MONITOREO POST-DEPLOYMENT

### Primeras 2 horas

- [ ] Revisar logs de Render Backend cada 30 min
- [ ] Revisar logs de Render Frontend cada 30 min
- [ ] Monitorear Railway (CPU, RAM, conexiones)
- [ ] Probar login de 2-3 usuarios diferentes
- [ ] Confirmar que no hay errores 500

### Primeras 24 horas

- [ ] Revisar logs 1 vez cada 4 horas
- [ ] Monitorear quejas de usuarios (si hay)
- [ ] Verificar que performance mejoró
- [ ] Confirmar que backups automáticos de Railway funcionan

---

## ⚠️ PROBLEMAS Y ROLLBACK

### Si algo falla (marcar si aplica)

**Backend no responde:**
- [ ] Revisé logs de Render
- [ ] Error identificado: ___________________
- [ ] Rollback ejecutado en Render (commit anterior)
- [ ] Backend funcionando nuevamente

**Frontend roto:**
- [ ] Revisé logs de Render
- [ ] Revisé console del navegador
- [ ] Error identificado: ___________________
- [ ] Rollback ejecutado en Render (commit anterior)
- [ ] Frontend funcionando nuevamente

**Base de datos corrupta:**
- [ ] Backup restaurado desde Railway
- [ ] Datos verificados
- [ ] Aplicación funcionando

**Performance peor que antes:**
- [ ] Verificar que columnas normalizadas existen
- [ ] Verificar que índices existen
- [ ] Revisar queries en logs
- [ ] Consultar con desarrollador

---

## 🎉 DEPLOYMENT EXITOSO

### Confirmación Final

- [ ] Todos los tests pasaron
- [ ] No hay errores en logs
- [ ] Performance mejoró
- [ ] Usuarios pueden usar la aplicación normalmente
- [ ] Cambios visuales se ven correctamente

### Post-Deployment

- [ ] Merge a `main` si usé branch de release
- [ ] Actualizar documentación si es necesario
- [ ] Notificar a usuarios de mejoras (opcional)
- [ ] Celebrar 🎉

---

## 📝 Notas del Deployment

**Problemas encontrados:**
```
_______________________________________________________________
_______________________________________________________________
_______________________________________________________________
```

**Soluciones aplicadas:**
```
_______________________________________________________________
_______________________________________________________________
_______________________________________________________________
```

**Tiempo total de deployment:**
```
Inicio: ___________________
Fin:    ___________________
Total:  ___________________
```

**Resultado:**
- [ ] ✅ Exitoso - Sin problemas
- [ ] ⚠️  Exitoso - Con problemas menores resueltos
- [ ] ❌ Fallido - Rollback ejecutado

---

**Firma:** _____________________  **Fecha:** _____________________

---

## 📞 Contactos de Emergencia

Si necesitas ayuda:
1. Revisar `DEPLOYMENT_PLAN.md` para troubleshooting detallado
2. Revisar logs de Render y Railway
3. Ejecutar rollback si es necesario
4. No entrar en pánico - tienes backup de todo

---

**¡Éxito! 🚀**
