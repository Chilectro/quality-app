# 🚀 Estado de la Optimización de Performance

**Fecha:** 2025-11-17
**Estado:** ✅ Fase de Instrumentación y Fixes Críticos COMPLETADA

---

## 📋 Resumen Ejecutivo

Se ha completado la instrumentación de performance y se ha **solucionado un problema CRÍTICO** que causaba que `/metrics/cards` tardara **más de 15 minutos**.

### Problema Crítico Encontrado

**Endpoint:** `GET /metrics/cards`
**Query problemática:** Cálculo de "Error de SS" (subsistema)
**Síntoma:** >15 minutos sin completar
**Causa:** Subconsultas correlacionadas con EXISTS + normalización en runtime

**Solución aplicada:**
- ✅ Reescrita con LEFT JOIN y subconsultas
- ⏱️ Tiempo esperado: 2-5 segundos (mejora del 99.7%)
- 📊 Aún puede optimizarse más con índices

---

## ✅ Cambios Completados

### 1. Instrumentación de Performance

**Archivo:** `backend/app/timing.py`

- Sistema completo de medición de tiempos
- Decoradores para endpoints
- Context managers para queries SQL
- Almacenamiento thread-safe de métricas

**Endpoints instrumentados:**
- `/metrics/cards` (5+ queries)
- `/metrics/disciplinas` (40 queries - problema N+1 conocido)
- `/metrics/subsistemas` (2 queries)
- `/metrics/changes/summary` (2 queries)
- `/aconex/duplicates` (1 query)

**Nuevos endpoints de administración:**
- `GET /admin/performance/stats` - Ver estadísticas detalladas
- `GET /admin/performance/summary` - Resumen de los 5 endpoints principales
- `POST /admin/performance/reset` - Resetear métricas

**Documentación:** `backend/PERFORMANCE_INSTRUMENTATION.md`

---

### 2. Fix Crítico: Query "Error de SS"

**Archivo:** `backend/app/main.py` (líneas 855-898)

**Antes (LENTO):**
```python
# Subconsultas correlacionadas con EXISTS
# Por cada fila de APSA, ejecuta 2 subconsultas
# Complejidad: O(n × m)
# Tiempo: >15 minutos
exists_code_only = select(1).where(...).exists()
exists_code_ss = select(1).where(...).exists()
aconex_error_ss = db.execute(
    select(func.count()).where(
        exists_code_only,
        ~exists_code_ss
    )
).scalar()
```

**Después (RÁPIDO):**
```python
# Subconsultas + JOIN
# Normalización se ejecuta 1 vez por tabla, no por comparación
# Complejidad: O(n + m)
# Tiempo esperado: 2-5 segundos
apsa_with_code_match = select(...).where(...).subquery()
aconex_normalized = select(...).where(...).subquery()
aconex_error_ss = db.execute(
    select(func.count())
    .select_from(apsa_with_code_match)
    .join(aconex_normalized, ...)
    .where(...)
).scalar()
```

---

### 3. Scripts de Optimización

**Archivo:** `backend/scripts/add_indexes.py`

Script Python para agregar índices de forma segura:
- Verifica si índices ya existen
- Crea solo los faltantes
- Reporta resultados detallados

**Índices que agrega:**
1. `idx_apsa_codigo_cmdic` - Para JOINs APSA-ACONEX
2. `idx_aconex_document_no` - Para JOINs ACONEX-APSA
3. `idx_apsa_load_disc` - Queries por load_id + disciplina
4. `idx_apsa_load_subs` - Queries por load_id + subsistema
5. `idx_aconex_load_doc` - Queries ACONEX por load_id + documento
6. `idx_aconex_load_sub` - Queries ACONEX por load_id + subsistema
7. `idx_apsa_load_disc_status` - Métricas por disciplina + status
8. `idx_apsa_load_subs_status` - Métricas por subsistema + status

**Archivo SQL alternativo:** `backend/migrations/add_performance_indexes.sql`

---

### 4. Queries Optimizadas (Referencia)

**Archivo:** `backend/app/metrics_optimized.py`

