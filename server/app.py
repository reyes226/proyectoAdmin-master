import os
import re
import sys
import json
import secrets
import logging
import threading
from functools import wraps
from collections import defaultdict
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, send_from_directory, session, abort
from werkzeug.security import check_password_hash

# ── Logging ──────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)

# ── Rutas base ───────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR    = os.path.join(BASE_DIR, 'web')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
UPLOAD_DIR = os.path.join(BASE_DIR, 'procesamiento', 'uploads')
CONFIG_DIR = os.path.join(BASE_DIR, 'config')
USERS_FILE = os.path.join(CONFIG_DIR, 'users.json')
DIASINHABILES_FILE = os.path.join(CONFIG_DIR, 'dias_inhabiles.json')

sys.path.insert(0, BASE_DIR)
from procesamiento.logic import procesar

# ── App ──────────────────────────────────────────────
app = Flask(__name__, static_folder=WEB_DIR, static_url_path='')

app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY = True,
    SESSION_COOKIE_SAMESITE = 'Strict',
    SESSION_COOKIE_SECURE   = os.environ.get('HTTPS', 'false').lower() == 'true',
)

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ══════════════════════════════════════════════════════
# USUARIOS
# ══════════════════════════════════════════════════════

def _load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        raise RuntimeError(
            f"Archivo de usuarios no encontrado: {USERS_FILE}\n"
            "Ejecuta: python setup_users.py --reset"
        )
    with open(USERS_FILE, encoding='utf-8') as f:
        return json.load(f)


# ══════════════════════════════════════════════════════
# DÍAS INHABILES
# ══════════════════════════════════════════════════════

def _load_dias_inhabiles() -> list:
    """Carga la lista de días inhabiles desde el JSON."""
    if not os.path.exists(DIASINHABILES_FILE):
        return []
    try:
        with open(DIASINHABILES_FILE, encoding='utf-8') as f:
            data = json.load(f)
            return data.get('dias', [])
    except Exception:
        return []

def _save_dias_inhabiles(dias: list) -> None:
    """Guarda la lista de días inhabiles en el JSON."""
    try:
        with open(DIASINHABILES_FILE, 'w', encoding='utf-8') as f:
            json.dump({'dias': dias}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Error guardando días inhabiles: %s", e)


# ══════════════════════════════════════════════════════
# RATE LIMITING (login)
# ══════════════════════════════════════════════════════

_login_attempts: dict = defaultdict(list)
_rl_lock = threading.Lock()

def _check_rate_limit(ip: str, max_attempts: int = 5, window: int = 60) -> bool:
    """Devuelve False si la IP superó el límite de intentos."""
    now    = datetime.now()
    cutoff = now - timedelta(seconds=window)
    with _rl_lock:
        _login_attempts[ip] = [t for t in _login_attempts[ip] if t > cutoff]
        if len(_login_attempts[ip]) >= max_attempts:
            return False
        _login_attempts[ip].append(now)
        return True


# ══════════════════════════════════════════════════════
# CSRF
# ══════════════════════════════════════════════════════

def _get_csrf_token() -> str:
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']

def _validate_csrf() -> None:
    token = request.headers.get('X-CSRF-Token', '')
    if not token or token != session.get('csrf_token'):
        logger.warning("CSRF inválido desde %s", request.remote_addr)
        abort(403)


# ══════════════════════════════════════════════════════
# DECORADORES DE AUTORIZACIÓN
# ══════════════════════════════════════════════════════

def require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'usuario' not in session:
            return jsonify({'error': 'No autorizado'}), 401
        return f(*args, **kwargs)
    return decorated

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'usuario' not in session:
            return jsonify({'error': 'No autorizado'}), 401
        if session.get('rol') != 'ADMIN':
            return jsonify({'error': 'Sin permisos'}), 403
        return f(*args, **kwargs)
    return decorated


# ══════════════════════════════════════════════════════
# CABECERAS DE SEGURIDAD
# ══════════════════════════════════════════════════════

@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options']         = 'DENY'
    response.headers['X-XSS-Protection']        = '1; mode=block'
    response.headers['Referrer-Policy']          = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy']  = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self';"
    )
    return response


