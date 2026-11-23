#!/bin/bash
# Script de construcción para Vercel
echo "=== INICIANDO BUILD DE INNOVAR CALIFICA EN VERCEL ==="
python3 -m pip install -r requirements.txt
python3 manage.py collectstatic --noinput --clear
echo "=== BUILD COMPLETADO CON ÉXITO ==="