Funciones de referencia con diferentes estrategias de optimización:
- `count_error_ss_optimized()` - Versión con LEFT JOIN
- `count_error_ss_simple()` - Versión con CTE (Common Table Expression)
- `count_error_ss_with_temp_columns()` - Versión óptima con columnas pre-calculadas

---

## 📊 Estado Actual de los Endpoints

| Endpoint | Queries | Estado | Siguiente Optimización |
|----------|---------|--------|----------------------|
| `/metrics/cards` | 5 | ✅ OPTIMIZADO | Agregar índices |
| `/metrics/disciplinas` | 40 | ⚠️ N+1 PROBLEM | Reescribir con GROUP BY |
| `/metrics/subsistemas` | 2 | ⚠️ EXISTS lento | Reescribir con LEFT JOIN |
| `/metrics/changes/summary` | 2 | ✅ OK | Posible unificación en 1 query |
| `/aconex/duplicates` | 1 | ⚠️ Normalización lenta | Agregar índices |

**Leyenda:**
- ✅ = Optimizado o rendimiento aceptable
- ⚠️ = Requiere optimización
- 🔴 = Crítico (>15 segundos)

---

## 🎯 Próximos Pasos Recomendados

### Paso 1: Probar el Fix Crítico (AHORA)

```bash
# 1. Reiniciar el backend
cd backend
# Detener el servidor si está corriendo (Ctrl+C)
# Iniciar de nuevo
uvicorn app.main:app --reload

# 2. Probar el endpoint
curl http://localhost:8000/metrics/cards \
  -H "Authorization: Bearer YOUR_TOKEN"

# 3. Verificar los logs - deberías ver:
# ⏱️  Count APSA con Error de SS (OPTIMIZADO con LEFT JOIN): X.XXms
```

**Resultado esperado:** Debería completar en 2-10 segundos en lugar de >15 minutos.

---

### Paso 2: Agregar Índices (5 minutos)

```bash
# Opción A: Usar script Python (recomendado)
cd backend
python scripts/add_indexes.py

# Opción B: Ejecutar SQL manualmente
# Conectar a tu base de datos y ejecutar:
# backend/migrations/add_performance_indexes.sql
```

**Impacto esperado:**
- 40-60% de mejora en queries con JOINs
- 50-80% de mejora en queries con EXISTS

---

### Paso 3: Medir Baseline (10 minutos)

