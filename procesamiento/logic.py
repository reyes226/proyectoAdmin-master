import logging
import os
import json
import time
import datetime as dt
import unicodedata

import pandas as pd
import numpy as np
import re

logger = logging.getLogger(__name__)

# ==================================================
# CONSTANTES DE PROCESAMIENTO
# ==================================================

VENTANA_ANTES   = 15   # minutos antes de la hora oficial que se considera válido
VENTANA_DESPUES = 60   # minutos después (captura toda la hora de clase)
TOLERANCIA_MIN  = 10   # minutos de retraso aceptados para marcar PUNTUAL

VENTANA_ANTES_ADMIN   = 60   # admin: 1 hora antes de la hora de entrada
VENTANA_DESPUES_ADMIN = 120  # admin: 2 horas después de la hora de entrada


# ==================================================
# FUNCIONES DE CONFIGURACIÓN
# ==================================================

def cargar_dias_inhabiles() -> set:
    """
    Carga la lista de días inhabiles desde config/dias_inhabiles.json.
    Devuelve un set de fechas en formato YYYY-MM-DD.
    """
    config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config')
    dias_file = os.path.join(config_dir, 'dias_inhabiles.json')
    
    if not os.path.exists(dias_file):
        return set()
    
    try:
        with open(dias_file, encoding='utf-8') as f:
            data = json.load(f)
            return set(data.get('dias', []))
    except Exception as e:
        logger.warning("No se pudieron cargar los días inhabiles: %s", e)
        return set()


# ==================================================
# FUNCIONES AUXILIARES
# ==================================================

def limpiar_id(v):
    if pd.isna(v):
        return None
    s = str(v).strip().replace("'", "")
    s = ''.join(c for c in s if c.isdigit())
    if len(s) > 6:
        s = s[-6:]
    elif s:
        s = s.zfill(6)
    return s if s else None


def limpiar_texto(texto):
    texto = str(texto).upper()
    texto = unicodedata.normalize('NFKD', texto)
    texto = texto.encode('ASCII', 'ignore').decode('utf-8')
    texto = texto.replace("-", " ")
    texto = " ".join(texto.split())
    return texto


def normalizar_columna(col):
    texto = str(col).strip().lower()
    texto = unicodedata.normalize('NFKD', texto)
    texto = texto.encode('ASCII', 'ignore').decode('utf-8')
    return ''.join(c for c in texto if c.isalnum())


def buscar_columna(df, aliases):
    alias_set = {normalizar_columna(a) for a in aliases}
    for col in df.columns:
        if normalizar_columna(col) in alias_set:
            return col
    return None


def reconstruir_encabezados_desde_primera_fila(df, alias_sets):
    if df.empty:
        return df

    alias_set = {normalizar_columna(a) for aliases in alias_sets for a in aliases}
    max_filas = min(len(df), 50)

    for fila_idx in range(max_filas):
        fila = df.iloc[fila_idx].fillna('').astype(str).tolist()
        normalizados = [normalizar_columna(v) for v in fila]
        coincidencias = sum(1 for v in normalizados if v in alias_set)

        if coincidencias >= 3:
            columnas_nuevas = [v if str(v).strip() else f'Unnamed: {i}' for i, v in enumerate(fila)]
            df2 = df.iloc[fila_idx + 1 :].copy()
            df2.columns = columnas_nuevas
            return df2

    return df


def estandarizar_columnas_registro(registro):
    """
    Convierte variantes de encabezados a:
    ID_DOCENTE, FECHA, HORA, PROFESOR.
    """
    registro = reconstruir_encabezados_desde_primera_fila(registro, [
        ['ID_DOCENTE', 'IDDOCENTE', 'ID DE PERSONA', 'ID_PERSONA', 'IDPERSONA', 'ID'],
        ['PROFESOR', 'PROFESOR HORA', 'DOCENTE', 'NOMBRE', 'NOMBRE COMPLETO', 'NOMBRE DEL PROFESOR'],
        ['FECHA', 'DIA'],
        ['HORA', 'HORA REGISTRO', 'HORARIO'],
    ])

    id_col = buscar_columna(registro, [
        'ID_DOCENTE',
        'IDDOCENTE',
        'ID DE PERSONA',
        'ID_PERSONA',
        'IDPERSONA',
        'ID',
    ])
    profesor_col = buscar_columna(registro, [
        'PROFESOR',
        'PROFESOR HORA',
        'DOCENTE',
        'NOMBRE',
        'NOMBRE COMPLETO',
        'NOMBRE DEL PROFESOR',
    ])
    fecha_col = buscar_columna(registro, ['FECHA', 'DIA'])
    hora_col = buscar_columna(registro, ['HORA', 'HORA REGISTRO', 'HORARIO'])

    # Formato comun: dos columnas "HORA" (ej. HORA y HORA.1),
    # donde la primera es la fecha/dia y la segunda la hora de acceso.
    cols_hora = [c for c in registro.columns if normalizar_columna(c).startswith('hora')]
    if fecha_col is None and len(cols_hora) >= 2:
        fecha_col = cols_hora[0]
        if hora_col is None or hora_col == fecha_col:
            hora_col = cols_hora[1]

    faltantes = []
    if id_col is None:
        faltantes.append('ID_DOCENTE')
    if profesor_col is None:
        faltantes.append('PROFESOR')
    if fecha_col is None:
        faltantes.append('FECHA')
    if hora_col is None:
        faltantes.append('HORA')

    if faltantes:
        raise ValueError(
            "El archivo de registro no tiene columnas compatibles para: "
            f"{', '.join(faltantes)}. "
            f"Columnas detectadas: {list(registro.columns)}"
        )

    columnas = {
        id_col: 'ID_DOCENTE',
        profesor_col: 'PROFESOR',
        fecha_col: 'FECHA',
        hora_col: 'HORA',
    }
    columnas_finales = [id_col, profesor_col, fecha_col, hora_col]
    return registro[columnas_finales].rename(columns=columnas)


def estandarizar_columnas_horario(horarios):
    """
    Convierte variantes de encabezados a:
    ID_DOCENTE, PROFESOR, DIA, HORA.
    También detecta columnas opcionales SEMESTRE y GENERACION.
    """
    horarios = reconstruir_encabezados_desde_primera_fila(horarios, [
        ['ID_DOCENTE', 'IDDOCENTE', 'ID'],
        ['PROFESOR', 'NOMBRE DEL PROFESOR', 'NOMBRE', 'DOCENTE', 'NOMBRE COMPLETO'],
        ['DIA', 'DIAS', 'DÍA', 'DIAS DE CLASE'],
        ['HORARIO', 'HORA'],
        ['SEMESTRE', 'SEM'],
        ['GENERACION', 'GENERACIÓN', 'GEN'],
    ])

    id_col = buscar_columna(horarios, [
        'ID_DOCENTE',
        'IDDOCENTE',
        'ID',
    ])
    profesor_col = buscar_columna(horarios, [
        'PROFESOR',
        'NOMBRE DEL PROFESOR',
        'NOMBRE',
        'DOCENTE',
        'NOMBRE COMPLETO',
    ])
    dia_col = buscar_columna(horarios, ['DIA', 'DIAS', 'DÍA', 'DIAS DE CLASE'])
    hora_col = buscar_columna(horarios, ['HORARIO', 'HORA'])
    semestre_col = buscar_columna(horarios, ['SEMESTRE', 'SEM'])
    generacion_col = buscar_columna(horarios, ['GENERACION', 'GENERACIÓN', 'GEN'])

    faltantes = []
    if id_col is None:
        faltantes.append('ID')
    if profesor_col is None:
        faltantes.append('PROFESOR')
    if dia_col is None:
        faltantes.append('DIA')
    if hora_col is None:
        faltantes.append('HORARIO')

    if faltantes:
        raise ValueError(
            "El archivo de horarios no tiene columnas compatibles para: "
            f"{', '.join(faltantes)}. "
            f"Columnas detectadas: {list(horarios.columns)}"
        )

    columnas = {
        id_col: 'ID_DOCENTE',
        profesor_col: 'PROFESOR',
        dia_col: 'DIA',
        hora_col: 'HORA',
    }
    columnas_finales = [id_col, profesor_col, dia_col, hora_col]

    if semestre_col:
        columnas[semestre_col] = 'SEMESTRE'
        columnas_finales.append(semestre_col)
    if generacion_col:
        columnas[generacion_col] = 'GENERACION'
        columnas_finales.append(generacion_col)

    return horarios[columnas_finales].rename(columns=columnas)


