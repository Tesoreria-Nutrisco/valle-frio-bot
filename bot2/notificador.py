"""
Envío de correos de notificación y alertas al desarrollador.
"""

import logging
import base64
from pathlib import Path
from typing import Optional, List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from config import (
    GOOGLE_DRIVE_CREDENTIALS_PATH,
    GMAIL_SENDER,
    GMAIL_REPLY_TO,
    TEMPLATES_PATH,
    MODO_TEST,
    CORREO_PRUEBA,
)

logger = logging.getLogger(__name__)


def obtener_servicio_gmail():
    """Inicializa cliente de Gmail API."""
    scopes = ["https://www.googleapis.com/auth/gmail.send"]
    credentials = Credentials.from_service_account_file(
        GOOGLE_DRIVE_CREDENTIALS_PATH, scopes=scopes
    )
    return build("gmail", "v1", credentials=credentials)


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
        filas_facturas = ""
        for factura in facturas:
            filas_facturas += f"""
            <tr>
              <td style="padding:10px; color:#1B1868; border-bottom:1px solid #f1f5f9;">{factura.get('numero', 'N/A')}</td>
              <td style="padding:10px; color:#2c2c2a; border-bottom:1px solid #f1f5f9;">{factura.get('fecha', fecha_pago)}</td>
              <td style="padding:10px; color:#2c2c2a; border-bottom:1px solid #f1f5f9; text-align:right;">${factura.get('monto', monto_total):,.0f}</td>
            </tr>
            """

        # Reemplazar placeholders
        html_content = html_template
        html_content = html_content.replace("{{NOMBRE_PRODUCTOR}}", productor_nombre)
        html_content = html_content.replace("{{MONTO_TOTAL}}", f"{monto_total:,.0f}")
        html_content = html_content.replace("{{NUM_FACTURAS}}", str(len(facturas)))
        html_content = html_content.replace("{{COMPROBANTE}}", Path(comprobante_path).name)
        html_content = html_content.replace("{{FILAS_FACTURAS}}", filas_facturas)
        html_content = html_content.replace("{{FECHA_PAGO}}", str(fecha_pago))
        html_content = html_content.replace("{{NOMBRE_COMPROBANTE}}", Path(comprobante_path).name)

        # Preparar destinatarios
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
            asunto_prefix = ""
            logger.info(f"Modo producción: enviando a {to_emails}" + (f" CC: {cc_emails}" if cc_emails else ""))

        # Crear mensaje
        message = MIMEMultipart('alternative')
        message['Subject'] = f"{asunto_prefix}Notificación de pago confirmado - Valle Frío (${monto_total:,.0f})"
        message['From'] = GMAIL_SENDER
        message['To'] = ", ".join(to_emails)
        if not MODO_TEST and 'cc_emails' in locals():
            message['Cc'] = ", ".join(cc_emails)
        message['Reply-To'] = GMAIL_REPLY_TO

        # Adjuntar HTML
        message.attach(MIMEText(html_content, 'html'))

        # Adjuntar comprobante PDF (si existe en local)
        if Path(comprobante_path).exists():
            with open(comprobante_path, 'rb') as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename= {Path(comprobante_path).name}')
                message.attach(part)

        # Enviar por Gmail
        gmail = obtener_servicio_gmail()
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        send_message = {'raw': raw_message}
        gmail.users().messages().send(userId='me', body=send_message).execute()

        logger.info(f"✓ Correo enviado a {', '.join(to_emails)}" + (f" CC: {', '.join(cc_emails)}" if cc_emails else ""))
        return True

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
        html_content = html_content.replace("{{COMPROBANTE}}", f"{egreso['CpbAno']} / {egreso['CpbNum']}")
        html_content = html_content.replace("{{FECHA_CONTABLE}}", str(egreso['CpbFec']))
        html_content = html_content.replace("{{MONTO}}", f"${egreso['monto_egreso']:,.0f}")
        html_content = html_content.replace("{{CUENTA_SOFTLAND}}", str(egreso['cuenta_banco']))
        html_content = html_content.replace("{{PRODUCTOR_COD}}", str(egreso['productor_cod']))
        html_content = html_content.replace("{{PRODUCTOR_NOMBRE}}", "N/A")  # Agregar si disponible
        html_content = html_content.replace("{{GLOSA}}", str(egreso.get('MovGlosa', 'N/A')))
        html_content = html_content.replace("{{FECHA_CORRIDA}}", str(Path.cwd().name))  # Placeholder

        # Enviar
        gmail = obtener_servicio_gmail()
        message = MIMEText(html_content, 'html')
        message['Subject'] = f"⚠️ Alerta: pago sin cuadrar - Comprobante {egreso['CpbNum']}"
        message['From'] = GMAIL_SENDER
        message['To'] = "projects.treasury.finance@nutrisco.com"

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        gmail.users().messages().send(userId='me', body={'raw': raw_message}).execute()

        logger.info("✓ Alerta enviada a desarrollador")
        return True

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
        html_content = html_content.replace("{{COMPROBANTE}}", f"{egreso['CpbAno']} / {egreso['CpbNum']}")
        html_content = html_content.replace("{{FECHA_PAGO}}", str(egreso['CpbFec']))
        html_content = html_content.replace("{{MONTO}}", f"${egreso['monto_egreso']:,.0f}")
        html_content = html_content.replace("{{PRODUCTOR_NOMBRE}}", "N/A")
        html_content = html_content.replace("{{PRODUCTOR_COD}}", str(egreso['productor_cod']))
        html_content = html_content.replace("{{PRODUCTOR_EMAIL}}", "no registrado")
        html_content = html_content.replace("{{PRODUCTOR_EMAIL_DTE}}", "no registrado")
        html_content = html_content.replace("{{PRODUCTOR_EMAIL_CONTACTO}}", "no registrado")
        html_content = html_content.replace("{{ZONAL_EMAIL}}", "no disponible")
        html_content = html_content.replace("{{FECHA_CORRIDA}}", str(Path.cwd().name))

        # Enviar
        gmail = obtener_servicio_gmail()
        message = MIMEText(html_content, 'html')
        message['Subject'] = f"⚠️ Alerta: pago confirmado sin contacto - {egreso['CpbNum']}"
        message['From'] = GMAIL_SENDER
        message['To'] = "projects.treasury.finance@nutrisco.com"

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        gmail.users().messages().send(userId='me', body={'raw': raw_message}).execute()

        logger.info("✓ Alerta 'falta contacto' enviada")
        return True

    except Exception as e:
        logger.error(f"Error enviando alerta 'falta contacto': {e}")
        return False
