"""
Punto de entrada del servidor.

Uso local:
    python run.py

Producción (gunicorn):
    gunicorn run:app --bind 0.0.0.0:5000 --workers 2
"""
import os
from server.app import app

if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    print(f"Servidor en http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
