"""
Envío de correos de notificación y alertas al desarrollador.
Usa Supabase Edge Function (send-email-bot2) para envío seguro.
"""

import logging
import requests
import os
import base64
import sys
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

# Importar config desde el directorio actual (bot2/)
sys.path.insert(0, str(Path(__file__).parent))
from config import (
    GMAIL_SENDER,
    GMAIL_REPLY_TO,
    TEMPLATES_PATH,
    MODO_TEST,
    CORREO_PRUEBA,
)

logger = logging.getLogger(__name__)

# Cache de logos en base64
_LOGOS_CACHE = {}

def obtener_logo_base64(nombre_logo: str) -> str:
    """Obtiene logo en base64, cacheado en memoria."""
    if nombre_logo not in _LOGOS_CACHE:
        # Buscar en templates/
        logo_path = TEMPLATES_PATH / f"logo_{nombre_logo}.png"
        if not logo_path.exists():
            # Fallback: buscar sin prefijo
            logo_path = TEMPLATES_PATH / f"{nombre_logo}.png"

        try:
            with open(logo_path, "rb") as f:
                _LOGOS_CACHE[nombre_logo] = base64.b64encode(f.read()).decode("utf-8")
                logger.debug(f"Logo cacheado: {nombre_logo} ({len(_LOGOS_CACHE[nombre_logo])} chars)")
        except FileNotFoundError:
            logger.warning(f"Logo no encontrado: {logo_path}")
            _LOGOS_CACHE[nombre_logo] = ""
    return _LOGOS_CACHE[nombre_logo]

# URL de la Edge Function de Supabase para Bot 2
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SEND_EMAIL_BOT2_FUNCTION_URL = f"{SUPABASE_URL}/functions/v1/send-email-bot2"


def enviar_email_via_edge_function(to: str, subject: str, html: str, attachment_base64: str = None, attachment_filename: str = None) -> bool:
    """
    Envía email usando Supabase Edge Function (send-email-bot2).
    Usa credenciales de Google OAuth 2.0 configuradas en Supabase secrets.

    Args:
        to: Email destino
        subject: Asunto del correo
        html: Contenido HTML del correo
        attachment_base64: Archivo en base64 (opcional)
        attachment_filename: Nombre del archivo adjunto (opcional)

    Returns:
        True si se envió, False si falló
    """
    if not SUPABASE_SERVICE_ROLE_KEY or not SEND_EMAIL_BOT2_FUNCTION_URL:
        logger.warning(f"⚠️ Credenciales de Supabase no configuradas. No se puede enviar email a {to}")
        logger.info(f"📧 Para: {to} | Asunto: {subject}")
        return False

    try:
        payload = {
            "to": to,
            "subject": subject,
            "html": html
        }

        # Agregar attachment si está disponible
        if attachment_base64 and attachment_filename:
            payload["attachment"] = {
                "filename": attachment_filename,
                "content": attachment_base64,
                "encoding": "base64"
            }

        response = requests.post(
            SEND_EMAIL_BOT2_FUNCTION_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
            },
            timeout=30
        )

        if response.status_code in [200, 201, 202]:
            logger.info(f"✓ Email enviado a {to} vía Edge Function send-email-bot2")
            return True
        else:
            logger.warning(f"⚠️ Edge Function retornó {response.status_code}: {response.text}")
            return False

    except Exception as e:
        logger.warning(f"⚠️ Error llamando Edge Function: {e}")
        logger.info(f"📧 Para: {to}")
        return False


