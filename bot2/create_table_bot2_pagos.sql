-- Ejecutar en Supabase SQL Editor o psql
-- Schema: valle_frio_bot
-- Tabla: bot2_pagos_notificados

CREATE TABLE valle_frio_bot.bot2_pagos_notificados (
  id SERIAL PRIMARY KEY,
  cpb_ano INT NOT NULL,
  cpb_num TEXT NOT NULL,
  cuenta_softland TEXT NOT NULL,
  banco_real TEXT NOT NULL,
  monto NUMERIC NOT NULL,
  fecha_pago DATE NOT NULL,
  productor_cod TEXT NOT NULL,
  productor_nombre TEXT,
  productor_email TEXT,
  zonal_email TEXT,
  comprobante_drive_path TEXT,
  estado TEXT NOT NULL CHECK (estado IN ('confirmado', 'rechazado', 'pendiente_contacto', 'notificado')),
  intentos_match INT DEFAULT 0,
  fecha_registro TIMESTAMP DEFAULT NOW(),
  fecha_notificacion TIMESTAMP,
  UNIQUE (cpb_ano, cpb_num, productor_cod)
);

-- Índices para optimizar búsquedas
CREATE INDEX idx_bot2_estado ON valle_frio_bot.bot2_pagos_notificados(estado);
CREATE INDEX idx_bot2_productor ON valle_frio_bot.bot2_pagos_notificados(productor_cod);
CREATE INDEX idx_bot2_comprobante ON valle_frio_bot.bot2_pagos_notificados(cpb_ano, cpb_num);
CREATE INDEX idx_bot2_fecha ON valle_frio_bot.bot2_pagos_notificados(fecha_pago);

-- Descripción de campos
COMMENT ON TABLE valle_frio_bot.bot2_pagos_notificados IS 'Registro de pagos confirmados y notificados a productores';
COMMENT ON COLUMN valle_frio_bot.bot2_pagos_notificados.cpb_ano IS 'Año del comprobante en Softland';
COMMENT ON COLUMN valle_frio_bot.bot2_pagos_notificados.cpb_num IS 'Número del comprobante en Softland';
COMMENT ON COLUMN valle_frio_bot.bot2_pagos_notificados.cuenta_softland IS 'Cuenta contable donde Softland registró el pago (ej: 10-01-10-06 para Consorcio)';
COMMENT ON COLUMN valle_frio_bot.bot2_pagos_notificados.banco_real IS 'Banco REAL de la cartola (ej: CONSORCIO), independiente de cuenta_softland';
COMMENT ON COLUMN valle_frio_bot.bot2_pagos_notificados.monto IS 'Monto pagado en Softland';
COMMENT ON COLUMN valle_frio_bot.bot2_pagos_notificados.fecha_pago IS 'Fecha de pago en el banco';
COMMENT ON COLUMN valle_frio_bot.bot2_pagos_notificados.productor_cod IS 'Código auxiliar (RUT) del productor';
COMMENT ON COLUMN valle_frio_bot.bot2_pagos_notificados.estado IS 'Estado: confirmado (cuadró), rechazado (error), pendiente_contacto (sin email), notificado (correo enviado)';
COMMENT ON COLUMN valle_frio_bot.bot2_pagos_notificados.intentos_match IS 'Cantidad de intentos de matching dentro de esta corrida';
COMMENT ON COLUMN valle_frio_bot.bot2_pagos_notificados.comprobante_drive_path IS 'Ruta completa en Google Drive del comprobante PDF';
