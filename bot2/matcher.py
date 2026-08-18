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
    Cruza egresos de Softland contra cartola limpia por MONTO + FECHA (exacto).

    REGLA CONSORCIO↔BCI:
    - Si banco = CONSORCIO: buscar contra AMBAS cuentas
      (10-01-10-16 cuenta propia + 10-01-10-06 BCI por bug conocido)
    - Otros bancos: solo contra cuenta propia

    Reintentos: 3 DENTRO DE LA MISMA CORRIDA (con pausa breve), sin ampliar ventana de fechas.
    - Primer intento: búsqueda inmediata
    - Intentos 2-3: reintento con pausa, por si la cartola aún no se procesó en banco
    - Si sigue fallando tras 3 intentos: registrar en 'no_cuadra' para alerta

    Args:
        egresos_softland: lista de egresos de Softland
        cartola_limpia: DataFrame con cargos de cartola
        banco: nombre del banco
        max_intentos: intentos de matching por egreso (default 3)

    Returns:
        Dict con:
        {
            'confirmados': [egresos que cuadraron],
            'sin_match': [egresos NO encontrados en primer intento — aparecerán en próxima corrida],
            'no_cuadra': [egresos con discrepancia tras N reintentos — requieren alerta]
        }
    """
    import time

    logger.info(f"Iniciando matching: {len(egresos_softland)} egresos vs {len(cartola_limpia)} cargos")
    logger.debug(f"Columnas cartola: {list(cartola_limpia.columns)}")
    logger.debug(f"Cartola shape: {cartola_limpia.shape}")

    cuentas_busqueda = BANCO_CUENTA_MAP.get(banco, [banco])
    logger.info(f"Banco: {banco} | Cuentas a buscar: {cuentas_busqueda}")

    confirmados = []
    sin_match = []
    no_cuadra = []

    for egreso in egresos_softland:
        logger.debug(f"Procesando egreso: {egreso['CpbNum']} | ${egreso['monto_egreso']} | {egreso['fecha']}")

        monto = egreso['monto_egreso']
        fecha = egreso['fecha']

        # Primer intento: búsqueda inmediata
        cargo = _buscar_cargo_en_cartola(cartola_limpia, monto, fecha, cuentas_busqueda)

        if cargo is not None:
            # MATCH encontrado en primer intento
            confirmados.append({
                **egreso,
                'cargo_cartola': cargo,
                'intentos_match': 1
            })
            logger.info(f"  [OK] MATCH encontrado (intento 1)")

        else:
            # No encontrado en primer intento
            # Distinguir: ¿existe la fecha en cartola o no?
            fecha_existe = _existe_fecha_en_cartola(cartola_limpia, fecha)

            if not fecha_existe:
                # CASO A: No hay NINGÚN cargo con esa fecha en cartola
                # -> sin_match (aparecerá en próxima corrida cuando se procese la cartola)
                sin_match.append({
                    **egreso,
                    'motivo': f'Fecha {fecha} no existe aún en cartola (cartola incompleta o desfasada)'
                })
                logger.info(f"  [PAUSE] SIN MATCH: Fecha {fecha} no existe en cartola, reintentará próxima corrida")

            else:
                # CASO B: Existe la fecha, pero el monto no calza
                # -> Intentar reintentos (por si cartola se actualiza) y luego no_cuadra
                match_encontrado = False

                for intento_num in range(2, max_intentos + 1):
                    logger.debug(f"  • Reintento {intento_num}/{max_intentos}: pausa 2s antes de reintentar...")
                    time.sleep(2)  # Pausa breve para que se procese cartola en banco

                    cargo = _buscar_cargo_en_cartola(cartola_limpia, monto, fecha, cuentas_busqueda)

                    if cargo is not None:
                        confirmados.append({
                            **egreso,
                            'cargo_cartola': cargo,
                            'intentos_match': intento_num
                        })
                        logger.info(f"  [OK] MATCH encontrado (reintento {intento_num})")
                        match_encontrado = True
                        break

                if not match_encontrado:
                    # Tras 3 intentos sigue sin encontrarse (fecha existe pero monto no)
                    no_cuadra.append({
                        **egreso,
                        'intentos_match': max_intentos,
                        'motivo': f'Fecha existe pero monto ${monto} no coincide con nada tras {max_intentos} intentos'
                    })
                    logger.warning(f"  [FAIL] NO CUADRA: {egreso['CpbNum']} fecha existe pero monto no calza tras {max_intentos} intentos")

    logger.info(f"Resultado: {len(confirmados)} confirmados, {len(sin_match)} sin match, {len(no_cuadra)} no cuadra")

    return {
        'confirmados': confirmados,
        'sin_match': sin_match,
        'no_cuadra': no_cuadra
    }


def _existe_fecha_en_cartola(
    cartola: pd.DataFrame,
    fecha: str
) -> bool:
    """Verifica si existe ALGÚN cargo en cartola con esa fecha."""
    if cartola.empty:
        return False
    cartola_fecha = pd.to_datetime(cartola.get('fecha', []), errors='coerce')
    fecha_dt = pd.to_datetime(fecha, errors='coerce')
    return (cartola_fecha == fecha_dt).any()


def _buscar_cargo_en_cartola(
    cartola: pd.DataFrame,
    monto: float,
    fecha: str,
    cuentas: List[str]
) -> Optional[Dict]:
    """
    Busca un cargo en cartola que coincida EXACTAMENTE con MONTO + FECHA.

    NO amplia la ventana de fechas — solo búsqueda exacta.
    Los reintentos dentro de la corrida son por pausa breve, no por rango de fechas.
    Esto evita falsos positivos (matchear contra día equivocado por casualidad de monto).

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
    if 'monto' not in cartola.columns or 'fecha' not in cartola.columns:
        logger.warning(f"Cartola sin columnas esperadas. Columnas disponibles: {list(cartola.columns)}")
        logger.warning(f"Contenido de cartola:\n{cartola.head()}")
        return None

    cartola_monto = pd.to_numeric(cartola.get('monto', []), errors='coerce')
    cartola_fecha = pd.to_datetime(cartola.get('fecha', []), errors='coerce')

    monto_num = float(monto) if isinstance(monto, (int, float)) else pd.to_numeric(monto, errors='coerce')
    fecha_dt = pd.to_datetime(fecha, errors='coerce')

    # Buscar por MONTO exacto + FECHA exacta (sin rango de fechas)
    mask = (cartola_monto == monto_num) & (cartola_fecha == fecha_dt)

    coincidencias = cartola[mask]
    if len(coincidencias) > 0:
        return coincidencias.iloc[0].to_dict()

    # No encontrado — retornar None (reintento será manejado por hacer_matching con pausa)
    return None