# ══════════════════════════════════════════════════════
# ARCHIVOS ESTÁTICOS  (web/)
# ══════════════════════════════════════════════════════

@app.route('/')
def index():
    return send_from_directory(WEB_DIR, 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    filepath = os.path.join(WEB_DIR, filename)
    if os.path.isfile(filepath):
        return send_from_directory(WEB_DIR, filename)
    return send_from_directory(WEB_DIR, 'index.html')


# ══════════════════════════════════════════════════════
# ARCHIVOS DE SALIDA  (output/)  — requiere login
# ══════════════════════════════════════════════════════

@app.route('/output/<path:filename>')
@require_login
def output_files(filename):
    # Prevenir path traversal: solo nombre de archivo
    safe_name = os.path.basename(filename)
    return send_from_directory(OUTPUT_DIR, safe_name)


# ══════════════════════════════════════════════════════
# API — AUTENTICACIÓN
# ══════════════════════════════════════════════════════

@app.route('/api/login', methods=['POST'])
def api_login():
    ip = request.remote_addr
    if not _check_rate_limit(ip):
        logger.warning("Rate limit alcanzado para IP %s", ip)
        return jsonify({'error': 'Demasiados intentos. Espera un momento.'}), 429

    data     = request.get_json(silent=True) or {}
    usuario  = str(data.get('usuario', '')).strip()
    password = str(data.get('password', ''))

    if not usuario or not password:
        return jsonify({'error': 'Credenciales requeridas'}), 400

    try:
        users = _load_users()
    except RuntimeError as e:
        logger.error("Error cargando usuarios: %s", e)
        return jsonify({'error': 'Error de configuración del servidor'}), 500

    user_data = users.get(usuario)
    if not user_data or not check_password_hash(user_data['password_hash'], password):
        logger.warning("Login fallido para '%s' desde %s", usuario, ip)
        return jsonify({'error': 'Usuario o contraseña incorrectos'}), 401

    session.clear()
    session['usuario'] = usuario
    session['rol']     = user_data['rol']
    csrf_token         = _get_csrf_token()

    logger.info("Login exitoso: %s (%s) desde %s", usuario, user_data['rol'], ip)
    return jsonify({'ok': True, 'rol': user_data['rol'], 'csrf_token': csrf_token})


@app.route('/api/logout', methods=['POST'])
def api_logout():
    usuario = session.get('usuario', 'desconocido')
    session.clear()
    logger.info("Logout: %s", usuario)
    return jsonify({'ok': True})


@app.route('/api/whoami')
def api_whoami():
    if 'usuario' not in session:
        return jsonify({'authenticated': False}), 401
    return jsonify({
        'authenticated': True,
        'usuario':    session['usuario'],
        'rol':        session['rol'],
        'csrf_token': _get_csrf_token(),
    })


# ══════════════════════════════════════════════════════
# API — DATOS
# ══════════════════════════════════════════════════════

@app.route('/api/meses')
@require_login
def get_meses():
    """Devuelve los meses disponibles ordenados de más reciente a más antiguo."""
    try:
        archivos = [
            f for f in os.listdir(OUTPUT_DIR)
            if f.startswith('data_') and f.endswith('.json')
        ]
        meses = sorted([f[5:-5] for f in archivos], reverse=True)
        return jsonify(meses)
    except Exception:
        logger.exception("Error en /api/meses")
        return jsonify({'error': 'Error al obtener meses'}), 500


_XLSX_MIMES = {
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/octet-stream',
    'application/zip',
}

@app.route('/api/upload', methods=['POST'])
@require_admin
def upload():
    """
    Recibe los dos Excel, procesa y genera el JSON del mes.
    Form-data: 'horario' (xlsx), 'registro' (xlsx)
    """
    _validate_csrf()

    horario  = request.files.get('horario')
    registro = request.files.get('registro')

    if not horario or not registro:
        return jsonify({'error': 'Se requieren ambos archivos'}), 400

    for archivo, nombre in [(horario, 'horario'), (registro, 'registro')]:
        if not archivo.filename.lower().endswith('.xlsx'):
            return jsonify({'error': f'El archivo {nombre} debe ser .xlsx'}), 400
        if archivo.mimetype and archivo.mimetype not in _XLSX_MIMES:
            return jsonify({'error': f'El tipo del archivo {nombre} no es válido'}), 400

    h_path = os.path.join(UPLOAD_DIR, 'horario.xlsx')
    r_path = os.path.join(UPLOAD_DIR, 'registro.xlsx')
    horario.save(h_path)
    registro.save(r_path)

    try:
        mes = procesar(h_path, r_path, OUTPUT_DIR)
        logger.info("Mes procesado: %s por %s", mes, session.get('usuario'))
        return jsonify({'ok': True, 'mes': mes})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception:
        logger.exception("Error al procesar archivos")
        return jsonify({'error': 'Error al procesar los archivos. Verifica el formato de los Excel.'}), 500


@app.route('/api/delete/<mes>', methods=['DELETE'])
@require_admin
def delete_mes(mes):
    """Elimina JSON y Excel de un mes. Formato esperado: 'YYYY_MM'"""
    _validate_csrf()

    if not re.match(r'^\d{4}_\d{2}$', mes):
        return jsonify({'error': 'Formato inválido'}), 400

    eliminados = []
    for nombre in [f'data_{mes}.json', f'reporte_asistencia_{mes}.xlsx']:
        path = os.path.join(OUTPUT_DIR, nombre)
        if os.path.exists(path):
            os.remove(path)
            eliminados.append(nombre)
            logger.info("Archivo eliminado: %s por %s", nombre, session.get('usuario'))

    return jsonify({'ok': True, 'eliminados': eliminados})


# ══════════════════════════════════════════════════════
# API — DÍAS INHABILES
# ══════════════════════════════════════════════════════

@app.route('/api/diasinhabiles', methods=['GET'])
@require_login
def get_diasinhabiles():
    """Obtiene la lista de días inhabiles."""
    try:
        dias = _load_dias_inhabiles()
        # Ordenar por fecha
        dias_ordenados = sorted(dias)
        return jsonify(dias_ordenados)
    except Exception:
        logger.exception("Error en /api/diasinhabiles GET")
        return jsonify({'error': 'Error al obtener días inhabiles'}), 500


@app.route('/api/diasinhabiles', methods=['POST'])
@require_admin
def add_diasinhabible():
    """Agrega un nuevo día inhabible. Requiere: {'fecha': 'YYYY-MM-DD'}"""
    _validate_csrf()
    
    data = request.get_json(silent=True) or {}
    fecha = str(data.get('fecha', '')).strip()
    
    if not fecha:
        return jsonify({'error': 'Fecha requerida'}), 400
    
    # Validar formato de fecha (YYYY-MM-DD)
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', fecha):
        return jsonify({'error': 'Formato inválido. Use YYYY-MM-DD'}), 400
    
    try:
        dias = _load_dias_inhabiles()
        
        # Evitar duplicados
        if fecha in dias:
            return jsonify({'error': 'Este día ya está marcado como inhabible'}), 400
        
        dias.append(fecha)
        _save_dias_inhabiles(dias)
        
        logger.info("Día inhabible agregado: %s por %s", fecha, session.get('usuario'))
        return jsonify({'ok': True, 'dias': sorted(dias)}), 201
    except Exception:
        logger.exception("Error al agregar día inhabible")
        return jsonify({'error': 'Error al agregar el día'}), 500


@app.route('/api/diasinhabiles/<fecha>', methods=['DELETE'])
@require_admin
def delete_diasinhabible(fecha):
    """Elimina un día inhabible. Formato esperado: 'YYYY-MM-DD'"""
    _validate_csrf()
    
    # Validar formato
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', fecha):
        return jsonify({'error': 'Formato inválido'}), 400
    
    try:
        dias = _load_dias_inhabiles()
        
        if fecha not in dias:
            return jsonify({'error': 'Este día no está en la lista'}), 404
        
        dias.remove(fecha)
        _save_dias_inhabiles(dias)
        
        logger.info("Día inhabible eliminado: %s por %s", fecha, session.get('usuario'))
        return jsonify({'ok': True, 'dias': sorted(dias)})
    except Exception:
        logger.exception("Error al eliminar día inhabible")
        return jsonify({'error': 'Error al eliminar el día'}), 500
