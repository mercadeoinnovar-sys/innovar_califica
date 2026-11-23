import os
import sys
from pathlib import Path

# Agregar directorio raíz al sys.path para que Django encuentre innovar_service y main
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'innovar_service.settings')

from django.core.wsgi import get_wsgi_application

# Vercel Serverless Function entry point
app = get_wsgi_application()
