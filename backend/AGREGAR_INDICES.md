# 🚀 Cómo Agregar los Índices de Performance

**Base de datos:** MySQL
**Tiempo estimado:** 5-10 minutos
**Impacto:** 40-80% de mejora en velocidad

---

## ✅ Pre-requisitos

1. Backend funcionando correctamente
2. Acceso a la base de datos MySQL
3. Python instalado con pymysql

---

## 📋 Opción 1: Script Python Automatizado (RECOMENDADO)

### Paso 1: Verificar que tienes el archivo `.env` configurado

```bash
cd backend
cat .env
```

Deberías ver algo como:
```
DB_USER=tu_usuario
DB_PASSWORD=tu_password
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=quality_db
```

### Paso 2: Ejecutar el script

```bash
cd backend
python scripts/add_indexes.py
```

### Paso 3: Verificar la salida

Deberías ver algo como:

```
================================================================================
🚀 AGREGANDO ÍNDICES DE PERFORMANCE
================================================================================

📊 Índice en codigo_cmdic para JOINs con ACONEX
⏳ Creando índice idx_apsa_codigo_cmdic en apsa_protocols...
✅ Índice idx_apsa_codigo_cmdic creado exitosamente

📊 Índice en document_no para JOINs con APSA
⏳ Creando índice idx_aconex_document_no en aconex_docs...
✅ Índice idx_aconex_document_no creado exitosamente

... (8 índices en total)

================================================================================
📊 RESUMEN
================================================================================
✅ Creados: 8
⏭️  Omitidos (ya existían): 0
❌ Errores: 0
📝 Total procesado: 8
================================================================================

✅ Índices de performance agregados exitosamente!

💡 Próximo paso: Ejecuta los endpoints y compara los tiempos
   GET /admin/performance/summary
```

---

## 📋 Opción 2: SQL Manual

Si prefieres ejecutar el SQL manualmente o el script Python no funciona:

### Paso 1: Conectar a MySQL

```bash
# Desde línea de comandos
mysql -u tu_usuario -p quality_db

# O usar un cliente gráfico como MySQL Workbench, phpMyAdmin, etc.
```

### Paso 2: Ejecutar los índices uno por uno

```sql
-- ÍNDICES BÁSICOS (MÁS IMPORTANTES)
CREATE INDEX idx_apsa_codigo_cmdic ON apsa_protocols(codigo_cmdic);
CREATE INDEX idx_aconex_document_no ON aconex_docs(document_no);

-- ÍNDICES COMPUESTOS
CREATE INDEX idx_apsa_load_disc ON apsa_protocols(load_id, disciplina);
CREATE INDEX idx_apsa_load_subs ON apsa_protocols(load_id, subsistema);
CREATE INDEX idx_aconex_load_doc ON aconex_docs(load_id, document_no);
CREATE INDEX idx_aconex_load_sub ON aconex_docs(load_id, subsystem_code);

-- ÍNDICES CON STATUS
CREATE INDEX idx_apsa_load_disc_status ON apsa_protocols(load_id, disciplina, status_bim360);
CREATE INDEX idx_apsa_load_subs_status ON apsa_protocols(load_id, subsistema, status_bim360);
```

### Paso 3: Verificar

```sql
-- Ver índices de apsa_protocols
SHOW INDEX FROM apsa_protocols WHERE Key_name LIKE 'idx_%';

-- Ver índices de aconex_docs
SHOW INDEX FROM aconex_docs WHERE Key_name LIKE 'idx_%';
```

Deberías ver 5 índices en `apsa_protocols` y 3 en `aconex_docs`.

---

## ⚠️ Troubleshooting

### Error: "Duplicate key name"

✅ **Esto es normal!** Significa que el índice ya existe. Puedes ignorarlo.

### Error: "Access denied"

❌ Tu usuario no tiene permisos para crear índices.

**Solución:**
```sql
-- Ejecutar como administrador de MySQL:
GRANT INDEX ON quality_db.* TO 'tu_usuario'@'localhost';
FLUSH PRIVILEGES;
```

### Error: "Table doesn't exist"

❌ Las tablas no existen o tienen nombres diferentes.

**Verificación:**
```sql
SHOW TABLES LIKE '%protocol%';
SHOW TABLES LIKE '%aconex%';
```

