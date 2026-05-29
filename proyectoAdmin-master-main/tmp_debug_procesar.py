import pandas as pd, os, sys
sys.path.insert(0, 'procesamiento')
from logic import procesar

horario = r'procesamiento\\FORMATO PROGRAMACION ACADÉMICA DGE 6A GEN OTOÑO 2026 2DO SEMESTRE.xlsx'
# Minimal registro with header row (will be interpreted by parser)
reg = pd.DataFrame([
    ['ID','PROFESOR','FECHA','HORA'],
    ['100376444','Dr. José Aurelio Cruz de los Angeles','2026-08-10','17:00:00'],
    ['100376444','Dr. José Aurelio Cruz de los Angeles','2026-09-10','17:00:00'],
])
registro_path = 'tmp_registro.xlsx'
reg.to_excel(registro_path, index=False, header=False)
try:
    mes = procesar(horario, registro_path, 'tmp_output', tipo_horario='maestria_doctorado')
    print('procesar ok', mes)
except Exception as e:
    print('procesar error', type(e).__name__, str(e))
finally:
    if os.path.exists(registro_path): os.remove(registro_path)
    if os.path.exists('tmp_output'):
        import shutil
        shutil.rmtree('tmp_output')
