# === IMPORTS ===
# Bibliothèques standards
import base64
import io
from datetime import datetime
import configparser
from io import StringIO
import zipfile
from time import sleep

# Dash & Flask
import flask
import numpy as np
from dash import ALL, Dash, html, Input, Output, callback, dcc, no_update, ctx, State, State, MATCH
import dash
import dash_bootstrap_components as dbc

# Data et visualisation
import pandas as pd
import plotly.express as px
import plotly.graph_objs as go
from plotly.subplots import make_subplots

# Modules internes
from layout import layout  # Layout de l'application (interface)
from utils import *  # Fonctions utilitaires (parsing, nettoyage, etc.)

# === INITIALISATION DU SERVEUR FLASK ET DE L'APPLICATION DASH ===
server = flask.Flask(__name__)  # Nécessaire pour déployer sur des plateformes type Heroku

app = Dash(
    __name__,
    server=server,
    title='IceLoss 19',
    update_title='Updating...',  # Message temporaire pendant le chargement
    external_stylesheets=[dbc.themes.YETI],  # Thème Bootstrap
    suppress_callback_exceptions=True  # Permet de gérer les callbacks définis dynamiquement
)


# Définition du layout principal
app.layout = layout.layout

def update_dropdown(col_name, selected_file_name, file_contents, file_names,):
    if not col_name:
        return []
    selected_file_content = file_contents[file_names.index(selected_file_name)]
    df = parse_contents_into_df(selected_file_content, selected_file_name)
    unique_values_normal_ops_col = df[col_name].unique()
    return [{'label': unique_value, 'value': unique_value} for unique_value in unique_values_normal_ops_col]


@callback(
    Output('selected-file-div', 'children'), 
    Input('selected-filename', 'value'),  
    [
        State('upload-data', 'contents'),
        State('upload-data', 'filename'),
    ], 
    #prevent_initial_call=True
)
def update_output(selected_file_name, file_contents, file_names):
    selected_file_content = file_contents[file_names.index(selected_file_name)]
    return parse_contents_to_html(selected_file_content, selected_file_name)


# === CALLBACK : Affichage du contenu d'un fichier uploadé ===
@callback(
    Output('uploaded-data-output', 'children'),  # Conteneur pour afficher l'aperçu
    Input('upload-data', 'contents'),  # Contenu du fichier uploadé
    [State('upload-data', 'filename')], 
     # Nom du fichier (utilisé pour le parsing)
)
def update_output(file_contents, file_names):
    if file_contents is not None:
        return dbc.Row(children=[
            dbc.Col(
                html.H5("Filename: ", style={'fontWeight': 'bold', 'textDecoration': 'underline'}),
                width='auto',
            ),
            dbc.Col(
                dcc.Dropdown(
                    id='selected-filename', 
                    options=[{'label': file_name, 'value': file_name} for file_name in file_names],  # Choix disponibles
                    value=file_names[0],
                    #value=matched_col  # Préremplissage désactivé pour le moment
                ),
            ),
            html.Div(id='selected-file-div')
        ],
            className='my-3 mb-4'
        )


@callback(
    Output('power-curve-graph', 'figure'),
    [
        Input('selected-filename', 'value'),
        Input({'type': 'column-mapper', 'index': 'Wind speed'}, 'value'),
        Input({'type': 'column-mapper', 'index': 'Output Power'}, 'value'),
        Input({'type': 'column-mapper', 'index': 'Normal Operation'}, 'value'),
    ],
    
    [
        State('upload-data', 'contents'),
        State('upload-data', 'filename'),
    ]
)
def update_normal_ops_DD_options(selected_file_name, selected_WS_col_name, selected_P_col_name, selected_normal_ops_col_name, file_contents, file_names,):
    if selected_file_name and selected_WS_col_name and selected_P_col_name:
        selected_file_content = file_contents[file_names.index(selected_file_name)]
        df = parse_contents_into_df(selected_file_content, selected_file_name)
        
        return px.scatter(df, x=selected_WS_col_name, y=selected_P_col_name, hover_data=selected_normal_ops_col_name, color=selected_normal_ops_col_name)
    else:
        return None



