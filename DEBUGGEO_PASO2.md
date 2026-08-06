# Debuggeo del Paso 2 - Descarga de Nómina PDF

## Estado Actual
- ✅ **PASO 1**: Cartola descargada y subida a Drive - **100% FUNCIONAL**
- ✅ **Scheduler**: Ejecuta automáticamente a las 08:00 y 12:00
- ❌ **PASO 2**: Nómina PDF - En debuggeo

## El Problema
El bot no puede encontrar los selectores de `"Estado de Firmas"` después de navegar a la sección de Pago Nómina.

Pasos completados exitosamente:
1. ✅ Click en menú "Pagos"
2. ✅ Click en opción de nómina  
3. ✅ Menú cargado
4. ❌ Búsqueda de "Estado de Firmas" - **FALLA AQUÍ**

## Cómo Debuggear Manualmente

### Paso 1: Abre el navegador
```
Ve a: https://servicios.bancoconsorcio.cl/BancaEmpresas/nominas/consultar
```

### Paso 2: Navega a Estado de Firmas
1. Haz click en el menú superior **"Pagos"**
2. Selecciona **"Pago nómina"**
3. Deberías ver las tabs:
   - Ingresar
   - **Consultar** ← Haz click aquí
   - Seguimiento y resultado

### Paso 3: Dentro de "Consultar", encontrarás:
   - **Estado de Firmas** (activa por defecto)
   - Seguimiento de pagos
   - Consulta histórica

### Paso 4: Extrae los selectores
Abre **DevTools (F12)** y busca:

```html
<!-- Busca este elemento dentro de "Consultar" -->
a:has-text('Estado de Firmas')
<!-- O -->
button:has-text('Estado de Firmas')
```

Verifica el HTML exacto de:
1. La tab/botón "Estado de Firmas"
2. El icono de 3 puntos (⋮) en la columna "Acciones"
3. El link "Descarga PDF" en el menú desplegable

### Paso 5: Actualiza el código
Una vez tengas los selectores correctos, actualiza `procesos/descargar_nomina.py` con:
- Selector de "Estado de Firmas"
- Selector del icono de acciones
- Selector de "Descarga PDF"

## Selectores Conocidos que Funcionan
```python
# El botón dropdown de acciones funciona:
"button.dropdown"

# El link de descarga funciona:
"a.dropdown-content-action:has-text('Descarga PDF')"
```

## Notas
- El problema está en encontrar la tab "Estado de Firmas" **después** de estar en "Pago Nómina > Consultar"
- Es posible que esté dentro de un iframe o contenedor dinámico
- Podría requerir esperas más largas para que carguen los elementos

## Recursos
- Selector del bot: `procesos/descargar_nomina.py` línea ~50
- Test manual: Abre el navegador en modo headless=False en `run.py`