def enviar_notificacion_pago(
    productor_email: Optional[str],
    zonal_email: Optional[str],
    monto_total: float,
    facturas: List[Dict],
    comprobante_path: str,
    productor_nombre: str
) -> bool:
    """
    Envía correo de notificación de pago confirmado al productor (y zonal en CC si existe).

    Args:
        productor_email: email del productor
        zonal_email: email del agrónomo zonal (puede ser None)
        monto_total: monto total pagado
        facturas: lista de dicts con números de factura
        comprobante_path: ruta al PDF del comprobante en local o Drive
        productor_nombre: nombre del productor

    Returns:
        True si se envió, False si no
    """
    if not productor_email and not zonal_email:
        logger.warning("No hay correo disponible (productor ni zonal)")
        return False

    logger.info(f"Preparando correo de notificación a {productor_email} (CC: {zonal_email})")

    try:
        # Cargar plantilla
        template_path = TEMPLATES_PATH / "correo_valle_frio.html"
        with open(template_path, 'r', encoding='utf-8') as f:
            html_template = f.read()

        # Preparar datos dinámicos
        fecha_pago = facturas[0]['fecha_pago'] if facturas else "N/A"

        # Generar filas de facturas con estructura HTML correcta
        filas_facturas = ""
        for factura in facturas:
            numero = factura.get('numero', 'N/A')
            fecha = factura.get('fecha', str(fecha_pago))
            monto = factura.get('monto', monto_total)
            filas_facturas += f'        <tr>\n'
            filas_facturas += f'          <td style="padding:10px; color:#1B1868; border-bottom:1px solid #f1f5f9;">{numero}</td>\n'
            filas_facturas += f'          <td style="padding:10px; color:#2c2c2a; border-bottom:1px solid #f1f5f9;">{fecha}</td>\n'
            filas_facturas += f'          <td style="padding:10px; color:#2c2c2a; border-bottom:1px solid #f1f5f9; text-align:right;">${monto:,.0f}</td>\n'
            filas_facturas += f'        </tr>\n'

        # Reemplazar placeholders
        html_content = html_template
        html_content = html_content.replace("{{PRODUCTOR_NOMBRE}}", productor_nombre)  # CRÍTICO: es PRODUCTOR_NOMBRE, no NOMBRE_PRODUCTOR
        html_content = html_content.replace("{{MONTO_TOTAL}}", f"${monto_total:,.0f}")
        html_content = html_content.replace("{{NUM_FACTURAS}}", str(len(facturas)))
        html_content = html_content.replace("{{FILAS_FACTURAS}}", filas_facturas)
        html_content = html_content.replace("{{FECHA_PAGO}}", str(fecha_pago))
        html_content = html_content.replace("{{NOMBRE_ARCHIVO}}", Path(comprobante_path).name)
        html_content = html_content.replace("{{CPB_NUM}}", "N/A")

        # Insertar logos en base64
        logo_vallefrio = obtener_logo_base64("vallefrio")
        logo_nutrisco = obtener_logo_base64("nutrisco")
        html_content = html_content.replace("{{LOGO_VALLEFRIO_BASE64}}", logo_vallefrio)
        html_content = html_content.replace("{{LOGO_NUTRISCO_BASE64}}", logo_nutrisco)

        # Preparar destinatarios
        to_emails = []
        cc_emails = []
        asunto_prefix = ""

        if MODO_TEST:
            # Modo prueba: enviar a correo de prueba
            to_emails = [CORREO_PRUEBA]
            destinatarios_reales = [e for e in [productor_email, zonal_email] if e]
            asunto_prefix = "[PRUEBA] "
            nota_prueba = f"<p style='color:#ba7517; font-weight:bold;'>⚠️ Este es un correo de PRUEBA.</p><p>Destinatario real sería: {', '.join(destinatarios_reales)}</p>"
            html_content = html_content.replace("</body>", f"{nota_prueba}</body>")
            logger.info(f"MODO_TEST activado: enviando a {CORREO_PRUEBA} (destinatarios reales: {destinatarios_reales})")
        else:
            # Modo producción: enviar a destinatarios reales
            to_emails = [e for e in [productor_email] if e]
            cc_emails = [e for e in [zonal_email] if e]
            logger.info(f"Modo producción: enviando a {to_emails}" + (f" CC: {cc_emails}" if cc_emails else ""))

        # Preparar attachment del comprobante
        attachment_base64 = None
        attachment_filename = None

        if comprobante_path and Path(comprobante_path).exists():
            try:
                with open(comprobante_path, "rb") as f:
                    import base64 as b64_module
                    attachment_base64 = b64_module.b64encode(f.read()).decode("utf-8")
                    attachment_filename = Path(comprobante_path).name
                    logger.info(f"Comprobante adjuntado: {attachment_filename}")
            except Exception as e:
                logger.warning(f"No se pudo adjuntar comprobante {comprobante_path}: {e}")

        # Enviar vía Edge Function
        email_enviado = enviar_email_via_edge_function(
            to=to_emails[0],
            subject=f"{asunto_prefix}Notificación de pago confirmado - Valle Frío (${monto_total:,.0f})",
            html=html_content,
            attachment_base64=attachment_base64,
            attachment_filename=attachment_filename
        )

        if email_enviado:
            logger.info(f"[OK] Correo enviado a {', '.join(to_emails)}" + (f" CC: {', '.join(cc_emails)}" if cc_emails else ""))
            return True
        else:
            logger.warning(f"⚠️ No se pudo enviar correo vía Edge Function")
            logger.info(f"📧 Destinatarios: {', '.join(to_emails)}" + (f" CC: {', '.join(cc_emails)}" if cc_emails else ""))
            logger.info("   → Estado permanecerá 'confirmado', se reintentará en próxima corrida")
            return False

    except Exception as e:
        logger.error(f"Error enviando correo: {e}")
        return False