@callback(
    Output('time-series-graph', 'figure'),
    [
        Input('selected-filename', 'value'),
        Input({'type': 'column-mapper', 'index': 'Timestamp'}, 'value'),
        Input({'type': 'column-mapper', 'index': 'Wind speed'}, 'value'),
        Input({'type': 'column-mapper', 'index': 'Output Power'}, 'value'),
        Input({'type': 'column-mapper', 'index': 'Normal Operation'}, 'value'),
    ],
    
    [
        State('upload-data', 'contents'),
        State('upload-data', 'filename'),
    ]
)
def update_normal_ops_DD_options(
    selected_file_name, 
    selected_time_col_name, 
    selected_WS_col_name, 
    selected_P_col_name, 
    selected_normal_ops_col_name, 
    file_contents, 
    file_names,
):
    if selected_file_name and selected_WS_col_name and selected_P_col_name:
        selected_file_content = file_contents[file_names.index(selected_file_name)]
        df = parse_contents_into_df(selected_file_content, selected_file_name)
        return px.scatter(df, x=selected_time_col_name, y=selected_P_col_name, hover_data=selected_normal_ops_col_name, color=selected_normal_ops_col_name)
    else:
        return None


# Update the key option for Normal Operation
@callback(
    Output('normal-operation-key', 'options'),
    [
        Input({'type': 'column-mapper', 'index': 'Normal Operation'}, 'value'),
        Input('selected-filename', 'value'),
    ],
    [
        State('upload-data', 'contents'),
        State('upload-data', 'filename'),
    ]
)
def update_operation_key_options(col_name, selected_file_name, file_contents, file_names,):
    if not col_name:
        return []
    selected_file_content = file_contents[file_names.index(selected_file_name)]
    df = parse_contents_into_df(selected_file_content, selected_file_name)
    unique_values_normal_ops_col = df[col_name].unique()
    return [{'label': unique_value, 'value': unique_value} for unique_value in unique_values_normal_ops_col]


# Update the maintenance key option
@callback(
    Output('column-key-oper-Maintenance', 'options'),
    Input('column-mapper-oper-Maintenance',  'value'),
    State('selected-filename', 'value'),
    State('upload-data', 'contents'),
    State('upload-data', 'filename'),
)
def update_maintenance_key_options(col_name, selected_file_name, file_contents, file_names):
    return update_dropdown(col_name, selected_file_name, file_contents, file_names)


# Update the faults key option
@callback(
    Output( 'column-key-oper-Faults', 'options'),
    Input('column-mapper-oper-Faults',  'value'),
    State('selected-filename', 'value'),
    State('upload-data', 'contents'),
    State('upload-data', 'filename'),
)
def update_faults_key_options(col_name, selected_file_name, file_contents, file_names):
    return update_dropdown(col_name, selected_file_name, file_contents, file_names)


# Update the curtailment key option
@callback(
    Output( 'column-key-oper-Curtailment', 'options'),
    Input('column-mapper-oper-Curtailment',  'value'),
    State('selected-filename', 'value'),
    State('upload-data', 'contents'),
    State('upload-data', 'filename'),
)
def update_Curtailment_key_options(col_name, selected_file_name, file_contents, file_names):
    return update_dropdown(col_name, selected_file_name, file_contents, file_names)


# Update the other manual key option
@callback(
    Output( 'column-key-oper-Other manual', 'options'),
    Input('column-mapper-oper-Other manual',  'value'),
    State('selected-filename', 'value'),
    State('upload-data', 'contents'),
    State('upload-data', 'filename'),
)
def update_other_manual_key_options(col_name, selected_file_name, file_contents, file_names):
    return update_dropdown(col_name, selected_file_name, file_contents, file_names)


# Update the icing codes key option
@callback(
    Output( 'column-key-icing-Icing codes', 'options'),
    Input('column-mapper-icing-Icing codes',  'value'),
    State('selected-filename', 'value'),
    State('upload-data', 'contents'),
    State('upload-data', 'filename'),
)
def update_icing_codes_key_options(col_name, selected_file_name, file_contents, file_names):
    return update_dropdown(col_name, selected_file_name, file_contents, file_names)


