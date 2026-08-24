#!/usr/bin/env python3
"""Test obtener_egresos_softland con el nuevo filtro de nóminas"""
import sys
sys.path.insert(0, 'bot2')

from gaussdb_client import obtener_egresos_softland

print("Obteniendo egresos con nuevo filtro (emisión de nómina)...")
egresos = obtener_egresos_softland(dias_atras=30)

print(f"\nTotal egresos encontrados: {len(egresos)}")

# Buscar comprobante 00023091
cpb_23091 = [e for e in egresos if e['CpbNum'] == '00023091']
print(f"Líneas del comprobante 00023091: {len(cpb_23091)}")

if cpb_23091:
    print("\nPrimeras 3 líneas del 00023091:")
    for row in cpb_23091[:3]:
        print(f"  RUT {row['productor_cod']}: ${row['monto_productor']:,}")
else:
    print("Comprobante 00023091 NO encontrado (error)")

# Resumen por fecha
from collections import Counter
fechas = Counter([e['fecha'] for e in egresos])
print(f"\nEgresos por fecha:")
for fecha in sorted(fechas.keys(), reverse=True):
    print(f"  {fecha}: {fechas[fecha]} egresos")
