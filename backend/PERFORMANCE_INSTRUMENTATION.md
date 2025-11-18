# 📊 Instrumentación de Performance - Guía de Uso

Este documento explica cómo usar la instrumentación de performance implementada en el backend para medir y analizar el rendimiento de los endpoints.

---

## 🎯 ¿Qué está instrumentado?

Los siguientes 5 endpoints principales están instrumentados con medición automática de tiempos:

1. **`GET /metrics/cards`** - Métricas generales del dashboard
2. **`GET /metrics/disciplinas`** - Métricas por disciplina (50-59)
3. **`GET /metrics/subsistemas`** - Métricas por subsistema
4. **`GET /metrics/changes/summary`** - Resumen de cambios entre cargas
5. **`GET /aconex/duplicates`** - Documentos duplicados en ACONEX

---

## 📋 Endpoints de Administración

### 1. Ver Estadísticas de Performance

**Endpoint:** `GET /admin/performance/stats`

**Descripción:** Obtiene estadísticas detalladas de todos los endpoints instrumentados o uno específico.

**Parámetros:**
- `endpoint` (opcional): Nombre del endpoint específico (ej: `metrics_cards`)

**Ejemplos:**

```bash
# Ver estadísticas de todos los endpoints
GET /admin/performance/stats

# Ver estadísticas de un endpoint específico
GET /admin/performance/stats?endpoint=metrics_cards
```

**Respuesta:**
```json
{
  "success": true,
  "stats": {
    "metrics_cards": {
      "calls": 5,
      "total_time_ms": 2450.5,
      "avg_time_ms": 490.1,
      "min_time_ms": 450.2,
      "max_time_ms": 520.8,
      "last_execution_queries": [
        {
          "description": "Count APSA ABIERTOS",
          "time_ms": 45.3
        },
        {
          "description": "Count APSA CERRADOS",
          "time_ms": 42.1
        },
        ...
      ]
    }
  },
  "note": "Tiempos en milisegundos (ms)"
}
```

---

### 2. Resumen Simplificado

**Endpoint:** `GET /admin/performance/summary`

**Descripción:** Retorna un resumen simplificado de los 5 endpoints principales, ideal para dashboards.

**Ejemplo:**
```bash
GET /admin/performance/summary
```

**Respuesta:**
```json
{
  "success": true,
  "summary": [
    {
      "endpoint": "metrics_cards",
      "avg_time_ms": 490.1,
      "min_time_ms": 450.2,
      "max_time_ms": 520.8,
      "calls": 5,
      "last_execution": {
        "query_count": 5,
        "total_query_time_ms": 450.0,
        "overhead_ms": 40.1
      }
    },
    ...
  ],
  "note": "Tiempos en milisegundos (ms). 'overhead_ms' = tiempo no gastado en queries SQL"
}
```

**Interpretación:**
- `avg_time_ms`: Tiempo promedio total del endpoint
- `query_count`: Número de queries SQL ejecutadas
- `total_query_time_ms`: Tiempo total gastado en queries SQL
- `overhead_ms`: Tiempo gastado en procesamiento Python (no SQL)

---

### 3. Resetear Estadísticas

**Endpoint:** `POST /admin/performance/reset`

**Descripción:** Limpia todas las estadísticas acumuladas. Útil después de pruebas o para empezar fresh.

**Ejemplo:**
```bash
POST /admin/performance/reset
```

**Respuesta:**
```json
{
  "success": true,
  "message": "Performance statistics reset successfully"
}
```

---

## 🔍 Cómo Leer los Logs

Cuando llamas a un endpoint instrumentado, verás logs como estos:

```
============================================================
🚀 START: metrics_cards
============================================================
  📊 Query #1: Count APSA ABIERTOS
     ⏱️  Completed in 45.30ms
  📊 Query #2: Count APSA CERRADOS
     ⏱️  Completed in 42.10ms
  📊 Query #3: Count ACONEX total rows
     ⏱️  Completed in 38.50ms
  ...
============================================================
✅ END: metrics_cards - Total: 490.10ms (0.490s)
============================================================
```

**Elementos:**
- `🚀 START`: Inicio del endpoint
- `📊 Query #N`: Cada query SQL individual
- `⏱️ Completed in`: Tiempo que tardó esa query
- `✅ END`: Tiempo total del endpoint

---

## 📈 Proceso de Medición (Workflow Recomendado)

### Paso 1: Resetear estadísticas
```bash
POST /admin/performance/reset
```

### Paso 2: Ejecutar los endpoints que quieres medir
```bash
# Ejecuta cada endpoint varias veces para obtener un promedio confiable
GET /metrics/cards
GET /metrics/disciplinas
GET /metrics/subsistemas
GET /metrics/changes/summary
GET /aconex/duplicates
```