# Update the Ice detection key option
@callback(
    Output( 'column-key-icing-Ice detection', 'options'),
    Input('column-mapper-icing-Ice detection',  'value'),
    State('selected-filename', 'value'),
    State('upload-data', 'contents'),
    State('upload-data', 'filename'),
)
def update_ice_detection_key_options(col_name, selected_file_name, file_contents, file_names):
    return update_dropdown(col_name, selected_file_name, file_contents, file_names)


# Update the IPS status key option
@callback(
    Output( 'column-key-icing-IPS status', 'options'),
    Input('column-mapper-icing-IPS status',  'value'),
    State('selected-filename', 'value'),
    State('upload-data', 'contents'),
    State('upload-data', 'filename'),
)
def update_IPS_status_key_options(col_name, selected_file_name, file_contents, file_names):
    return update_dropdown(col_name, selected_file_name, file_contents, file_names)


# Fonction to validate that all required field is well chosen
def validate_required_fields(selected_columns, dropdown_ids, unit_wind_speed, unit_power, unit_temperature,
                             normal_operation_key):
    # Vérifie les colonnes manquantes
    required_fields = [id_dict["index"] for id_dict in dropdown_ids]
    missing_fields = [field for field, selected in zip(required_fields, selected_columns) if not selected]
    if missing_fields:
        return f"Choose a column for: {', '.join(missing_fields)}"

    # Vérifie si les unités et le mot-clé sont définis
    missing_params = []
    if not unit_wind_speed:
        missing_params.append("Unit wind speed")
    if not unit_temperature:
        missing_params.append("Unit temperature")
    if not unit_power:
        missing_params.append("Unit power")
    if not normal_operation_key:
        missing_params.append("Normal operation key")

    if missing_params:
        return f"Missing parameter(s): {', '.join(missing_params)}"

    return None