def enviar_alerta_desarrollador_no_cuadra(egreso: Dict, intento_numero: int = 3) -> bool:
    """
    Envía alerta al desarrollador cuando un pago no cuadra tras N intentos.

    Args:
        egreso: dict con datos del comprobante
        intento_numero: número de intentos realizados

    Returns:
        True si se envió
    """
    logger.info(f"Enviando alerta 'no cuadra' para comprobante {egreso['CpbNum']}")

    try:
        template_path = TEMPLATES_PATH / "alerta_desarrollador_no_cuadra.html"
        with open(template_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # Reemplazar placeholders
        fecha_corrida = datetime.now().strftime("%Y-%m-%d %H:%M")
        html_content = html_content.replace("{{COMPROBANTE}}", f"{egreso['CpbAno']} / {egreso['CpbNum']}")
        html_content = html_content.replace("{{FECHA_CONTABLE}}", str(egreso.get('fecha_carga', egreso.get('CpbFec', 'N/A'))))
        html_content = html_content.replace("{{MONTO}}", f"${egreso['monto_egreso']:,.0f}")
        html_content = html_content.replace("{{CUENTA_SOFTLAND}}", str(egreso['cuenta_banco']))
        html_content = html_content.replace("{{PRODUCTOR_COD}}", str(egreso['productor_cod']))
        html_content = html_content.replace("{{PRODUCTOR_NOMBRE}}", "N/A")
        html_content = html_content.replace("{{GLOSA}}", str(egreso.get('MovGlosa', 'N/A')))
        html_content = html_content.replace("{{FECHA_CORRIDA}}", fecha_corrida)

        # Enviar vía Edge Function
        email_enviado = enviar_email_via_edge_function(
            to="javiera.munozc@nutrisco.com",
            subject=f"⚠️ Alerta: pago sin cuadrar - Comprobante {egreso['CpbNum']}",
            html=html_content
        )

        if email_enviado:
            logger.info("[OK] Alerta enviada a desarrollador")
            return True
        else:
            logger.warning("[FAIL] No se pudo enviar alerta")
            return False

    except Exception as e:
        logger.error(f"Error enviando alerta 'no cuadra': {e}")
        return False


def enviar_alerta_desarrollador_falta_contacto(egreso: Dict) -> bool:
    """
    Envía alerta cuando el pago está confirmado pero falta email de productor/zonal.
    """
    logger.info(f"Enviando alerta 'falta contacto' para comprobante {egreso['CpbNum']}")

    try:
        template_path = TEMPLATES_PATH / "alerta_desarrollador_falta_contacto.html"
        with open(template_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # Reemplazar placeholders
        fecha_corrida = datetime.now().strftime("%Y-%m-%d %H:%M")
        html_content = html_content.replace("{{COMPROBANTE}}", f"{egreso['CpbAno']} / {egreso['CpbNum']}")
        html_content = html_content.replace("{{FECHA_PAGO}}", str(egreso['CpbFec']))
        html_content = html_content.replace("{{MONTO}}", f"${egreso['monto_egreso']:,.0f}")
        html_content = html_content.replace("{{PRODUCTOR_NOMBRE}}", "N/A")
        html_content = html_content.replace("{{PRODUCTOR_RUT}}", str(egreso.get('productor_cod', 'N/A')))
        html_content = html_content.replace("{{FECHA_CORRIDA}}", fecha_corrida)

        # Enviar vía Edge Function
        email_enviado = enviar_email_via_edge_function(
            to="javiera.munozc@nutrisco.com",
            subject=f"⚠️ Alerta: pago confirmado sin contacto - {egreso['CpbNum']}",
            html=html_content
        )

        if email_enviado:
            logger.info("[OK] Alerta 'falta contacto' enviada")
            return True
        else:
            logger.warning("[FAIL] No se pudo enviar alerta 'falta contacto'")
            return False

    except Exception as e:
        logger.error(f"Error enviando alerta 'falta contacto': {e}")
        return False
