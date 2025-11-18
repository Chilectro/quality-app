-- ============================================================================
-- MIGRACION: Índices para Optimización de Performance (MySQL)
-- Fecha: 2025-11-17
-- Objetivo: Mejorar performance de endpoints /metrics/* y /aconex/*
-- Base de datos: MySQL 5.7+
-- ============================================================================

-- IMPORTANTE: Ejecutar estas queries una a la vez y verificar que completen
-- MySQL soporta CREATE INDEX IF NOT EXISTS desde la versión 5.7

-- ============================================================================
-- 1. ÍNDICES BÁSICOS EN COLUMNAS DE JOIN
-- ============================================================================

-- Índice en codigo_cmdic (usado en JOINs con ACONEX)
-- Antes: Sin índice, joins lentos
-- Después: Joins instantáneos
CREATE INDEX idx_apsa_codigo_cmdic
    ON apsa_protocols(codigo_cmdic);

-- Índice en document_no (usado en JOINs con APSA)
CREATE INDEX idx_aconex_document_no
    ON aconex_docs(document_no);

-- ============================================================================
-- 2. ÍNDICES COMPUESTOS PARA QUERIES FRECUENTES
-- ============================================================================

-- Para queries que filtran por load_id + disciplina
CREATE INDEX idx_apsa_load_disc
    ON apsa_protocols(load_id, disciplina);

-- Para queries que filtran por load_id + subsistema
CREATE INDEX idx_apsa_load_subs
    ON apsa_protocols(load_id, subsistema);

-- Para queries ACONEX que filtran por load_id + document_no
CREATE INDEX idx_aconex_load_doc
    ON aconex_docs(load_id, document_no);

-- Para queries ACONEX que filtran por load_id + subsystem_code
CREATE INDEX idx_aconex_load_sub
    ON aconex_docs(load_id, subsystem_code);

-- ============================================================================
-- 3. ÍNDICES COMPUESTOS CON STATUS (para métricas)
-- ============================================================================

-- Para queries que agrupan por disciplina + status
CREATE INDEX idx_apsa_load_disc_status
    ON apsa_protocols(load_id, disciplina, status_bim360);

-- Para queries que agrupan por subsistema + status
CREATE INDEX idx_apsa_load_subs_status
    ON apsa_protocols(load_id, subsistema, status_bim360);

-- ============================================================================
-- VERIFICACIÓN DE ÍNDICES CREADOS (MySQL)
-- ============================================================================

-- Ejecutar esto para verificar que los índices se crearon correctamente:
/*
-- Ver todos los índices de apsa_protocols
SHOW INDEX FROM apsa_protocols WHERE Key_name LIKE 'idx_%';

-- Ver todos los índices de aconex_docs
SHOW INDEX FROM aconex_docs WHERE Key_name LIKE 'idx_%';

-- O ver detalles completos:
SELECT
    TABLE_NAME,
    INDEX_NAME,
    COLUMN_NAME,
    SEQ_IN_INDEX,
    NON_UNIQUE
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('apsa_protocols', 'aconex_docs')
  AND INDEX_NAME LIKE 'idx_%'
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
*/

-- ============================================================================
-- NOTAS:
-- - Estos índices mejorarán significativamente el performance
-- - Especialmente en queries con JOINs y subconsultas EXISTS
-- - El overhead de mantenimiento es mínimo (inserts/updates ligeramente más lentos)
-- - Beneficio estimado: 50-90% reducción en tiempos de query
-- ============================================================================
