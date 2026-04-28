import logging
import os
import json
import time
import datetime as dt
import unicodedata

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ==================================================
# CONSTANTES DE PROCESAMIENTO
# ==================================================

VENTANA_ANTES   = 15   # minutos antes de la hora oficial que se considera válido
VENTANA_DESPUES = 60   # minutos después (captura toda la hora de clase)
TOLERANCIA_MIN  = 10   # minutos de retraso aceptados para marcar PUNTUAL


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
    return s


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


def estandarizar_columnas_registro(registro):
    """
    Convierte variantes de encabezados a:
    ID_DOCENTE, FECHA, HORA, PROFESOR.
    """
    id_col = buscar_columna(registro, [
        'ID_DOCENTE',
        'IDDOCENTE',
        'ID DE PERSONA',
        'ID_PERSONA',
        'IDPERSONA',
    ])
    profesor_col = buscar_columna(registro, [
        'PROFESOR',
        'PROFESOR HORA',
        'DOCENTE',
        'NOMBRE',
        'NOMBRE COMPLETO',
    ])
    fecha_col = buscar_columna(registro, ['FECHA', 'DIA'])
    hora_col = buscar_columna(registro, ['HORA', 'HORA REGISTRO'])

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
    s = str(v)
    if "-" in s:
        s = s.split("-")[0]
    digits = ''.join(c for c in s if c.isdigit())
    if len(digits) == 3:
        digits = "0" + digits
    if len(digits) == 4:
        try:
            return dt.datetime.strptime(digits, "%H%M").time()
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
    dias = str(dias).upper()
    mapa = {"L": 0, "A": 1, "M": 2, "J": 3, "V": 4, "S": 5, "D": 6}
    return [mapa[d] for d in dias if d in mapa]


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
        rows.append({
            'PROFESOR':   profesor,
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
        rows.append({'PROFESOR': profesor, **conteo_estatus(dp)})
    return rows


# ==================================================
# FUNCIÓN PRINCIPAL
# ==================================================

def procesar(horario_path: str, registro_path: str, output_dir: str) -> str:
    """
    Procesa los archivos Excel de horario y registro.

    Returns:
        mes (str): clave del mes procesado, e.g. "2026_01"

    Raises:
        ValueError: si los archivos no tienen el formato esperado.
    """
    inicio = time.perf_counter()

    os.makedirs(output_dir, exist_ok=True)

    logger.info("Leyendo horario:  %s", horario_path)
    logger.info("Leyendo registro: %s", registro_path)

    try:
        horarios = pd.read_excel(horario_path)
    except Exception as e:
        raise ValueError(f"No se pudo leer el archivo de horarios: {e}") from e

    try:
        registro = pd.read_excel(registro_path)
    except Exception as e:
        raise ValueError(f"No se pudo leer el archivo de registro: {e}") from e

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

    # ── Exportar Excel ──
    reporte_path = os.path.join(output_dir, f'reporte_asistencia_{mes}.xlsx')
    reporte_final.to_excel(reporte_path, index=False)

    # ── Exportar JSON ──
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
        'por_profesor':    por_profesor,
        'quincena_1':      quincena_1,
        'quincena_2':      quincena_2,
        'por_dia_semana':  por_dia_semana,
    }

    data_json_path = os.path.join(output_dir, f'data_{mes}.json')
    with open(data_json_path, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    logger.info("data_%s.json generado en %s", mes, output_dir)
    return mes
