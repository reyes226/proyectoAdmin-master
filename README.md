# Sistema de Control de Asistencia Docente

Estructura del proyecto reorganizada para mejor mantenimiento y escalabilidad.

## 📁 Estructura de Carpetas

```
/proyecto
│
├── procesamiento/
│   ├── app.py                          # Script principal de procesamiento
│   ├── Horario_oficial.xlsx            # Archivo de horarios (entrada)
│   └── REGISTRO ASISTENCIA ENE-26.xlsx # Registro de asistencia (entrada)
│
├── output/
│   ├── reporte_asistencia.xlsx         # Reporte generado (salida)
│   ├── estadisticas_prof.xlsx          # Estadísticas por profesor (salida)
│   └── data.json                       # Datos para frontend (salida)
│
├── web/
│   ├── index.html                      # Página principal
│   ├── dashboard.html                  # Panel de control
│   ├── login.html                      # Página de login
│   ├── js/
│   │   ├── main.js                     # Script principal
│   │   └── auth.js                     # Script de autenticación
│   └── css/
│       └── style.css                   # Estilos
│
├── config/
│   └── reglas.json                     # Configuración de reglas
│
└── README.md                           # Este archivo
```

## 🚀 Cómo Usar

### 1. Preparar los datos de entrada

- Coloca el archivo `Horario_oficial.xlsx` en la carpeta `/procesamiento/`
- Coloca el archivo `REGISTRO ASISTENCIA ENE-26.xlsx` en la carpeta `/procesamiento/`

### 2. Ejecutar el procesamiento

```bash
cd procesamiento
python app.py
```

### 3. Verificar los resultados

Los archivos generados se guardarán en `/output/`:
- `reporte_asistencia.xlsx` - Reporte detallado
- `data.json` - Datos para el frontend

### 4. Ver el dashboard

Abre `/web/dashboard.html` en tu navegador para ver las estadísticas.

## 📊 Configuración

Edita `config/reglas.json` para cambiar:
- Tolerancia de minutos
- Ventana de entrada
- Definición de quincenas

## 📝 Campos de Salida

El archivo `data.json` contiene:

```json
{
  "resumen_general": {
    "total": 0,
    "asistencia": 0,
    "retardo": 0,
    "falta": 0
  },
  "por_profesor": [
    {
      "PROFESOR": "Nombre",
      "general": {...},
      "quincena_1": {...},
      "quincena_2": {...}
    }
  ],
  "quincena_1": [...],
  "quincena_2": [...]
}
```

## 🔧 Requisitos

- Python 3.7+
- pandas
- openpyxl (para Excel)

Instalar dependencias:
```bash
pip install pandas openpyxl
```

## 📄 Notas

- La quincena 1 abarca días 1-15
- La quincena 2 abarca días 16 hasta fin de mes
- Los registros con profesor desconocido (NaN) se filtran automáticamente
- El sistema considera TOLERANCIA dentro del rango configurado