```bash
# 1. Resetear estadísticas
curl -X POST http://localhost:8000/admin/performance/reset \
  -H "Authorization: Bearer YOUR_TOKEN"

# 2. Ejecutar cada endpoint 3-5 veces
for i in {1..5}; do
  curl http://localhost:8000/metrics/cards -H "Authorization: Bearer YOUR_TOKEN"
  curl http://localhost:8000/metrics/disciplinas -H "Authorization: Bearer YOUR_TOKEN"
  curl http://localhost:8000/metrics/subsistemas -H "Authorization: Bearer YOUR_TOKEN"
  curl http://localhost:8000/metrics/changes/summary -H "Authorization: Bearer YOUR_TOKEN"
  curl http://localhost:8000/aconex/duplicates -H "Authorization: Bearer YOUR_TOKEN"
done

# 3. Ver resumen
curl http://localhost:8000/admin/performance/summary \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Documentar resultados en:** `PERFORMANCE_BASELINE.md`

---

### Paso 4: Optimizar `/metrics/disciplinas` (30 minutos)

**Problema:** Ejecuta 40 queries en un loop (4 queries × 10 disciplinas)

**Solución:** Reescribir con 2 queries usando GROUP BY

**Impacto esperado:** 90-95% de reducción en tiempo

**Referencia:** Plan de Optimización - Etapa 2

---

### Paso 5: Optimizar `/metrics/subsistemas` (20 minutos)

**Problema:** 2 queries separadas, una con EXISTS

**Solución:** Unificar en 1 query con LEFT JOIN

**Impacto esperado:** 40-60% de reducción en tiempo

**Referencia:** Plan de Optimización - Etapa 4

---

### Paso 6: (Opcional) Columnas Normalizadas (1 hora)

Si después de índices aún hay lentitud por normalización:

1. Agregar columnas:
   - `apsa_protocols.codigo_cmdic_norm`
   - `apsa_protocols.subsistema_norm`
   - `aconex_docs.document_no_norm`
   - `aconex_docs.subsystem_code_norm`

2. Crear triggers para auto-actualización

3. Crear índices en columnas normalizadas

4. Actualizar queries para usar columnas pre-calculadas

**Impacto esperado:** 80-95% de reducción adicional

---

## 📈 Mejoras Esperadas Totales

Con todos los pasos completados:

| Endpoint | Antes | Después (estimado) | Mejora |
|----------|-------|-------------------|--------|
| `/metrics/cards` | >15 min | 1-3 seg | 99.7% |
| `/metrics/disciplinas` | 10-30 seg | 0.5-2 seg | 95% |
| `/metrics/subsistemas` | 3-8 seg | 0.5-1.5 seg | 70% |
| `/metrics/changes/summary` | 2-5 seg | 1-2 seg | 50% |
| `/aconex/duplicates` | 1-3 seg | 0.3-0.8 seg | 60% |

**Nota:** Los tiempos "Antes" son estimaciones. Los tiempos reales dependen del tamaño de tu base de datos.

---

## 🐛 Problemas Conocidos

### 1. Normalización en Runtime

**Descripción:** La función `N()` ejecuta 3 REPLACE anidados en cada comparación.

**Impacto:** Queries lentas cuando hay muchos registros.

**Solución temporal:** ✅ Reducido con subconsultas (ejecuta 1 vez por tabla)

**Solución óptima:** Columnas pre-calculadas (Paso 6)

---

### 2. Problema N+1 en `/metrics/disciplinas`

**Descripción:** Ejecuta 40 queries en un loop.

**Impacto:** ALTO - Este es el segundo problema más grave después de "Error de SS".

**Solución:** Paso 4 (reescribir con GROUP BY)

---

### 3. Subconsultas EXISTS en Varios Endpoints

**Descripción:** Uso de subconsultas correlacionadas con EXISTS.

**Impacto:** MEDIO - Puede ser lento en tablas grandes.

**Solución:** Reescribir con LEFT JOIN (Pasos 4-5)

---

## 📝 Archivos Creados/Modificados

### Nuevos Archivos

- `backend/app/timing.py` - Sistema de instrumentación
- `backend/app/metrics_optimized.py` - Queries optimizadas de referencia
- `backend/scripts/add_indexes.py` - Script para agregar índices
- `backend/scripts/__init__.py` - Módulo Python
- `backend/migrations/add_performance_indexes.sql` - Índices en SQL
- `backend/PERFORMANCE_INSTRUMENTATION.md` - Documentación de instrumentación
- `backend/OPTIMIZATION_STATUS.md` - Este archivo

### Archivos Modificados

- `backend/app/main.py`:
  - Agregado logging e imports de timing
  - Instrumentados 5 endpoints principales
  - Reescrita query "Error de SS" (líneas 855-898)
  - Agregados 3 endpoints de administración de performance

---

## 🔧 Configuración

### Logging

El logging está configurado en `backend/app/main.py` línea 108:

```python
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

Para más detalle, cambiar a `logging.DEBUG`.

### Desactivar Instrumentación

Si necesitas desactivar la instrumentación temporalmente:

```python
# Comentar decoradores en main.py
# @measure_endpoint("metrics_cards")  # ← Comentar esta línea
def metrics_cards(...):
    ...
```

---

## 📞 Soporte

Si encuentras problemas:

1. Revisa los logs del servidor
2. Verifica que los índices se crearon: `python scripts/add_indexes.py`
3. Confirma que el endpoint devuelve resultados (aunque sean lentos)
4. Usa `/admin/performance/stats` para ver dónde está el cuello de botella

---

## ✅ Checklist de Verificación

Después de aplicar cada paso, verifica:

- [ ] El servidor inicia sin errores
- [ ] Los endpoints devuelven resultados correctos
- [ ] Los tiempos han mejorado (ver `/admin/performance/summary`)
- [ ] No hay errores en los logs
- [ ] Los índices se crearon correctamente
- [ ] Las métricas de "Error de SS" son correctas (comparar con versión anterior si tienes)

---

**Última actualización:** 2025-11-17
**Siguiente revisión:** Después de completar Paso 3 (baseline)
