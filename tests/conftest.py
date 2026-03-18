"""
conftest.py — configuración global del entorno de tests.
Mockeamos el cliente de Supabase antes de que cualquier módulo lo importe,
así los tests no necesitan credenciales reales.
"""