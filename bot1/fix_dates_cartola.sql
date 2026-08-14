-- FIX: Corregir fechas invertidas en bot1_cartola_transacciones
-- PROBLEMA: pandas interpretó DD/MM/YYYY como MM/DD/YYYY
-- SOLUCIÓN: Intercambiar mes y día

-- NOTA: Esto asume que NO hay movimientos legítimos en marzo (mes 3)
-- Si sí hay, necesitamos un filtro más específico.

BEGIN TRANSACTION;

-- Tabla temporal para auditar cambios
CREATE TEMP TABLE cartola_fix_audit AS
SELECT
    id,
    num_transaccion,
    fecha_contable AS fecha_vieja,
    MAKE_DATE(
        EXTRACT(YEAR FROM fecha_contable)::int,
        EXTRACT(DAY FROM fecha_contable)::int,   -- El día es el mes real
        EXTRACT(MONTH FROM fecha_contable)::int  -- El mes es el día real
    ) AS fecha_nueva
FROM
    valle_frio_bot.bot1_cartola_transacciones
WHERE
    -- Filtro: fechas con mes en rango 1-12 pero que se ven sospechosas
    -- (mes pequeño, día grande: típico de inversión)
    EXTRACT(MONTH FROM fecha_contable) < 9  -- Meses 1-8
    AND EXTRACT(DAY FROM fecha_contable) > 12  -- Días > 12 (imposible si fuera mes)
    AND EXTRACT(YEAR FROM fecha_contable) = 2026;  -- Solo agosto 2026 en phase 1

-- Verificar cambios ANTES de aplicar
SELECT
    COUNT(*) as registros_a_corregir,
    MIN(fecha_vieja) as fecha_min_incorrecta,
    MAX(fecha_vieja) as fecha_max_incorrecta
FROM cartola_fix_audit;

-- Aplicar corrección (DESCOMENTAR cuando estés seguro)
-- UPDATE valle_frio_bot.bot1_cartola_transacciones
-- SET fecha_contable = (
--     SELECT fecha_nueva
--     FROM cartola_fix_audit
--     WHERE cartola_fix_audit.id = bot1_cartola_transacciones.id
-- )
-- WHERE id IN (SELECT id FROM cartola_fix_audit);

-- Si deseas rollback automático, descomentar siguiente línea antes de "BEGIN TRANSACTION"
-- ROLLBACK;

COMMIT;