### Paso 3: Ver el resumen
```bash
GET /admin/performance/summary
```

### Paso 4: Analizar detalles de endpoints lentos
```bash
# Si metrics_disciplinas es lento:
GET /admin/performance/stats?endpoint=metrics_disciplinas
```

---

## 🎨 Interpretación de Resultados

### Ejemplo: `/metrics/disciplinas`

Si ves algo como:
```json
{
  "endpoint": "metrics_disciplinas",
  "avg_time_ms": 3500,
  "last_execution": {
    "query_count": 40,
    "total_query_time_ms": 3200,
    "overhead_ms": 300
  }
}
```

**Diagnóstico:**
- ✅ Total: 3.5 segundos (3500ms)
- ⚠️ 40 queries SQL (problema N+1)
- ✅ 3.2 segundos en queries, 0.3 en overhead (91% en SQL)

**Conclusión:** El problema está en el número de queries (40), no en la eficiencia individual de cada una.

---

### Ejemplo: `/metrics/cards`

Si ves:
```json
{
  "endpoint": "metrics_cards",
  "avg_time_ms": 800,
  "last_execution": {
    "query_count": 5,
    "total_query_time_ms": 750,
    "overhead_ms": 50
  }
}
```

**Diagnóstico:**
- ✅ Total: 0.8 segundos (800ms)
- ✅ 5 queries (razonable)
- ⚠️ 750ms en queries (cada query promedia 150ms)

**Conclusión:** Posible problema con subconsultas EXISTS o normalización en runtime.

---

## 🚨 Señales de Alerta

### 🔴 Problema N+1
- `query_count` muy alto (>20 queries)
- Ejemplo: `/metrics/disciplinas` con 40 queries

**Solución:** Reemplazar loops por GROUP BY

---

### 🟠 Queries lentas individuales
- Una sola query tarda >200ms
- `total_query_time_ms` alto pero `query_count` bajo

**Solución:** Agregar índices o optimizar subconsultas

---

### 🟡 Alto overhead
- `overhead_ms` representa >30% del tiempo total
- Mucho procesamiento en Python

**Solución:** Mover lógica a SQL o cachear resultados

---

## 🛠️ Cómo Agregar Instrumentación a Nuevos Endpoints

Si quieres instrumentar un nuevo endpoint:

### 1. Agregar decorador al endpoint
```python
from .timing import measure_endpoint, measure_query

@app.get("/mi-nuevo-endpoint")
@measure_endpoint("mi_nuevo_endpoint")
def mi_nuevo_endpoint(db: Session = Depends(get_db)):
    # ...
```

### 2. Envolver queries SQL
```python
with measure_query("Descripción de la query", "mi_nuevo_endpoint"):
    result = db.execute(query).scalar()
```

### 3. Verificar logs
```bash
# Revisar logs de la aplicación
tail -f logs/app.log
```

---

## 📊 Métricas de Baseline (ANTES de optimizar)

Después de implementar la instrumentación, documenta los tiempos actuales como baseline:

| Endpoint | Queries | Tiempo Actual | Objetivo |
|----------|---------|---------------|----------|
| `/metrics/cards` | 5-8 | ? ms | <300ms |
| `/metrics/disciplinas` | 40 | ? ms | <500ms |
| `/metrics/subsistemas` | 2 | ? ms | <200ms |
| `/metrics/changes/summary` | 2 | ? ms | <300ms |
| `/aconex/duplicates` | 1 | ? ms | <200ms |

**TODO:** Completa esta tabla después de ejecutar tus endpoints con datos reales.

---

## 🎯 Próximos Pasos

1. ✅ **Instrumentación completada** (este documento)
2. ⏭️ **Medir baseline** con datos de producción
3. ⏭️ **Implementar optimizaciones** por etapas
4. ⏭️ **Medir mejoras** después de cada etapa
5. ⏭️ **Documentar resultados** finales

---

## ⚙️ Configuración Avanzada

### Cambiar nivel de logging

En `backend/app/main.py`, línea 108:

```python
logging.basicConfig(
    level=logging.INFO,  # Cambiar a logging.DEBUG para más detalle
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

**Niveles disponibles:**
- `logging.DEBUG`: Máximo detalle
- `logging.INFO`: Información normal (recomendado)
- `logging.WARNING`: Solo warnings y errores
- `logging.ERROR`: Solo errores

---

## 📞 Soporte

Si tienes problemas con la instrumentación:

1. Verifica que el logging esté configurado correctamente
2. Revisa que los endpoints estén decorados con `@measure_endpoint`
3. Verifica que las queries usen `with measure_query(...)`
4. Revisa los logs de la aplicación para errores

---

**Última actualización:** 2025-11-17