def extraer_semestre_generacion(filename: str):
    """
    Extrae semestre y generación del nombre del archivo Excel.
    Ejemplo: "FORMATO PROGRAMACION ACADÉMICA DGE 6A GEN OTOÑO 2026 2DO SEMESTRE.xlsx"
    Retorna: (semestre_slug, generacion_slug) → ("2do", "6a")
    """
    nombre = os.path.basename(filename)
    nombre = unicodedata.normalize('NFKD', nombre.upper())
    nombre = nombre.encode('ASCII', 'ignore').decode('utf-8')

    gen_match = re.search(r'(\w+)\s+GEN\b', nombre)
    generacion = gen_match.group(1).lower() if gen_match else None

    sem_match = re.search(r'(\d+(?:[A-Z]+)?)\s+SEMESTRE', nombre)
    semestre = sem_match.group(1).lower() if sem_match else None

    return semestre, generacion


def clave_horario(nombre):
    nombre = limpiar_texto(nombre)
    partes = nombre.split()
    return partes[0] + " " + partes[1] if len(partes) >= 2 else nombre


def clave_registro(nombre):
    nombre = limpiar_texto(nombre)
    partes = nombre.split()
    return partes[-2] + " " + partes[-1] if len(partes) >= 2 else nombre


def parse_hora_horario(v):
    if pd.isna(v):
        return None
    s = str(v).lower()
    # Normalizar separadores comunes y eliminar texto no relevante
    s = s.replace('hrs', '').replace('horas', '').replace('.', ' ')

    # Buscar la primera ocurrencia de un patrón de hora (ej. 17:00, 1700, 9:00)
    m = re.search(r"(\d{1,2}[:\.]?\d{2})", s)
    if not m:
        return None
    time_str = m.group(1).replace('.', ':')
    # Asegurar formato HH:MM
    if ':' not in time_str and len(time_str) == 4:
        time_str = time_str[:2] + ':' + time_str[2:]

    try:
        return dt.datetime.strptime(time_str, "%H:%M").time()
    except Exception:
        try:
            # Intentar con %H%M por si quedó sin separador
            digits = ''.join(c for c in time_str if c.isdigit())
            if len(digits) == 3:
                digits = '0' + digits
            if len(digits) == 4:
                return dt.datetime.strptime(digits, "%H%M").time()
        except Exception:
            return None
    return None


def parse_hora_salida(v):
    """Extrae la hora de SALIDA (segunda hora) de cadenas como '08:00 - 16:00'."""
    if pd.isna(v):
        return None
    s = str(v).lower().replace('hrs', '').replace('horas', '')
    matches = re.findall(r'\d{1,2}:\d{2}', s)
    if len(matches) >= 2:
        try:
            return dt.datetime.strptime(matches[-1], "%H:%M").time()
        except Exception:
            return None
    return None


