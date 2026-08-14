"""
Matching entre cartola bancaria y egresos de Softland.
CRÍTICO: Implementa la regla Consorcio↔BCI.
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import pandas as pd

from config import BANCO_CUENTA_MAP, MAX_INTENTOS_MATCH_MISMA_CORRIDA

logger = logging.getLogger(__name__)


def hacer_matching(
    egresos_softland: List[Dict],
    cartola_limpia: pd.DataFrame,
    banco: str,
    max_intentos: int = MAX_INTENTOS_MATCH_MISMA_CORRIDA
) -> Dict[str, list]:
    """
    Cruza egresos de Softland contra cartola limpia por MONTO + FECHA.

    REGLA CONSORCIO↔BCI:
    - Si banco = CONSORCIO: buscar contra AMBAS cuentas
      (10-01-10-16 cuenta propia + 10-01-10-06 BCI por bug conocido)
    - Otros bancos: solo contra cuenta propia

    Args:
        egresos_softland: lista de egresos de Softland
        cartola_limpia: DataFrame con cargos de cartola
        banco: nombre del banco
        max_intentos: intentos de matching por egreso

    Returns:
        Dict con:
        {
            'confirmados': [egresos que cuadraron],
            'sin_match': [egresos sin coincidencia en cartola],
            'no_cuadra': [egresos con discrepancia tras N intentos]
        }
    """
    logger.info(f"Iniciando matching: {len(egresos_softland)} egresos vs {len(cartola_limpia)} cargos")

    cuentas_busqueda = BANCO_CUENTA_MAP.get(banco, [banco])
    logger.info(f"Banco: {banco} | Cuentas a buscar: {cuentas_busqueda}")

    confirmados = []
    sin_match = []
    no_cuadra = []

    for egreso in egresos_softland:
        logger.debug(f"Procesando egreso: {egreso['CpbNum']} | ${egreso['monto_egreso']} | {egreso['CpbFec']}")

        cuenta_registro = egreso['cuenta_banco']
        monto = egreso['monto_egreso']
        fecha = egreso['CpbFec']

        # Intentar matching contra las cuentas configuradas
        match_encontrado = False
        intentos = 0

        while intentos < max_intentos and not match_encontrado:
            intentos += 1

            # Buscar en cartola: MONTO + FECHA exacto
            cargo = _buscar_cargo_en_cartola(cartola_limpia, monto, fecha, cuentas_busqueda)

            if cargo is not None:
                confirmados.append({
                    **egreso,
                    'cargo_cartola': cargo,
                    'intentos_match': intentos
                })
                logger.info(f"  ✓ MATCH encontrado (intento {intentos})")
                match_encontrado = True

            else:
                if intentos < max_intentos:
                    logger.debug(f"  • Intento {intentos}/{max_intentos}: sin match, reintentando...")
                else:
                    no_cuadra.append({
                        **egreso,
                        'intentos_match': intentos,
                        'motivo': 'No encontrado en cartola tras reintentos'
                    })
                    logger.warning(f"  ✗ NO CUADRA: tras {intentos} intentos")

        if not match_encontrado and intentos == 0:
            sin_match.append(egreso)
            logger.info(f"  ~ SIN MATCH: no hay cargo equivalente en cartola")

    logger.info(f"Resultado: {len(confirmados)} confirmados, {len(sin_match)} sin match, {len(no_cuadra)} no cuadra")

    return {
        'confirmados': confirmados,
        'sin_match': sin_match,
        'no_cuadra': no_cuadra
    }


def _buscar_cargo_en_cartola(
    cartola: pd.DataFrame,
    monto: float,
    fecha: str,
    cuentas: List[str]
) -> Optional[Dict]:
    """
    Busca un cargo en cartola que coincida con MONTO + FECHA.

    Args:
        cartola: DataFrame de cartola limpia
        monto: monto a buscar
        fecha: fecha a buscar (formato YYYY-MM-DD)
        cuentas: lista de cuentas contra las que buscar (para Consorcio: [principal, BCI])

    Returns:
        Dict del cargo si lo encuentra, None si no
    """
    if cartola.empty:
        return None

    # Normalizar tipos de datos
    cartola_monto = pd.to_numeric(cartola.get('monto', []), errors='coerce')
    cartola_fecha = pd.to_datetime(cartola.get('fecha', []), errors='coerce')

    monto_num = float(monto) if isinstance(monto, (int, float)) else pd.to_numeric(monto, errors='coerce')
    fecha_dt = pd.to_datetime(fecha, errors='coerce')

    # Buscar por MONTO exacto + FECHA
    mask = (cartola_monto == monto_num) & (cartola_fecha == fecha_dt)

    coincidencias = cartola[mask]
    if len(coincidencias) > 0:
        return coincidencias.iloc[0].to_dict()

    # Si no encuentra, intentar rango de ±1 día (por diferencias de procesamiento)
    fecha_dia_anterior = fecha_dt - pd.Timedelta(days=1)
    fecha_dia_siguiente = fecha_dt + pd.Timedelta(days=1)

    mask_rango = (cartola_monto == monto_num) & (
        (cartola_fecha == fecha_dia_anterior) |
        (cartola_fecha == fecha_dia_siguiente)
    )

    coincidencias_rango = cartola[mask_rango]
    if len(coincidencias_rango) > 0:
        logger.debug(f"  • Match por rango ±1 día encontrado")
        return coincidencias_rango.iloc[0].to_dict()

    return None