# === CALLBACK : Génération et téléchargement du fichier nettoyé ===
@callback(
    Output('data-to-download', 'data'),
    Output('missing-columns-alert', 'children'),
    Output('missing-columns-alert', 'is_open'),
    Input('download-clean-files', 'n_clicks'),
    [
        State('upload-data', 'contents'),
        State('upload-data', 'filename'),
        State({'type': 'column-mapper', 'index': ALL}, 'value'),
        State({'type': 'column-mapper', 'index': ALL}, 'id'),
        State('unit-wind-speed', 'value'),
        State('unit-power', 'value'),
        State('unit-temperature', 'value'),
        State('normal-operation-key', 'value'),

        # Données météo optionnelles
        State('column-mapper-met-Wind direction', 'value'),
        State('unit-wind-direction', 'value'),
        State('column-mapper-met-Pressure', 'value'),
        State('unit-pressure', 'value'),

        # Colonnes opérationnelles
        *[State(f'column-mapper-oper-{col}', 'value') for col in OPTIONAL_OPER_COLUMNS],
        *[State(f'column-key-oper-{col}', 'value') for col in OPTIONAL_OPER_COLUMNS],

        # Colonnes de givre
        *[State(f'column-mapper-icing-{col}', 'value') for col in OPTIONAL_ICING_COLUMNS],
        *[State(f'column-key-icing-{col}', 'value') for col in OPTIONAL_ICING_COLUMNS],
    ],
    prevent_initial_call=True,
)
def download_clean_file(
    n_clicks, file_contents, file_names,
    selected_columns, dropdown_ids,
    unit_wind_speed, unit_power, unit_temperature, normal_operation_key,
    wd_col, wd_unit, p_col, p_unit,
    *args
):
    if not n_clicks:
        return no_update, no_update, no_update

    # === Extraire les parties des args ===
    nb_oper = len(OPTIONAL_OPER_COLUMNS)
    nb_icing = len(OPTIONAL_ICING_COLUMNS)

    oper_cols = args[:nb_oper]
    oper_keys = args[nb_oper:nb_oper * 2]
    oper_mapping = {
        OPTIONAL_OPER_COLUMNS[i]: {
            "column": oper_cols[i] or "",
            "key": oper_keys[i] or ""
        }
        for i in range(nb_oper)
    }

    icing_cols = args[nb_oper * 2:nb_oper * 2 + nb_icing]
    icing_keys = args[nb_oper * 2 + nb_icing:nb_oper * 2 + nb_icing * 2]

    icing_mapping = {
        OPTIONAL_ICING_COLUMNS[i]: {
            "column": icing_cols[i] or "",
            "key": icing_keys[i] or ""
        }
        for i in range(nb_icing)
    }

    output_path = args[-11:]

    if n_clicks:
        df = parse_contents_into_df(file_contents[0], file_names[0])
        dfs = [parse_contents_into_df(c, n) for c, n in zip(file_contents, file_names)]
        cleaned_dfs = []

        # Récupère les noms requis attendus
        required_fields = [id_dict["index"] for id_dict in dropdown_ids]

        # Vérifie les colonnes manquantes
        missing_fields = [field for field, selected in zip(required_fields, selected_columns) if not selected]
        if missing_fields:
            # Affiche une alerte lisible
            msg = f"Choose a column for: {', '.join(missing_fields)}"
            return no_update, msg, True  # pas de téléchargement, message d'erreur visible

        # Vérifie si les unités et le mot-clé sont définis
        missing_params = []
        if not unit_wind_speed:
            missing_params.append("Unit wind speed")
        if not unit_temperature:
            missing_params.append("Unit temperature")
        if not unit_power:
            missing_params.append("Unit power")
        if not normal_operation_key:
            missing_params.append("Normal operation key")

        if missing_params:
            msg = f"Missing parameter(s): {', '.join(missing_params)}"
            return no_update, msg, True

        if len(dfs) > 1 and not all(list(df.columns) == list(dfs[0].columns) for df in dfs[1:]):
            return no_update, "Toutes les colonnes ne sont pas identiques", True

        for i, df in enumerate(dfs):
            
            # Tout est OK, créer le fichier à télécharger
            rename_map = {}
            col_normal_operation = None
            col_to_keep = []
            for col_value, id_dict in zip(selected_columns, dropdown_ids):
                label = id_dict['index']
                if label == "Normal Operation":
                    col_normal_operation = col_value
                else:
                    rename_map[col_value] = label
                col_to_keep.append(label)
            df = df.rename(columns=rename_map)

            # === Conversion 1: Timestamp ===
            if 'Timestamp' in df.columns:
                try:
                    df['Timestamp'] = pd.to_datetime(df['Timestamp'], dayfirst=True)
                    df['Timestamp'] = df['Timestamp'].dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception as e:
                    return no_update, f"Date error format for Timestamp: {str(e)}", True

            # === Conversion 2: Wind speed to m/s ===
            if 'Wind speed' in df.columns:
                if unit_wind_speed == 'kph':
                    df['Wind speed'] = df['Wind speed'] / 3.6
                elif unit_wind_speed == 'mph':
                    df['Wind speed'] = df['Wind speed'] * 0.44704

            # === Conversion 3: Output Power to kW ===
            if 'Output Power' in df.columns:
                if unit_power == 'W':
                    df['Output Power'] = df['Output Power'] / 1000
                elif unit_power == 'MW':
                    df['Output Power'] = df['Output Power'] * 1000

            # === Conversion 4: Ambient temperature to °C ===
            if 'Ambient temperature' in df.columns:
                if unit_temperature == 'F':
                    df['Ambient temperature'] = (df['Ambient temperature'] - 32) * 5.0 / 9.0
                elif unit_temperature == 'K':
                    df['Ambient temperature'] = df['Ambient temperature'] - 273.15

            # === Conversion 5: Normal Operation
            if col_normal_operation in df.columns:
                df["Normal Operation"] = df[col_normal_operation] == normal_operation_key

            # Rename Wind Direction and pressure columns
            df = df.rename(columns={wd_col: "Wind Direction", p_col: "Pressure"})

            # === Conversion 6: Wind Direction to deg
            if "Wind Direction" in df.columns:
                if wd_unit == "Radian":
                    df['Wind Direction'] = df['Wind Direction']*np.pi/180
            else:
                df["Wind Direction"] = np.nan
            col_to_keep.append("Wind Direction")

            # === Conversion 7: Pressure to Pa ===
            if "Pressure" in df.columns:
                if p_unit == "hPa":
                    df["Pressure"] = df["Pressure"] * 100
                elif p_unit == "kPa":
                    df["Pressure"] = df["Pressure"] * 1000
                elif p_unit == "atm":
                    df["Pressure"] = df["Pressure"] * 101325
                elif p_unit == "bar":
                    df["Pressure"] = df["Pressure"] * 100000
                elif p_unit == "PSI":
                    df["Pressure"] = df["Pressure"] * 6894.76
            else:
                df["Pressure"] = np.nan
            col_to_keep.append("Pressure")

            # === 8: Operation mode
            for oper_mode in oper_mapping:
                if oper_mapping[oper_mode]["column"] in df.columns:
                    df[oper_mode] = df[oper_mapping[oper_mode]["column"]] == oper_mapping[oper_mode]["key"]
                else:
                    df[oper_mode] = False
                col_to_keep.append(oper_mode)

            # === 9: Icing mode
            for icing_mode in icing_mapping:
                if icing_mapping[icing_mode]["column"] in df.columns:
                    df[icing_mode] = df[icing_mapping[icing_mode]["column"]] == icing_mapping[icing_mode]["key"]
                else:
                    df[icing_mode] = False
                col_to_keep.append(icing_mode)
            # Choose only the column to keep
            df = df[col_to_keep]
            # Remove space and capital letters
            df.columns = [col.lower().replace(" ", "_") for col in df.columns]
            cleaned_dfs.append(df)

        if len(cleaned_dfs) == 1:
            return dcc.send_data_frame(cleaned_dfs[0].to_csv, filename="cleaned_file_" + file_names[0] + ".csv", index=False, sep =','), "", False  # alert fermée

        else:
            # Multiple files: send as ZIP
            in_memory_zip = io.BytesIO()
            with zipfile.ZipFile(in_memory_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                for i, df in enumerate(dfs):
                    # Save each DataFrame as a CSV inside the zip
                    initial_fname = file_names[i]
                    file_buffer = io.StringIO()
                    df.to_csv(file_buffer, index=False, sep=',')
                    zf.writestr(f"cleaned_{initial_fname}.csv", file_buffer.getvalue())
            
            in_memory_zip.seek(0)
            return dcc.send_bytes(in_memory_zip.read(), filename=f"cleaned_files_bundle.zip"), '', False


# Download the json file
@callback(
    Output("settings-download", "data"),
    Input("download-json-btn", "n_clicks"),
    [
        State('upload-data', 'filename'),
        State({'type': 'column-mapper', 'index': ALL}, 'value'),
        State({'type': 'column-mapper', 'index': ALL}, 'id'),

        # Unités de base
        State('unit-wind-speed', 'value'),
        State('unit-power', 'value'),
        State('unit-temperature', 'value'),
        State('normal-operation-key', 'value'),

        # Données météo optionnelles
        State('column-mapper-met-Wind direction', 'value'),
        State('unit-wind-direction', 'value'),
        State('column-mapper-met-Pressure', 'value'),
        State('unit-pressure', 'value'),

        # Colonnes opérationnelles
        *[State(f'column-mapper-oper-{col}', 'value') for col in OPTIONAL_OPER_COLUMNS],
        *[State(f'column-key-oper-{col}', 'value') for col in OPTIONAL_OPER_COLUMNS],

        # Colonnes de givre
        *[State(f'column-mapper-icing-{col}', 'value') for col in OPTIONAL_ICING_COLUMNS],
        *[State(f'column-key-icing-{col}', 'value') for col in OPTIONAL_ICING_COLUMNS],

        # Infos turbine
        State('turbine-name', 'value'),
        State('rated-power', 'value'),
        State('hub-height', 'value'),
        State('elevation', 'value'),

        # Options courbe de puissance
        State('temperature-threshold', 'value'),
        State('output-path', 'value'),
        State('lower-limit', 'value'),
        State('upper-limit', 'value'),
        State('binning-min', 'value'),
        State('binning-max', 'value'),
        State('binning-step', 'value'),
    ],
    prevent_initial_call=True
)

def save_settings_to_json(n_clicks, filename, selected_columns, dropdown_ids,
                          unit_wind_speed, unit_power, unit_temperature, normal_key,
                          wd_col, wd_unit, p_col, p_unit,
                          *args):
    if not n_clicks:
        return

    # === Extraire les parties des args ===
    nb_oper = len(OPTIONAL_OPER_COLUMNS)
    nb_icing = len(OPTIONAL_ICING_COLUMNS)

    oper_cols = args[:nb_oper]
    oper_keys = args[nb_oper:nb_oper * 2]
    icing_cols = args[nb_oper * 2:nb_oper * 2 + nb_icing]
    icing_keys = args[nb_oper * 2 + nb_icing:nb_oper * 2 + nb_icing * 2]

    turbine_name, rated_power, hub_height, elevation, temp_thresh, output_path, lower_lim, upper_lim, bin_min, bin_max, bin_step = args[-11:]

    # === Construction du dictionnaire final ===
    config = {
        "columns": {
            id_dict['index']: col or "" for col, id_dict in zip(selected_columns, dropdown_ids)
        },
        "parameters": {
            "unit_wind_speed": unit_wind_speed or "",
            "unit_power": unit_power or "",
            "unit_temperature": unit_temperature or "",
            "normal_operation_key": normal_key or "",
        },
        "optional_columns": {
            "meteorological": {
                "Wind direction": {
                    "column": wd_col or "",
                    "unit": wd_unit or ""
                },
                "Pressure": {
                    "column": p_col or "",
                    "unit": p_unit or ""
                }
            },
            "operation": {
                OPTIONAL_OPER_COLUMNS[i]: {
                    "column": oper_cols[i] or "",
                    "key": oper_keys[i] or ""
                } for i in range(nb_oper)
            },
            "icing": {
                OPTIONAL_ICING_COLUMNS[i]: {
                    "column": icing_cols[i] or "",
                    "key": icing_keys[i] or ""
                } for i in range(nb_icing)
            }
        },
        "turbine_info": {
            "name": turbine_name or "",
            "rated_power_kW": rated_power if rated_power is not None else "",
            "hub_height_m": hub_height if hub_height is not None else "",
            "elevation_m": elevation if elevation is not None else ""
        },
        "power_curve_options": {
            "temperature_threshold_C": temp_thresh if temp_thresh is not None else "",
            "output_path": output_path or "",
            "lower_limit_percent": lower_lim if lower_lim is not None else "",
            "upper_limit_percent": upper_lim if upper_lim is not None else "",
            "binning": {
                "min": bin_min,
                "max": bin_max,
                "step": bin_step
            }
        }
    }

    # Génération du JSON
    json_str = json.dumps(config, indent=4)

    return dict(content=json_str, filename="settings_" + filename[0] + ".json", type="application/json")

# Download the json file and set the parameters
@callback(
    [
        # Colonnes obligatoires
        *[Output({'type': 'column-mapper', 'index': col}, 'value') for col in REQUIRED_COLUMNS],

        # Paramètres de base
        Output('unit-wind-speed', 'value'),
        Output('unit-power', 'value'),
        Output('unit-temperature', 'value'),

        # Colonnes météo optionnelles
        Output('column-mapper-met-Wind direction', 'value'),
        Output('unit-wind-direction', 'value'),
        Output('column-mapper-met-Pressure', 'value'),
        Output('unit-pressure', 'value'),

        # Colonnes opérationnelles
        *[Output(f'column-mapper-oper-{col}', 'value') for col in OPTIONAL_OPER_COLUMNS],
        *[Output(f'column-mapper-icing-{col}', 'value') for col in OPTIONAL_ICING_COLUMNS],

        # Infos turbine
        Output('turbine-name', 'value'),
        Output('rated-power', 'value'),
        Output('hub-height', 'value'),
        Output('elevation', 'value'),

        # Power curve params
        Output('temperature-threshold', 'value'),
        Output('output-path', 'value'),
        Output('lower-limit', 'value'),
        Output('upper-limit', 'value'),
        Output('binning-min', 'value'),
        Output('binning-max', 'value'),
        Output('binning-step', 'value'),

        # JSON brut à stocker
        Output('intermediate-json-config', 'data'),
    ],
    Input('settings-upload', 'contents'),
    prevent_initial_call=True
)
def load_static_settings(contents):
    if not contents:
        raise dash.exceptions.PreventUpdate

    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    config_json_str = decoded.decode('utf-8')
    config = json.loads(config_json_str)

    get_col = lambda key: config.get("columns", {}).get(key, "")
    get_param = lambda key: config.get("parameters", {}).get(key, "")

    required_values = [get_col(col) for col in REQUIRED_COLUMNS]
    param_values = [
        get_param("unit_wind_speed"),
        get_param("unit_power"),
        get_param("unit_temperature"),
    ]

    meteo = config.get("optional_columns", {}).get("meteorological", {})
    meteo_values = [
        meteo.get("Wind direction", {}).get("column", ""),
        meteo.get("Wind direction", {}).get("unit", ""),
        meteo.get("Pressure", {}).get("column", ""),
        meteo.get("Pressure", {}).get("unit", ""),
    ]

    operation = config.get("optional_columns", {}).get("operation", {})
    icing = config.get("optional_columns", {}).get("icing", {})

    oper_col_values = [operation.get(col, {}).get("column", "") for col in OPTIONAL_OPER_COLUMNS]
    icing_col_values = [icing.get(col, {}).get("column", "") for col in OPTIONAL_ICING_COLUMNS]

    turb_info = config.get("turbine_info", {})
    turbine_values = [
        turb_info.get("name", ""),
        turb_info.get("rated_power_kW", ""),
        turb_info.get("hub_height_m", ""),
        turb_info.get("elevation_m", ""),
    ]

    curve_info = config.get("power_curve_options", {})
    binning = curve_info.get("binning", {})
    curve_values = [
        curve_info.get("temperature_threshold_C", ""),
        curve_info.get("output_path", ""),
        curve_info.get("lower_limit_percent", ""),
        curve_info.get("upper_limit_percent", ""),
        binning.get("min", ""),
        binning.get("max", ""),
        binning.get("step", ""),
    ]

    return (
        required_values +
        param_values +
        meteo_values +
        oper_col_values +
        icing_col_values +
        turbine_values +
        curve_values +
        [config_json_str]  # Pour le dcc.Store
    )

@callback(
    Output('normal-operation-key', 'value'),
    *[Output(f'column-key-oper-{col}', 'value') for col in OPTIONAL_OPER_COLUMNS],
    *[Output(f'column-key-icing-{col}', 'value') for col in OPTIONAL_ICING_COLUMNS],
    Input('intermediate-json-config', 'data'),
    prevent_initial_call=True
)
def set_keys_from_stored_json(config_json_str):
    if not config_json_str:
        raise dash.exceptions.PreventUpdate
    sleep(1)
    config = json.loads(config_json_str)

    normal_key = config.get("parameters", {}).get("normal_operation_key", "")

    operation = config.get("optional_columns", {}).get("operation", {})
    icing = config.get("optional_columns", {}).get("icing", {})

    oper_keys = [operation.get(col, {}).get("key", "") for col in OPTIONAL_OPER_COLUMNS]
    icing_keys = [icing.get(col, {}).get("key", "") for col in OPTIONAL_ICING_COLUMNS]

    return [normal_key] + oper_keys + icing_keys

# === LANCEMENT DE L’APPLICATION ===
if __name__ == '__main__':
    app.run(debug=True, port=8051)  # Mode debug pour développement local