def parse_hora_registro(v):
    if pd.isna(v):
        return None
    if isinstance(v, dt.time):
        return v
    if isinstance(v, dt.datetime):
        return v.time()
    if isinstance(v, (int, float)) and 0 <= v < 1:
        # Excel puede guardar horas como fraccion de dia.
        segundos = int(round(v * 24 * 60 * 60)) % (24 * 60 * 60)
        return dt.time(segundos // 3600, (segundos % 3600) // 60, segundos % 60)
    try:
        return dt.datetime.strptime(str(v), "%H:%M:%S").time()
    except Exception:
        try:
            return dt.datetime.strptime(str(v), "%H:%M").time()
        except Exception:
            return None


def convertir_dias(dias):
    if pd.isna(dias):
        return []
    s = str(dias).upper()
    # Reemplazar separadores comunes
    s = s.replace('\r', ' ').replace('\n', ' ').replace(',', ' ').replace(';', ' ').replace('/', ' ').strip()
    mapa = {"L": 0, "A": 1, "M": 2, "J": 3, "V": 4, "S": 5, "D": 6}

    # Soporta listas de letras "L V" o rangos "L-V"
    dias_set = []
    parts = [p.strip() for p in re.split(r"[\s]+", s) if p.strip()]
    for p in parts:
        if '-' in p:
            a, b = p.split('-', 1)
            a = a.strip()
            b = b.strip()
            if a in mapa and b in mapa:
                start = mapa[a]
                end = mapa[b]
                if start <= end:
                    dias_set.extend(list(range(start, end + 1)))
                else:
                    dias_set.extend(list(range(start, 7)) + list(range(0, end + 1)))
        else:
            # Tomar cada carácter si viene junto (ej. "LVM") o la letra sola
            if len(p) > 1 and all(ch in mapa for ch in p):
                for ch in p:
                    dias_set.append(mapa[ch])
            elif p in mapa:
                dias_set.append(mapa[p])

    # Deduplicar y mantener orden
    seen = set()
    result = []
    for d in dias_set:
        if d not in seen:
            seen.add(d)
            result.append(d)
    return result


def obtener_quincena(fecha):
    return "Quincena 1" if fecha.day <= 15 else "Quincena 2"


def hora_a_minutos(t):
    if t is None or not isinstance(t, dt.time):
        return None
    return t.hour * 60 + t.minute + t.second / 60


def conteo_estatus(df):
    gp = df['ESTATUS'].value_counts()
    return {
        'PUNTUAL':    int(gp.get('PUNTUAL', 0)),
        'TOLERANCIA': int(gp.get('TOLERANCIA', 0)),
        'FALTA':      int(gp.get('FALTA', 0)),
        'TOTAL':      len(df),
    }


def contar_por_profesor_con_quincenas(df):
    rows = []
    df_valido = df[df['PROFESOR'].notna()]
    for profesor in df_valido['PROFESOR'].unique():
        dp = df_valido[df_valido['PROFESOR'] == profesor]
        ids = dp['ID_DOCENTE'].dropna().unique()
        semestres = dp['SEMESTRE'].dropna().unique() if 'SEMESTRE' in dp.columns else []
        generaciones = dp['GENERACION'].dropna().unique() if 'GENERACION' in dp.columns else []
        rows.append({
            'PROFESOR':   profesor,
            'ID':         ids[0] if len(ids) else None,
            'SEMESTRE':   semestres[0] if len(semestres) else None,
            'GENERACION': generaciones[0] if len(generaciones) else None,
            'general':    conteo_estatus(dp),
            'quincena_1': conteo_estatus(dp[dp['QUINCENA'] == 'Quincena 1']),
            'quincena_2': conteo_estatus(dp[dp['QUINCENA'] == 'Quincena 2']),
        })
    return rows


def contar_por_profesor_quincena(df, quincena_num):
    dq = df[(df['QUINCENA'] == f'Quincena {quincena_num}') & df['PROFESOR'].notna()]
    rows = []
    for profesor in dq['PROFESOR'].unique():
        dp = dq[dq['PROFESOR'] == profesor]
        ids = dp['ID_DOCENTE'].dropna().unique()
        semestres = dp['SEMESTRE'].dropna().unique() if 'SEMESTRE' in dp.columns else []
        generaciones = dp['GENERACION'].dropna().unique() if 'GENERACION' in dp.columns else []
        rows.append({
            'PROFESOR':   profesor,
            'ID':         ids[0] if len(ids) else None,
            'SEMESTRE':   semestres[0] if len(semestres) else None,
            'GENERACION': generaciones[0] if len(generaciones) else None,
            **conteo_estatus(dp)
        })
    return rows


# ==================================================
# PROCESAMIENTO DE PERSONAL ADMINISTRATIVO
# ==================================================

def _parsear_horario_admin(horario_str):
    """
    Parsea cadena de horario administrativo a lista de (dias_num, hora_entrada).

    Formatos soportados:
      "09:00 - 17:00"                                           → L-V, 09:00
      "L-J 11:00-19:00 / V 9:00-17:00"                         → L-J 11:00, V 09:00
      "X-S 13:00-21:00 / D 7:00-15:00"                         → X-S 13:00, D 07:00
      "Lunes a jueves de 11:00 a 19:00 / viernes de 9:00..."   → L-J 11:00, V 09:00
      "13:00 – 21:00 miércoles a sábado y 07:00 – 15:00 ..."   → Mi-S 13:00, D 07:00
    """
    if pd.isna(horario_str) or str(horario_str).strip() == '':
        return []

    # Mapas de días: abreviaturas y nombres completos (normalizados sin acentos)
    MAPA = {
        'L': 0, 'LU': 0, 'LUNES': 0,
        'MA': 1, 'A': 1, 'MARTES': 1,
        'MI': 2, 'X': 2, 'M': 2, 'MIERCOLES': 2,
        'J': 3, 'JU': 3, 'JUEVES': 3,
        'V': 4, 'VI': 4, 'VIERNES': 4,
        'S': 5, 'SA': 5, 'SABADO': 5,
        'D': 6, 'DO': 6, 'DOMINGO': 6,
    }
    DIAS_LV = [0, 1, 2, 3, 4]

    def _norm(s):
        """Quita acentos y pasa a mayúsculas para comparar."""
        s = unicodedata.normalize('NFKD', str(s)).encode('ASCII', 'ignore').decode('utf-8')
        return s.upper().strip()

    def _rango(ini_s, fin_s):
        ini = MAPA.get(_norm(ini_s))
        fin = MAPA.get(_norm(fin_s))
        if ini is None or fin is None:
            return []
        return list(range(ini, fin + 1)) if ini <= fin else list(range(ini, 7)) + list(range(0, fin + 1))

    def _dias_de_texto(s_norm):
        """
        Extrae lista de días de un bloque normalizado (sin acentos, mayúsculas).
        Maneja abreviaturas (L-J, V) y nombres completos (LUNES A JUEVES, VIERNES).
        """
        # Patrón 1: abreviatura con guión  "L-J", "X-S", "L-V"
        m = re.match(r'^([A-Z]+)-([A-Z]+)\s+(?=\d)', s_norm)
        if m:
            dias = _rango(m.group(1), m.group(2))
            if dias:
                return dias, m.end()

        # Patrón 2: abreviatura sola  "V 09:00", "D 07:00"
        m = re.match(r'^([A-Z]+)\s+(?=\d)', s_norm)
        if m and m.group(1) in MAPA:
            return [MAPA[m.group(1)]], m.end()

        # Patrón 3: nombre completo con rango  "LUNES A JUEVES", "MIERCOLES A SABADO"
        day_pat = '|'.join(['LUNES', 'MARTES', 'MIERCOLES', 'JUEVES', 'VIERNES', 'SABADO', 'DOMINGO'])
        m = re.search(rf'({day_pat})\s+A\s+({day_pat})', s_norm)
        if m:
            return _rango(m.group(1), m.group(2)), None

        # Patrón 4: nombre de día suelto
        for day in ['DOMINGO', 'SABADO', 'VIERNES', 'JUEVES', 'MIERCOLES', 'MARTES', 'LUNES']:
            if re.search(rf'\b{day}\b', s_norm):
                return [MAPA[day]], None

        return DIAS_LV[:], None

    s_raw = str(horario_str).strip()

    # Dividir en bloques: primero por "/", si no por " y " (con o sin acento)
    if '/' in s_raw:
        bloques = [b.strip() for b in s_raw.split('/')]
    elif re.search(r'\s+[Yy]\s+', s_raw):
        bloques = [b.strip() for b in re.split(r'\s+[Yy]\s+', s_raw)]
    else:
        bloques = [s_raw]

    resultado = []
    for bloque in bloques:
        if not bloque:
            continue
        bloque_norm = _norm(bloque)

        dias, _ = _dias_de_texto(bloque_norm)
        hora_entrada = parse_hora_horario(bloque)
        hora_salida  = parse_hora_salida(bloque)

        if hora_entrada is not None:
            resultado.append((list(dias), hora_entrada, hora_salida))

    return resultado


def _clave_admin(nombre):
    """Clave de coincidencia por palabras ordenadas (robusta ante orden diferente de apellidos/nombre)."""
    return ' '.join(sorted(limpiar_texto(nombre).split()))


def procesar_admin(horario_path: str, registro_path: str, output_dir: str) -> str:
    """
    Procesa archivos de asistencia para personal administrativo.

    El Excel de horarios acepta columnas:
      - ID/No./Num  (opcional): número de empleado
      - NOMBRE/EMPLEADO/PERSONAL/etc.: nombre completo
      - HORARIO/HORA/TURNO: p. ej. "09:00 - 17:00" o "L-J 11:00-19:00 / V 09:00-17:00"
        Si no se indican días se asume Lunes-Viernes.

    Returns:
        clave "YYYY_MM"
    """
    inicio = time.perf_counter()
    os.makedirs(output_dir, exist_ok=True)

    logger.info("(Admin) Leyendo horario:  %s", horario_path)
    logger.info("(Admin) Leyendo registro: %s", registro_path)

    try:
        horarios_raw = pd.read_excel(horario_path, header=None)
    except Exception as e:
        raise ValueError(f"No se pudo leer el archivo de horarios: {e}") from e
    try:
        registro = pd.read_excel(registro_path, header=None)
    except Exception as e:
        raise ValueError(f"No se pudo leer el archivo de registro: {e}") from e

    # ── Estandarizar registro ──
    registro = estandarizar_columnas_registro(registro)

    # ── Detectar columnas del horario administrativo ──
    horarios_raw = reconstruir_encabezados_desde_primera_fila(horarios_raw, [
        ['ID', 'NO', 'NUM', 'NUMERO', 'ID_DOCENTE', 'IDDOCENTE',
         'ID_ADMINISTRATIVO', 'IDADMINISTRATIVO', 'ID DE PERSONA'],
        ['NOMBRE', 'PERSONAL', 'EMPLEADO', 'ADMINISTRATIVO', 'PROFESOR', 'TRABAJADOR', 'NOMBRE COMPLETO'],
        ['DIAS', 'DIA', 'DIAS DE CLASE'],
        ['HORARIO', 'HORA', 'HORARIOS', 'TURNO'],
    ])

    id_col      = buscar_columna(horarios_raw, ['ID', 'NO', 'NUM', 'NUMERO', 'ID_DOCENTE', 'IDDOCENTE',
                                                'ID_ADMINISTRATIVO', 'IDADMINISTRATIVO', 'ID DE PERSONA'])
    nombre_col  = buscar_columna(horarios_raw, ['NOMBRE', 'PERSONAL', 'EMPLEADO', 'ADMINISTRATIVO',
                                                'PROFESOR', 'TRABAJADOR', 'NOMBRE COMPLETO'])
    dia_col     = buscar_columna(horarios_raw, ['DIAS', 'DIA', 'DÍA', 'DIAS DE CLASE'])
    horario_col = buscar_columna(horarios_raw, ['HORARIO', 'HORA', 'HORARIOS', 'TURNO'])

    if nombre_col is None:
        raise ValueError(
            "El archivo de horarios no tiene columna de nombre. "
            f"Columnas detectadas: {list(horarios_raw.columns)}. "
            "Se requiere una columna llamada 'NOMBRE' o 'EMPLEADO'."
        )
    if horario_col is None:
        raise ValueError(
            "El archivo de horarios no tiene columna de horario. "
            f"Columnas detectadas: {list(horarios_raw.columns)}. "
            "Se requiere una columna llamada 'HORA' o 'HORARIO'."
        )

    logger.info("(Admin) Columnas detectadas — id:%s nombre:%s dias:%s hora:%s",
                id_col, nombre_col, dia_col, horario_col)

    horarios_raw = horarios_raw[horarios_raw[nombre_col].notna()]
    horarios_raw = horarios_raw[horarios_raw[nombre_col].astype(str).str.strip() != '']

    if horarios_raw.empty:
        raise ValueError("El archivo de horarios no contiene datos válidos.")

    # ── Expandir cada persona/horario a filas de bloque ──
    filas = []
    for _, row in horarios_raw.iterrows():
        nombre_val = limpiar_texto(str(row[nombre_col]))
        emp_id     = limpiar_id(row[id_col]) if id_col else None
        dias_v     = str(row[dia_col]).strip() if dia_col and pd.notna(row.get(dia_col)) else ''
        horario_v  = str(row[horario_col]).strip() if pd.notna(row.get(horario_col)) else ''

        # Caso complejo: el campo HORA contiene múltiples bloques con "/"" o " y "
        es_complejo = '/' in horario_v or bool(re.search(r'\s+[Yy]\s+', horario_v))

        if dia_col and dias_v and not es_complejo:
            # Formato estructurado: columna DIAS + entrada simple en HORA
            dias_num = convertir_dias(dias_v)
            if not dias_num:
                dias_num = [0, 1, 2, 3, 4]
            hora_ent = parse_hora_horario(horario_v)
            hora_sal = parse_hora_salida(horario_v)
            if hora_ent is None:
                logger.warning("(Admin) Sin hora válida para '%s': '%s'", nombre_val, horario_v)
                continue
            filas.append({
                'ID_DOCENTE':       emp_id,
                'PROFESOR':         nombre_val,
                'DIAS_NUM':         dias_num,
                'HORA_ENTRADA':     hora_ent,
                'HORA_SALIDA':      hora_sal,
                'HORA_OFICIAL_MIN': hora_a_minutos(hora_ent),
                'HORA_SALIDA_MIN':  hora_a_minutos(hora_sal),
                'CLAVE_H':          clave_horario(nombre_val),
                'CLAVE_ADMIN':      _clave_admin(nombre_val),
            })
        else:
            # Formato libre: parsear el campo HORA completo
            bloques = _parsear_horario_admin(horario_v)
            if not bloques:
                logger.warning("(Admin) Horario no interpretado '%s' para '%s'", horario_v, nombre_val)
                continue
            for dias_num, hora_entrada, hora_salida in bloques:
                filas.append({
                    'ID_DOCENTE':       emp_id,
                    'PROFESOR':         nombre_val,
                    'DIAS_NUM':         dias_num,
                    'HORA_ENTRADA':     hora_entrada,
                    'HORA_SALIDA':      hora_salida,
                    'HORA_OFICIAL_MIN': hora_a_minutos(hora_entrada),
                    'HORA_SALIDA_MIN':  hora_a_minutos(hora_salida),
                    'CLAVE_H':          clave_horario(nombre_val),
                    'CLAVE_ADMIN':      _clave_admin(nombre_val),
                })

    if not filas:
        raise ValueError(
            "No se pudo interpretar ningún horario. "
            "Verifica que la columna HORARIO tenga formato 'HH:MM - HH:MM'."
        )

    horarios = pd.DataFrame(filas)
    logger.info("(Admin) Personal: %d · Bloques: %d",
                horarios['PROFESOR'].nunique(), len(horarios))

    # ── Limpiar registro ──
    registro['ID_DOCENTE']        = registro['ID_DOCENTE'].apply(limpiar_id)
    registro['FECHA']             = pd.to_datetime(registro['FECHA'], errors='coerce')
    registro['HORA_REGISTRO']     = registro['HORA'].apply(parse_hora_registro)
    registro['CLAVE_R']           = registro['PROFESOR'].apply(clave_registro)
    registro['CLAVE_ADMIN']       = registro['PROFESOR'].apply(_clave_admin)
    registro = registro.dropna(subset=['FECHA'])
    registro['HORA_REGISTRO_MIN'] = registro['HORA_REGISTRO'].apply(hora_a_minutos)

    if registro.empty:
        raise ValueError("El archivo de registro no contiene fechas válidas.")

    # ── Mapear IDs por nombre (dos estrategias para cubrir distintos ordenes) ──
    # 1. Primero intento: clave_horario / clave_registro (primeras-últimas palabras)
    mapa_ids_h = horarios.drop_duplicates('CLAVE_H').set_index('CLAVE_H')['ID_DOCENTE'].to_dict()
    registro['ID_DOCENTE'] = registro.apply(
        lambda r: mapa_ids_h.get(r['CLAVE_R'], r['ID_DOCENTE']), axis=1
    )

    # 2. Segundo intento: palabras ordenadas (robusto ante apellidos-nombre vs nombre-apellidos)
    # Construir mapping: clave_admin del horario → ID_DOCENTE del registro
    reg_id_by_admin = (
        registro[registro['ID_DOCENTE'].notna()]
        .drop_duplicates('CLAVE_ADMIN')
        .set_index('CLAVE_ADMIN')['ID_DOCENTE']
        .to_dict()
    )
    # Propagar ID al horario si no lo tiene
    def _asignar_id(row):
        if row['ID_DOCENTE'] is not None:
            return row['ID_DOCENTE']
        return reg_id_by_admin.get(row['CLAVE_ADMIN'])

    horarios['ID_DOCENTE'] = horarios.apply(_asignar_id, axis=1)

    # ── Rango de fechas ──
    fecha_min    = registro['FECHA'].min().date()
    fecha_max    = registro['FECHA'].max().date()
    rango_fechas = pd.date_range(start=fecha_min, end=fecha_max)
    mes          = fecha_min.strftime('%Y_%m')
    logger.info("(Admin) Rango: %s → %s  |  Mes: %s", fecha_min, fecha_max, mes)

    # ── Cargar días inhabiles ──
    dias_inhabiles = cargar_dias_inhabiles()
    logger.info("(Admin) Días inhabiles: %d", len(dias_inhabiles))

    # ── Generar registros esperados ──
    bloques_exp = []
    for _, h in horarios.iterrows():
        dias_set = set(h['DIAS_NUM'])
        fechas_v = rango_fechas[rango_fechas.day_of_week.isin(dias_set)]
        fechas_v = pd.DatetimeIndex([f for f in fechas_v if f.strftime('%Y-%m-%d') not in dias_inhabiles])
        if len(fechas_v) == 0:
            continue
        bloques_exp.append(pd.DataFrame({
            'ID_DOCENTE':       h['ID_DOCENTE'],
            'PROFESOR':         h['PROFESOR'],
            'HORA_OFICIAL':     h['HORA_ENTRADA'],
            'HORA_OFICIAL_MIN': h['HORA_OFICIAL_MIN'],
            'HORA_SALIDA':      h['HORA_SALIDA'],
            'HORA_SALIDA_MIN':  h['HORA_SALIDA_MIN'],
            'FECHA':            fechas_v.date,
        }))

    if not bloques_exp:
        raise ValueError("No se generaron registros esperados. Verifica días y horarios.")

    expected = pd.concat(bloques_exp, ignore_index=True)
    logger.info("(Admin) Registros esperados: %d", len(expected))

    # ── Primer checkin por persona por día ──
    reg_all = registro[registro['HORA_REGISTRO_MIN'].notna()].copy()
    reg_all['FECHA_D'] = reg_all['FECHA'].dt.date

    reg_primero = (
        reg_all.sort_values('HORA_REGISTRO_MIN')
        .groupby(['ID_DOCENTE', 'FECHA_D'], as_index=False)
        .first()
    )

    KEY = ['ID_DOCENTE', 'FECHA', 'HORA_OFICIAL_MIN']

    def _merge_y_asignar(exp_df, reg_df, ventana_min, ventana_max, puntual_fn):
        merged = exp_df.merge(
            reg_df[['ID_DOCENTE', 'FECHA_D', 'HORA_REGISTRO', 'HORA_REGISTRO_MIN']],
            left_on=['ID_DOCENTE', 'FECHA'],
            right_on=['ID_DOCENTE', 'FECHA_D'],
            how='left'
        )
        merged['DIF_MINUTOS'] = merged['HORA_REGISTRO_MIN'] - merged['HORA_OFICIAL_MIN']
        in_win = merged[merged['DIF_MINUTOS'].between(ventana_min, ventana_max)].copy()
        in_win['ABS_DIF'] = in_win['DIF_MINUTOS'].abs()

        in_win_s = in_win.sort_values('ABS_DIF').reset_index(drop=True)
        used_e, used_r, assigned = set(), set(), []
        for _, row in in_win_s.iterrows():
            ek = (row['ID_DOCENTE'], row['FECHA'],   row['HORA_OFICIAL_MIN'])
            rk = (row['ID_DOCENTE'], row['FECHA_D'], row['HORA_REGISTRO_MIN'])
            if ek not in used_e and rk not in used_r:
                used_e.add(ek); used_r.add(rk); assigned.append(row)

        if assigned:
            best = pd.DataFrame(assigned)
            best['ESTATUS'] = np.where(best['DIF_MINUTOS'].apply(puntual_fn), 'PUNTUAL', 'TOLERANCIA')
            best['DIF_MINUTOS'] = best['DIF_MINUTOS'].round(2)
        else:
            best = pd.DataFrame(columns=KEY + ['HORA_REGISTRO', 'DIF_MINUTOS', 'ESTATUS'])

        rf = exp_df.merge(best[KEY + ['HORA_REGISTRO', 'DIF_MINUTOS', 'ESTATUS']], on=KEY, how='left')
        rf['ESTATUS']       = rf['ESTATUS'].fillna('FALTA')
        rf['DIF_MINUTOS']   = rf['DIF_MINUTOS'].where(rf['ESTATUS'] != 'FALTA', None)
        rf['HORA_REGISTRO'] = rf['HORA_REGISTRO'].where(rf['ESTATUS'] != 'FALTA', None)
        return rf

    # ── Comparar primer checkin del día con HORA_ENTRADA ──
    exp_e = expected[['ID_DOCENTE', 'PROFESOR', 'FECHA', 'HORA_OFICIAL', 'HORA_OFICIAL_MIN']].copy()
    reporte_final = _merge_y_asignar(
        exp_e, reg_primero,
        -VENTANA_ANTES_ADMIN, VENTANA_DESPUES_ADMIN,
        lambda d: d <= TOLERANCIA_MIN,
    )
    logger.info("(Admin) Registros: %d", len(reporte_final))

    reporte_final = reporte_final[
        ['ID_DOCENTE', 'PROFESOR', 'FECHA', 'HORA_OFICIAL', 'HORA_REGISTRO', 'DIF_MINUTOS', 'ESTATUS']
    ].sort_values(['PROFESOR', 'FECHA', 'HORA_OFICIAL'])

    duracion = time.perf_counter() - inicio
    logger.info("(Admin) Tiempo: %.2fs", duracion)
    logger.info("(Admin) Estatus:\n%s", reporte_final['ESTATUS'].value_counts().to_string())

    # ── Exportar Excel ──
    reporte_path = os.path.join(output_dir, f'reporte_asistencia_admin_{mes}.xlsx')
    reporte_final.to_excel(reporte_path, index=False)

    # ── Exportar JSON ──
    reporte_final['QUINCENA'] = pd.to_datetime(reporte_final['FECHA']).apply(obtener_quincena)
    por_profesor = contar_por_profesor_con_quincenas(reporte_final)
    quincena_1   = contar_por_profesor_quincena(reporte_final, 1)
    quincena_2   = contar_por_profesor_quincena(reporte_final, 2)

    total_reg  = int(reporte_final.shape[0])
    total_asist = int(reporte_final['ESTATUS'].isin(['PUNTUAL', 'TOLERANCIA']).sum())
    total_falt  = int((reporte_final['ESTATUS'] == 'FALTA').sum())

    resumen_general = {
        'total':        total_reg,
        'asistencia':   round(100 * total_asist / total_reg, 2) if total_reg else 0,
        'falta':        round(100 * total_falt  / total_reg, 2) if total_reg else 0,
        'fecha_inicio': str(fecha_min),
        'fecha_fin':    str(fecha_max),
    }

    dias_nombres = {0:'Lunes', 1:'Martes', 2:'Miércoles', 3:'Jueves', 4:'Viernes', 5:'Sábado', 6:'Domingo'}
    reporte_final['DIA_SEMANA_NUM'] = pd.to_datetime(reporte_final['FECHA']).dt.dayofweek
    por_dia_semana = []
    for num in sorted(dias_nombres):
        df_dia = reporte_final[reporte_final['DIA_SEMANA_NUM'] == num]
        if len(df_dia) == 0:
            continue
        gp = df_dia['ESTATUS'].value_counts()
        por_dia_semana.append({
            'dia':        dias_nombres[num],
            'PUNTUAL':    int(gp.get('PUNTUAL', 0)),
            'TOLERANCIA': int(gp.get('TOLERANCIA', 0)),
            'FALTA':      int(gp.get('FALTA', 0)),
            'TOTAL':      int(len(df_dia)),
        })

    out = {
        'resumen_general': resumen_general,
        'semestre':        None,
        'generacion':      None,
        'por_profesor':    por_profesor,
        'quincena_1':      quincena_1,
        'quincena_2':      quincena_2,
        'por_dia_semana':  por_dia_semana,
    }

    data_json_path = os.path.join(output_dir, f'data_admin_{mes}.json')
    with open(data_json_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    logger.info("data_admin_%s.json generado en %s", mes, output_dir)
    return mes


# ==================================================
# FUNCIÓN PRINCIPAL
# ==================================================

def procesar(horario_path: str, registro_path: str, output_dir: str, tipo_horario: str = 'oficial',
             horario_original_filename: str = None) -> str:
    """
    Procesa los archivos Excel de horario y registro.

    Args:
        horario_path: ruta al archivo de horarios guardado
        registro_path: ruta al archivo de asistencia
        output_dir: directorio donde guardar los resultados
        tipo_horario: 'oficial' o 'maestria_doctorado'
        horario_original_filename: nombre original del archivo de horario (para extraer semestre/generación)

    Returns:
        clave (str): identificador del resultado, e.g. "2026_01" u "2026_10_2do_6a"

    Raises:
        ValueError: si los archivos no tienen el formato esperado.
    """
    inicio = time.perf_counter()

    os.makedirs(output_dir, exist_ok=True)

    # Extraer semestre y generación desde el nombre del archivo de horario
    semestre_slug, generacion_slug = None, None
    if tipo_horario == 'maestria_doctorado':
        nombre_ref = horario_original_filename or horario_path
        semestre_slug, generacion_slug = extraer_semestre_generacion(nombre_ref)
        logger.info("Semestre detectado: %s | Generación detectada: %s", semestre_slug, generacion_slug)

    logger.info("Leyendo horario:  %s", horario_path)
    logger.info("Leyendo registro: %s", registro_path)

    try:
        horarios = pd.read_excel(horario_path, header=None)
    except Exception as e:
        raise ValueError(f"No se pudo leer el archivo de horarios: {e}") from e

    try:
        registro = pd.read_excel(registro_path, header=None)
    except Exception as e:
        raise ValueError(f"No se pudo leer el archivo de registro: {e}") from e

    horarios = estandarizar_columnas_horario(horarios)
    registro = estandarizar_columnas_registro(registro)

    # ── Validar columnas mínimas requeridas ──
    for col in ('ID_DOCENTE', 'HORA', 'DIA', 'PROFESOR'):
        if col not in horarios.columns:
            raise ValueError(f"El archivo de horarios no tiene la columna '{col}'")
    for col in ('ID_DOCENTE', 'FECHA', 'HORA', 'PROFESOR'):
        if col not in registro.columns:
            raise ValueError(f"El archivo de registro no tiene la columna '{col}'")

    # ── Limpiar horario ──
    horarios['ID_DOCENTE']       = horarios['ID_DOCENTE'].apply(limpiar_id)
    horarios['HORA_ENTRADA']     = horarios['HORA'].apply(parse_hora_horario)
    horarios['DIAS_NUM']         = horarios['DIA'].apply(convertir_dias)
    horarios['CLAVE']            = horarios['PROFESOR'].apply(clave_horario)
    horarios = horarios.dropna(subset=['HORA_ENTRADA'])
    horarios['HORA_OFICIAL_MIN'] = horarios['HORA_ENTRADA'].apply(hora_a_minutos)

    # ── Limpiar registro ──
    registro['ID_DOCENTE']        = registro['ID_DOCENTE'].apply(limpiar_id)
    registro['FECHA']             = pd.to_datetime(registro['FECHA'], errors='coerce')
    registro['HORA_REGISTRO']     = registro['HORA'].apply(parse_hora_registro)
    registro['CLAVE']             = registro['PROFESOR'].apply(clave_registro)
    registro = registro.dropna(subset=['FECHA'])
    registro['HORA_REGISTRO_MIN'] = registro['HORA_REGISTRO'].apply(hora_a_minutos)

    if registro.empty:
        raise ValueError("El archivo de registro no contiene fechas válidas.")

    # ── Mapear IDs por clave ──
    mapa_ids = horarios.drop_duplicates('CLAVE').set_index('CLAVE')['ID_DOCENTE'].to_dict()
    registro['ID_DOCENTE'] = registro.apply(
        lambda row: mapa_ids.get(row['CLAVE'], row['ID_DOCENTE']), axis=1
    )

    # ── Rango de fechas ──
    fecha_min    = registro['FECHA'].min().date()
    fecha_max    = registro['FECHA'].max().date()
    rango_fechas = pd.date_range(start=fecha_min, end=fecha_max)
    mes          = fecha_min.strftime('%Y_%m')

    logger.info("Rango: %s → %s  |  Mes: %s", fecha_min, fecha_max, mes)

    # ── Cargar días inhabiles ──
    dias_inhabiles = cargar_dias_inhabiles()
    logger.info("Días inhabiles cargados: %d", len(dias_inhabiles))

    # ── Generar clases esperadas ──
    bloques = []
    for _, h in horarios.iterrows():
        dias_set = set(h['DIAS_NUM'])
        fechas_validas = rango_fechas[rango_fechas.day_of_week.isin(dias_set)]
        
        # Excluir días inhabiles
        fechas_validas = pd.DatetimeIndex([
            f for f in fechas_validas
            if f.strftime('%Y-%m-%d') not in dias_inhabiles
        ])
        
        if len(fechas_validas) == 0:
            continue
        bloques.append(pd.DataFrame({
            'ID_DOCENTE':       h['ID_DOCENTE'],
            'PROFESOR':         h['PROFESOR'],
            'HORA_OFICIAL':     h['HORA_ENTRADA'],
            'HORA_OFICIAL_MIN': h['HORA_OFICIAL_MIN'],
            'FECHA':            fechas_validas.date,
        }))

    if not bloques:
        raise ValueError(
            "No se generaron clases esperadas. "
            "Verifica que el archivo de horarios tenga días y horas válidos."
        )

    expected = pd.concat(bloques, ignore_index=True)
    logger.info("Clases esperadas: %d", len(expected))

    # ── Merge vectorizado ──
    reg = registro[registro['HORA_REGISTRO_MIN'].notna()].copy()
    reg['FECHA_D'] = reg['FECHA'].dt.date

    merged = expected.merge(
        reg[['ID_DOCENTE', 'FECHA_D', 'HORA_REGISTRO', 'HORA_REGISTRO_MIN']],
        left_on=['ID_DOCENTE', 'FECHA'],
        right_on=['ID_DOCENTE', 'FECHA_D'],
        how='left'
    )
    merged['DIF_MINUTOS'] = merged['HORA_REGISTRO_MIN'] - merged['HORA_OFICIAL_MIN']

    in_window = merged[merged['DIF_MINUTOS'].between(-VENTANA_ANTES, VENTANA_DESPUES)].copy()
    in_window['ABS_DIF'] = in_window['DIF_MINUTOS'].abs()

    logger.info("Coincidencias en ventana: %d", len(in_window))

    # ── Asignación greedy ──
    in_window_sorted = in_window.sort_values('ABS_DIF').reset_index(drop=True)
    used_expected, used_registro, assigned = set(), set(), []

    for _, row in in_window_sorted.iterrows():
        e_key = (row['ID_DOCENTE'], row['FECHA'],   row['HORA_OFICIAL_MIN'])
        r_key = (row['ID_DOCENTE'], row['FECHA_D'], row['HORA_REGISTRO_MIN'])
        if e_key not in used_expected and r_key not in used_registro:
            used_expected.add(e_key)
            used_registro.add(r_key)
            assigned.append(row)

    KEY = ['ID_DOCENTE', 'FECHA', 'HORA_OFICIAL_MIN']

    if assigned:
        best = pd.DataFrame(assigned)
        best['ESTATUS'] = np.where(best['DIF_MINUTOS'] <= TOLERANCIA_MIN, 'PUNTUAL', 'TOLERANCIA')
        best['DIF_MINUTOS'] = best['DIF_MINUTOS'].round(2)
    else:
        best = pd.DataFrame(columns=KEY + ['HORA_REGISTRO', 'DIF_MINUTOS', 'ESTATUS'])

    # ── Unir con esperadas → faltas ──
    reporte_final = expected.merge(
        best[KEY + ['HORA_REGISTRO', 'DIF_MINUTOS', 'ESTATUS']],
        on=KEY, how='left'
    )
    reporte_final['ESTATUS']       = reporte_final['ESTATUS'].fillna('FALTA')
    reporte_final['DIF_MINUTOS']   = reporte_final['DIF_MINUTOS'].where(reporte_final['ESTATUS'] != 'FALTA', None)
    reporte_final['HORA_REGISTRO'] = reporte_final['HORA_REGISTRO'].where(reporte_final['ESTATUS'] != 'FALTA', None)

    reporte_final = reporte_final[
        ['ID_DOCENTE', 'PROFESOR', 'FECHA', 'HORA_OFICIAL', 'HORA_REGISTRO', 'DIF_MINUTOS', 'ESTATUS']
    ].sort_values(['PROFESOR', 'FECHA', 'HORA_OFICIAL'])

    duracion = time.perf_counter() - inicio
    logger.info("Tiempo de procesamiento: %.2fs", duracion)
    logger.info("Estatus:\n%s", reporte_final['ESTATUS'].value_counts().to_string())

    # ── Construir clave del resultado (incluye semestre/gen para maestría) ──
    clave = mes
    if tipo_horario == 'maestria_doctorado' and (semestre_slug or generacion_slug):
        sem_part = semestre_slug or 'semX'
        gen_part = generacion_slug or 'genX'
        clave = f"{mes}_{sem_part}_{gen_part}"

    # ── Exportar Excel ──
    excel_prefix = f'reporte_asistencia_admin_{clave}' if tipo_horario == 'admin' else f'reporte_asistencia_{clave}'
    reporte_path = os.path.join(output_dir, f'{excel_prefix}.xlsx')
    reporte_final.to_excel(reporte_path, index=False)

    # ── Exportar JSON ──
    reporte_final['QUINCENA'] = pd.to_datetime(reporte_final['FECHA']).apply(obtener_quincena)

    por_profesor = contar_por_profesor_con_quincenas(reporte_final)
    quincena_1   = contar_por_profesor_quincena(reporte_final, 1)
    quincena_2   = contar_por_profesor_quincena(reporte_final, 2)

    # Propagar semestre y generación del archivo a cada entrada de profesor
    if tipo_horario == 'maestria_doctorado' and (semestre_slug or generacion_slug):
        sem_label = semestre_slug.upper() if semestre_slug else None
        gen_label = generacion_slug.upper() if generacion_slug else None
        for p in por_profesor:
            if p.get('SEMESTRE') is None:
                p['SEMESTRE'] = sem_label
            if p.get('GENERACION') is None:
                p['GENERACION'] = gen_label

    total_registros   = int(reporte_final.shape[0])
    total_asistencias = int(reporte_final['ESTATUS'].isin(['PUNTUAL', 'TOLERANCIA']).sum())
    total_faltas      = int((reporte_final['ESTATUS'] == 'FALTA').sum())

    resumen_general = {
        'total':        total_registros,
        'asistencia':   round(100 * total_asistencias / total_registros, 2) if total_registros else 0,
        'falta':        round(100 * total_faltas      / total_registros, 2) if total_registros else 0,
        'fecha_inicio': str(fecha_min),
        'fecha_fin':    str(fecha_max),
    }

    dias_nombres = {0:'Lunes', 1:'Martes', 2:'Miércoles', 3:'Jueves', 4:'Viernes', 5:'Sábado', 6:'Domingo'}
    reporte_final['DIA_SEMANA_NUM'] = pd.to_datetime(reporte_final['FECHA']).dt.dayofweek

    por_dia_semana = []
    for num in sorted(dias_nombres):
        df_dia = reporte_final[reporte_final['DIA_SEMANA_NUM'] == num]
        if len(df_dia) == 0:
            continue
        gp = df_dia['ESTATUS'].value_counts()
        por_dia_semana.append({
            'dia':        dias_nombres[num],
            'PUNTUAL':    int(gp.get('PUNTUAL', 0)),
            'TOLERANCIA': int(gp.get('TOLERANCIA', 0)),
            'FALTA':      int(gp.get('FALTA', 0)),
            'TOTAL':      int(len(df_dia)),
        })

    out = {
        'resumen_general': resumen_general,
        'semestre':        semestre_slug.upper() if semestre_slug else None,
        'generacion':      generacion_slug.upper() if generacion_slug else None,
        'por_profesor':    por_profesor,
        'quincena_1':      quincena_1,
        'quincena_2':      quincena_2,
        'por_dia_semana':  por_dia_semana,
    }

    # Determinar prefijo del archivo JSON según tipo de horario
    prefijo = 'data' if tipo_horario == 'oficial' else f'data_{tipo_horario}'
    data_json_path = os.path.join(output_dir, f'{prefijo}_{clave}.json')
    with open(data_json_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    logger.info("%s_%s.json generado en %s (tipo: %s)", prefijo, clave, output_dir, tipo_horario)
    return clave


def procesar_verano(horario_path: str, registro_path: str, output_dir: str, *, start_date: str, end_date: str) -> str:
    """
    Procesa un periodo personalizado (verano) usando un rango de fechas explícito.

    Args:
        horario_path: ruta al archivo de horarios
        registro_path: ruta al archivo de registro
        output_dir: directorio de salida
        start_date: fecha de inicio (YYYY-MM-DD)
        end_date: fecha fin (YYYY-MM-DD)

    Returns:
        clave (str): identificador del resultado, por ejemplo "verano_20260515_20260615"
    """
    inicio = time.perf_counter()
    os.makedirs(output_dir, exist_ok=True)

    try:
        horarios = pd.read_excel(horario_path, header=None)
    except Exception as e:
        raise ValueError(f"No se pudo leer el archivo de horarios: {e}") from e

    try:
        registro = pd.read_excel(registro_path, header=None)
    except Exception as e:
        raise ValueError(f"No se pudo leer el archivo de registro: {e}") from e

    horarios = estandarizar_columnas_horario(horarios)
    registro = estandarizar_columnas_registro(registro)

    # Validaciones mínimas
    for col in ('ID_DOCENTE', 'HORA', 'DIA', 'PROFESOR'):
        if col not in horarios.columns:
            raise ValueError(f"El archivo de horarios no tiene la columna '{col}'")
    for col in ('ID_DOCENTE', 'FECHA', 'HORA', 'PROFESOR'):
        if col not in registro.columns:
            raise ValueError(f"El archivo de registro no tiene la columna '{col}'")

    horarios['ID_DOCENTE']       = horarios['ID_DOCENTE'].apply(limpiar_id)
    horarios['HORA_ENTRADA']     = horarios['HORA'].apply(parse_hora_horario)
    horarios['DIAS_NUM']         = horarios['DIA'].apply(convertir_dias)
    horarios['CLAVE']            = horarios['PROFESOR'].apply(clave_horario)
    horarios = horarios.dropna(subset=['HORA_ENTRADA'])
    horarios['HORA_OFICIAL_MIN'] = horarios['HORA_ENTRADA'].apply(hora_a_minutos)

    registro['ID_DOCENTE']        = registro['ID_DOCENTE'].apply(limpiar_id)
    registro['FECHA']             = pd.to_datetime(registro['FECHA'], errors='coerce')
    registro['HORA_REGISTRO']     = registro['HORA'].apply(parse_hora_registro)
    registro['CLAVE']             = registro['PROFESOR'].apply(clave_registro)
    registro = registro.dropna(subset=['FECHA'])
    registro['HORA_REGISTRO_MIN'] = registro['HORA_REGISTRO'].apply(hora_a_minutos)

    if registro.empty:
        raise ValueError("El archivo de registro no contiene fechas válidas.")

    # Mapear IDs por clave
    mapa_ids = horarios.drop_duplicates('CLAVE').set_index('CLAVE')['ID_DOCENTE'].to_dict()
    registro['ID_DOCENTE'] = registro.apply(
        lambda row: mapa_ids.get(row['CLAVE'], row['ID_DOCENTE']), axis=1
    )

    # Rango de fechas forzado por parámetros
    try:
        fecha_min = pd.to_datetime(start_date).date()
        fecha_max = pd.to_datetime(end_date).date()
    except Exception:
        raise ValueError('start_date o end_date con formato inválido. Use YYYY-MM-DD')

    if fecha_min > fecha_max:
        raise ValueError('start_date debe ser anterior o igual a end_date')

    rango_fechas = pd.date_range(start=fecha_min, end=fecha_max)
    clave = f"verano_{fecha_min.strftime('%Y%m%d')}_{fecha_max.strftime('%Y%m%d')}"

    # Cargar días inhabiles
    dias_inhabiles = cargar_dias_inhabiles()

    # Generar clases esperadas usando solo el rango indicado
    bloques = []
    for _, h in horarios.iterrows():
        dias_set = set(h['DIAS_NUM'])
        fechas_validas = rango_fechas[rango_fechas.day_of_week.isin(dias_set)]
        fechas_validas = pd.DatetimeIndex([f for f in fechas_validas if f.strftime('%Y-%m-%d') not in dias_inhabiles])
        if len(fechas_validas) == 0:
            continue
        bloques.append(pd.DataFrame({
            'ID_DOCENTE':       h['ID_DOCENTE'],
            'PROFESOR':         h['PROFESOR'],
            'HORA_OFICIAL':     h['HORA_ENTRADA'],
            'HORA_OFICIAL_MIN': h['HORA_OFICIAL_MIN'],
            'FECHA':            fechas_validas.date,
        }))

    if not bloques:
        raise ValueError(
            "No se generaron clases esperadas para el periodo indicado. Revisa los días y horas en el horario."
        )

    expected = pd.concat(bloques, ignore_index=True)

    # Merge y asignación — reutilizar la lógica de diferencia y ventana
    reg = registro[registro['HORA_REGISTRO_MIN'].notna()].copy()
    reg['FECHA_D'] = reg['FECHA'].dt.date

    merged = expected.merge(
        reg[['ID_DOCENTE', 'FECHA_D', 'HORA_REGISTRO', 'HORA_REGISTRO_MIN']],
        left_on=['ID_DOCENTE', 'FECHA'],
        right_on=['ID_DOCENTE', 'FECHA_D'],
        how='left'
    )
    merged['DIF_MINUTOS'] = merged['HORA_REGISTRO_MIN'] - merged['HORA_OFICIAL_MIN']

    in_window = merged[merged['DIF_MINUTOS'].between(-VENTANA_ANTES, VENTANA_DESPUES)].copy()
    in_window['ABS_DIF'] = in_window['DIF_MINUTOS'].abs()

    in_window_sorted = in_window.sort_values('ABS_DIF').reset_index(drop=True)
    used_expected, used_registro, assigned = set(), set(), []

    for _, row in in_window_sorted.iterrows():
        e_key = (row['ID_DOCENTE'], row['FECHA'],   row['HORA_OFICIAL_MIN'])
        r_key = (row['ID_DOCENTE'], row['FECHA_D'], row['HORA_REGISTRO_MIN'])
        if e_key not in used_expected and r_key not in used_registro:
            used_expected.add(e_key)
            used_registro.add(r_key)
            assigned.append(row)

    KEY = ['ID_DOCENTE', 'FECHA', 'HORA_OFICIAL_MIN']

    if assigned:
        best = pd.DataFrame(assigned)
        best['ESTATUS'] = np.where(best['DIF_MINUTOS'] <= TOLERANCIA_MIN, 'PUNTUAL', 'TOLERANCIA')
        best['DIF_MINUTOS'] = best['DIF_MINUTOS'].round(2)
    else:
        best = pd.DataFrame(columns=KEY + ['HORA_REGISTRO', 'DIF_MINUTOS', 'ESTATUS'])

    reporte_final = expected.merge(
        best[KEY + ['HORA_REGISTRO', 'DIF_MINUTOS', 'ESTATUS']],
        on=KEY, how='left'
    )
    reporte_final['ESTATUS']       = reporte_final['ESTATUS'].fillna('FALTA')
    reporte_final['DIF_MINUTOS']   = reporte_final['DIF_MINUTOS'].where(reporte_final['ESTATUS'] != 'FALTA', None)
    reporte_final['HORA_REGISTRO'] = reporte_final['HORA_REGISTRO'].where(reporte_final['ESTATUS'] != 'FALTA', None)

    reporte_final = reporte_final[
        ['ID_DOCENTE', 'PROFESOR', 'FECHA', 'HORA_OFICIAL', 'HORA_REGISTRO', 'DIF_MINUTOS', 'ESTATUS']
    ].sort_values(['PROFESOR', 'FECHA', 'HORA_OFICIAL'])

    # Exportar Excel
    reporte_path = os.path.join(output_dir, f'reporte_asistencia_verano_{clave}.xlsx')
    reporte_final.to_excel(reporte_path, index=False)

    # Exportar JSON con misma estructura esperada
    reporte_final['QUINCENA'] = pd.to_datetime(reporte_final['FECHA']).apply(obtener_quincena)

    por_profesor = contar_por_profesor_con_quincenas(reporte_final)
    quincena_1   = contar_por_profesor_quincena(reporte_final, 1)
    quincena_2   = contar_por_profesor_quincena(reporte_final, 2)

    total_registros   = int(reporte_final.shape[0])
    total_asistencias = int(reporte_final['ESTATUS'].isin(['PUNTUAL', 'TOLERANCIA']).sum())
    total_faltas      = int((reporte_final['ESTATUS'] == 'FALTA').sum())

    resumen_general = {
        'total':        total_registros,
        'asistencia':   round(100 * total_asistencias / total_registros, 2) if total_registros else 0,
        'falta':        round(100 * total_faltas      / total_registros, 2) if total_registros else 0,
        'fecha_inicio': str(fecha_min),
        'fecha_fin':    str(fecha_max),
    }

    dias_nombres = {0:'Lunes', 1:'Martes', 2:'Miércoles', 3:'Jueves', 4:'Viernes', 5:'Sábado', 6:'Domingo'}
    reporte_final['DIA_SEMANA_NUM'] = pd.to_datetime(reporte_final['FECHA']).dt.dayofweek

    por_dia_semana = []
    for num in sorted(dias_nombres):
        df_dia = reporte_final[reporte_final['DIA_SEMANA_NUM'] == num]
        if len(df_dia) == 0:
            continue
        gp = df_dia['ESTATUS'].value_counts()
        por_dia_semana.append({
            'dia':        dias_nombres[num],
            'PUNTUAL':    int(gp.get('PUNTUAL', 0)),
            'TOLERANCIA': int(gp.get('TOLERANCIA', 0)),
            'FALTA':      int(gp.get('FALTA', 0)),
            'TOTAL':      int(len(df_dia)),
        })

    out = {
        'resumen_general': resumen_general,
        'semestre':        None,
        'generacion':      None,
        'por_profesor':    por_profesor,
        'quincena_1':      quincena_1,
        'quincena_2':      quincena_2,
        'por_dia_semana':  por_dia_semana,
    }

    data_json_path = os.path.join(output_dir, f'data_verano_{clave}.json')
    with open(data_json_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    logger.info("data_verano_%s.json generado en %s", clave, output_dir)
    return clave