### Error de conexión Python

❌ No puede conectar a MySQL.

**Verificación:**
```bash
# Verificar que pymysql está instalado
pip list | grep pymysql

# Instalar si falta
pip install pymysql
```

### El script se cuelga / tarda mucho

⏳ **Es normal si tienes muchos datos.** Crear índices puede tardar:
- Base pequeña (<10k registros): 1-5 segundos por índice
- Base mediana (10-100k): 5-30 segundos por índice
- Base grande (>100k): 30-120 segundos por índice

**No interrumpas el proceso!** Déjalo terminar.

---

## 🔍 Verificar que Funcionaron los Índices

### Método 1: Query directa

```sql
SELECT
    TABLE_NAME,
    INDEX_NAME,
    GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) as COLUMNS
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('apsa_protocols', 'aconex_docs')
  AND INDEX_NAME LIKE 'idx_%'
GROUP BY TABLE_NAME, INDEX_NAME
ORDER BY TABLE_NAME, INDEX_NAME;
```

### Método 2: Script Python de verificación

```python
# En backend/scripts/verify_indexes.py (crear si no existe)
from app.db import engine
from sqlalchemy import text

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT TABLE_NAME, INDEX_NAME, COLUMN_NAME
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME IN ('apsa_protocols', 'aconex_docs')
          AND INDEX_NAME LIKE 'idx_%'
        ORDER BY TABLE_NAME, INDEX_NAME
    """))

    for row in result:
        print(f"{row[0]}.{row[1]}: {row[2]}")
```

---

## 📊 Resultados Esperados

Después de agregar los índices:

| Endpoint | Antes | Después | Mejora |
|----------|-------|---------|--------|
| `/metrics/cards` | 5-10s | 2-4s | 50-60% |
| `/metrics/disciplinas` | 10-30s | 8-20s | 20-40% |
| `/metrics/subsistemas` | 3-8s | 1-3s | 50-70% |

**Nota:** Los índices solos NO solucionarán el problema N+1 de `/metrics/disciplinas`. Para eso necesitamos reescribir la query (siguiente paso).

---

## ✅ Siguiente Paso

Una vez que los índices estén creados:

1. **Reiniciar el servidor backend** (para limpiar cache si existe)
   ```bash
   # Ctrl+C para detener
   uvicorn app.main:app --reload
   ```

2. **Probar los endpoints**
   ```bash
   curl http://localhost:8000/metrics/cards
   curl http://localhost:8000/metrics/disciplinas
   curl http://localhost:8000/metrics/subsistemas
   ```

3. **Ver estadísticas de performance**
   ```bash
   curl http://localhost:8000/admin/performance/summary
   ```

4. **Comparar con baseline** (si lo documentaste antes)

---

## 🎯 Prioridad de Índices

Si solo puedes crear algunos por limitaciones de recursos:

### CRÍTICOS (crear SÍ o SÍ):
1. `idx_apsa_codigo_cmdic` - Para JOINs con ACONEX
2. `idx_aconex_document_no` - Para JOINs con APSA

### IMPORTANTES:
3. `idx_apsa_load_subs` - Para métricas por subsistema
4. `idx_apsa_load_disc` - Para métricas por disciplina

### RECOMENDADOS:
5-8. Los demás índices compuestos

---

## 📝 Notas sobre Espacio en Disco

Los índices ocupan espacio adicional:

- **Estimación:** ~10-30% del tamaño de la tabla
- Si tu tabla `apsa_protocols` ocupa 100MB, los índices ocuparán ~10-30MB adicionales
- **Es un trade-off:** Más espacio → Mejor performance

Para verificar tamaño actual:
```sql
SELECT
    TABLE_NAME,
    ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 2) AS Size_MB,
    ROUND(INDEX_LENGTH / 1024 / 1024, 2) AS Index_Size_MB
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('apsa_protocols', 'aconex_docs');
```

---

## ⚡ Bonus: Optimizar tablas después de crear índices

Después de crear los índices, es recomendable optimizar las tablas:

```sql
OPTIMIZE TABLE apsa_protocols;
OPTIMIZE TABLE aconex_docs;
```

Esto puede tardar varios minutos pero mejora el performance.

---

**¿Problemas?** Revisa los logs del script o consulta `OPTIMIZATION_STATUS.md`
