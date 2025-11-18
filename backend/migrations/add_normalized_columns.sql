-- ============================================================================
-- MIGRACIÓN: Agregar Columnas Normalizadas para Optimización
-- Fecha: 2025-11-17
-- Objetivo: Eliminar normalización en runtime agregando columnas pre-calculadas
-- Base de datos: MySQL 5.7+
-- Tiempo estimado: 2-10 minutos dependiendo del tamaño de la tabla
-- ============================================================================

-- PASO 1: Agregar columnas normalizadas
-- ============================================================================

-- En apsa_protocols: columnas para código y subsistema normalizados
ALTER TABLE apsa_protocols
    ADD COLUMN codigo_cmdic_norm VARCHAR(120)
    GENERATED ALWAYS AS (
        UPPER(TRIM(REPLACE(REPLACE(REPLACE(codigo_cmdic, ' ', ''), '-', ''), '_', '')))
    ) STORED,
    ADD COLUMN subsistema_norm VARCHAR(60)
    GENERATED ALWAYS AS (
        UPPER(TRIM(REPLACE(REPLACE(REPLACE(subsistema, ' ', ''), '-', ''), '_', '')))
    ) STORED;

-- En aconex_docs: columnas para document_no y subsystem_code normalizados
ALTER TABLE aconex_docs
    ADD COLUMN document_no_norm VARCHAR(120)
    GENERATED ALWAYS AS (
        UPPER(TRIM(REPLACE(REPLACE(REPLACE(document_no, ' ', ''), '-', ''), '_', '')))
    ) STORED,
    ADD COLUMN subsystem_code_norm VARCHAR(60)
    GENERATED ALWAYS AS (
        UPPER(TRIM(REPLACE(REPLACE(REPLACE(subsystem_code, ' ', ''), '-', ''), '_', '')))
    ) STORED;

-- PASO 2: Crear índices en las columnas normalizadas
-- ============================================================================

-- Índices en columnas normalizadas de APSA
CREATE INDEX idx_apsa_codigo_norm ON apsa_protocols(codigo_cmdic_norm);
CREATE INDEX idx_apsa_subsistema_norm ON apsa_protocols(subsistema_norm);
CREATE INDEX idx_apsa_load_codigo_norm ON apsa_protocols(load_id, codigo_cmdic_norm);
CREATE INDEX idx_apsa_load_subs_norm ON apsa_protocols(load_id, subsistema_norm);

-- Índices en columnas normalizadas de ACONEX
CREATE INDEX idx_aconex_doc_norm ON aconex_docs(document_no_norm);
CREATE INDEX idx_aconex_sub_norm ON aconex_docs(subsystem_code_norm);
CREATE INDEX idx_aconex_load_doc_norm ON aconex_docs(load_id, document_no_norm);
CREATE INDEX idx_aconex_load_sub_norm ON aconex_docs(load_id, subsystem_code_norm);

-- PASO 3: Verificar que se crearon correctamente
-- ============================================================================

-- Ver las columnas nuevas
SELECT COLUMN_NAME, COLUMN_TYPE, GENERATION_EXPRESSION
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('apsa_protocols', 'aconex_docs')
  AND COLUMN_NAME LIKE '%_norm';

-- Ver los índices nuevos
SELECT TABLE_NAME, INDEX_NAME, COLUMN_NAME
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('apsa_protocols', 'aconex_docs')
  AND INDEX_NAME LIKE 'idx_%norm%'
ORDER BY TABLE_NAME, INDEX_NAME;

-- Ver algunos valores de ejemplo
SELECT
    codigo_cmdic,
    codigo_cmdic_norm,
    subsistema,
    subsistema_norm
FROM apsa_protocols
LIMIT 5;

-- ============================================================================
-- NOTAS IMPORTANTES
-- ============================================================================

-- 1. COLUMNAS GENERADAS (GENERATED ALWAYS)
--    - Se calculan AUTOMÁTICAMENTE cuando insertas/actualizas
--    - No necesitas triggers ni código adicional
--    - STORED = Se guarda físicamente (más rápido para queries)
--    - Compatible con MySQL 5.7.6+

-- 2. PERFORMANCE ESPERADO
--    - Antes: Normalización en cada query (muy lento)
--    - Después: Lectura directa del índice (instantáneo)
--    - Mejora estimada: 95-99% en queries con normalización

-- 3. ESPACIO EN DISCO
--    - Cada columna normalizada ocupa ~mismo espacio que la original
--    - Los índices ocupan ~10-30% adicional
--    - Trade-off: Espacio por velocidad (vale la pena)

-- 4. COMPATIBILIDAD
--    - Funciona con datos existentes (se calculan automáticamente)
--    - Funciona con datos nuevos (se calculan al insertar)
--    - NO requiere cambios en el código de upload

-- 5. ROLLBACK (si algo sale mal)
--    DROP INDEX idx_apsa_codigo_norm ON apsa_protocols;
--    DROP INDEX idx_apsa_subsistema_norm ON apsa_protocols;
--    -- ... (borrar todos los índices)
--    ALTER TABLE apsa_protocols DROP COLUMN codigo_cmdic_norm;
--    ALTER TABLE apsa_protocols DROP COLUMN subsistema_norm;
--    ALTER TABLE aconex_docs DROP COLUMN document_no_norm;
--    ALTER TABLE aconex_docs DROP COLUMN subsystem_code_norm;

-- ============================================================================
