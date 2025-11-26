# === IMPORTS ===
import pandas as pd
import base64
import io
import csv
import json

# Dash components pour affichage
from dash import html, dcc, ctx
import dash_bootstrap_components as dbc

# === COLONNES REQUISES POUR LE TRAITEMENT ===
REQUIRED_COLUMNS = [
    'Timestamp',
    'Wind speed',
    'Ambient temperature',
    'Output Power',
    'Normal Operation'
]

# === COLONNES OPTIONNELLES ===
OPTIONAL_OPER_COLUMNS = [
    "Maintenance",
    "Faults",
    "Curtailment",
    "Other manual",
]

OPTIONAL_ICING_COLUMNS = [
    "Icing codes",
    "Ice detection",
    "IPS status"
]

OPTIONAL_COLUMNS_met = [
    'Wind direction',
    'Pressure'
]


def clean_column_name(name):
    """
    Nettoie un nom de colonne en supprimant les unités entre crochets
    et en mettant tout en minuscule.
    Exemple :
        'Temperature [°C]' -> 'temperature'
    Utile pour faire des comparaisons plus souples entre noms.
    """
    return name.split('[')[0].strip().lower()


def parse_contents_into_df(contents, filename):
    """
    Décode les données encodées (base64) reçues d’un composant dcc.Upload
    et retourne un DataFrame Pandas en fonction du type de fichier (CSV ou Excel).

    Parameters:
        - contents : chaîne encodée base64 contenant les données
        - filename : nom du fichier (permet d’identifier le format)

    Returns:
        - df : DataFrame avec les données du fichier
    """
    # Séparation du type MIME et des données
    content_type, content_string = contents.split(',')

    # Décodage base64 en bytes
    decoded = base64.b64decode(content_string)
    try:
        if 'csv' in filename.lower():
            # Lecture partielle du fichier pour détecter le délimiteur
            sample = decoded[:1024].decode('utf-8', errors='ignore')  # décode juste un bout
            sniffer = csv.Sniffer()
            try:
                dialect = sniffer.sniff(sample)
                delim = dialect.delimiter
            except csv.Error:
                # Si Sniffer échoue, on utilise la virgule par défaut
                delim = ','

            # Lecture complète du fichier avec le bon délimiteur
            df = pd.read_csv(io.StringIO(decoded.decode('utf-8')), delimiter=delim)

        elif 'xls' in filename.lower():
            df = pd.read_excel(io.BytesIO(decoded))

        else:
            raise ValueError("Format de fichier non reconnu.")

    except Exception as e:
        print(f"Erreur de lecture du fichier {filename}: {e}")
        df = pd.DataFrame()

    return df


def parse_contents_to_html(contents, filename):
    """
    Génère un aperçu HTML à partir d’un fichier uploadé, incluant :
        - un aperçu des 5 premières lignes du DataFrame,
        - une série de menus déroulants pour associer les colonnes obligatoires,
        - un bouton de téléchargement.

    Parameters:
        - contents : contenu base64 du fichier
        - filename : nom du fichier

    Returns:
        - html.Div contenant tous les éléments décrits ci-dessus
    """
    # Conversion du fichier en DataFrame
    df = parse_contents_into_df(contents, filename)

    # Création d’un tableau Bootstrap à partir des 5 premières lignes
    table = dbc.Table.from_dataframe(
        df.head(5),
        striped=True,
        bordered=True,
        hover=True
    )

    # Liste des colonnes présentes dans le fichier importé
    uploaded_columns = list(df.columns)

    # Création d'un mapping {nom nettoyé : nom original}
    uploaded_clean_cols_map = {
        clean_column_name(col): col for col in uploaded_columns
    }

    dropdowns_units_map_required = {
        REQUIRED_COLUMNS[0]: html.Div(), # Timestamp, no units
        REQUIRED_COLUMNS[1]: dbc.Col([
                dbc.Label("Unit wind speed"),
                dcc.Dropdown(
                    id="unit-wind-speed",
                    options=[
                        {"label": "m/s", "value": "m/s"},
                        {"label": "km/h", "value": "kph"},
                        {"label": "mph", "value": "mph"},
                    ],
                    placeholder="Select wind speed unit"
                ),
            ], 
        ),
        REQUIRED_COLUMNS[2]: dbc.Col([
                dbc.Label("Unit temperature"),
                dcc.Dropdown(
                    id="unit-temperature",
                    options=[
                        {"label": "°C", "value": "C"},
                        {"label": "°F", "value": "F"},
                        {"label": "K", "value": "K"},
                    ],
                    placeholder="Select temperature unit"
                ),
            ], 
        ),
        REQUIRED_COLUMNS[3]: dbc.Col([
                dbc.Label("Unit power"),
                dcc.Dropdown(
                    id="unit-power",
                    options=[
                        {"label": "W", "value": "W"},
                        {"label": "kW", "value": "kW"},
                        {"label": "MW", "value": "MW"},
                    ],
                    placeholder="Select power unit"
                ),
            ], 
        ),
        REQUIRED_COLUMNS[4]: dbc.Col([
                dbc.Label("Normal Operation key"),
                # dbc.Input(id="normal-operation-key", type="text", placeholder="Enter key"),
                dcc.Dropdown(
                    id="normal-operation-key",
                    placeholder="Enter key"
                ),

            ],
        )
    }

    dropdowns_units_map_optional = {
        OPTIONAL_COLUMNS_met[0]: dbc.Col([
            #dbc.Label("Unit wind direction"),
            dcc.Dropdown(
                id="unit-wind-direction",
                options=[
                    {"label": "°", "value": "Deg"},
                    {"label": "radian", "value": "Radian"},
                ],
                placeholder="Select wind direction unit"
            ),
        ],
        ),
        OPTIONAL_COLUMNS_met[1]: dbc.Col([
            #.Label("Unit pressure"),
            dcc.Dropdown(
                id="unit-pressure",
                options=[
                    {"label": "Pa", "value": "Pa"},
                    {"label": "hPa", "value": "hPa"},
                    {"label": "kPa", "value": "kPa"},
                    {"label": "atm", "value": "atm"},
                    {"label": "bar", "value": "bar"},
                    {"label": "PSI", "value": "PSI"},
                ],
                placeholder="Select pressure unit"
            ),
        ],
        )
    }

    dropdowns = []  # Liste des menus déroulants

    # Pour chaque colonne requise, créer un menu déroulant pour faire le mapping
    for required_col in REQUIRED_COLUMNS:
        # Essayer d'identifier une colonne correspondante automatiquement
        matched_col = uploaded_clean_cols_map.get(clean_column_name(required_col), None)

        # Crée une colonne Bootstrap contenant un label + un dropdown
        dropdown_col = dbc.Col(
            [
                html.Div(required_col, style={'fontWeight': 'bold'}),
                dcc.Dropdown(
                    id={'type': 'column-mapper', 'index': required_col},  # ID dynamique pour callback
                    options=[{'label': c, 'value': c} for c in uploaded_columns],  # Choix disponibles
                    placeholder=f"Select uploaded col name for {required_col}",
                    value=matched_col  # Préremplissage désactivé pour le moment
                ),
                dropdowns_units_map_required[required_col]
            ],
            className="mb-3"  # Marge en bas
        )

        dropdowns.append(dropdown_col)

    # Adding optional parameters
    dropdowns.append(
        html.H5("Select the optional columns:", style={'fontWeight': 'bold', 'textDecoration': 'underline'})
    )

    dropdowns.append(
        dbc.Accordion([
            # Bloc pour les colonnes météo
            dbc.AccordionItem(
                children=[
                    html.H6("Meteorological (optional)", className="mt-2"),
                    dbc.Row([
                        dbc.Col([
                            html.Div(col, style={'fontWeight': 'bold'}),
                            dcc.Dropdown(
                                # id={'type': 'column-mapper_oper', 'index': col},
                                id='column-mapper-met-' + col,
                                options=[{'label': c, 'value': c} for c in uploaded_columns],
                                placeholder=f"Select uploaded col name for {col}",
                            ),
                            dbc.Label("Unit " + col.lower()),
                            dropdowns_units_map_optional.get(col, html.Div())
                            #dcc.Dropdown(
                            #    # id={'type': 'column-key-oper', 'index': col},
                            #    id='column-key-oper-' + col,
                            #    options=[],
                            #    placeholder=f"Choose key",
                            #),
                        ], width=6)  # if len(OPTIONAL_OPER_COLUMNS) == 2 else 4)  # Ajuste largeur selon le nombre
                        for col in OPTIONAL_COLUMNS_met
                    ])
                ],
                title=html.Span("Click to expand: Meteorological", style={'textDecoration': 'underline'}),
                item_id="accordion-met"
            ),

            # Bloc pour les colonnes opérationnelles
            dbc.AccordionItem(
                children=[
                    html.H6("Wind Turbine Operation (optional)", className="mt-2"),
                    dbc.Row([
                        dbc.Col([
                            html.Div(col, style={'fontWeight': 'bold'}),
                            dcc.Dropdown(
                                #id={'type': 'column-mapper_oper', 'index': col},
                                id = 'column-mapper-oper-' + col,
                                options=[{'label': c, 'value': c} for c in uploaded_columns],
                                placeholder=f"Select uploaded col name for {col}",
                            ),
                            dbc.Label(col  + " key"),
                            dcc.Dropdown(
                                #id={'type': 'column-key-oper', 'index': col},
                                id='column-key-oper-' + col,
                                options=[],
                                placeholder=f"Choose key",
                            ),
                        ], width=6)# if len(OPTIONAL_OPER_COLUMNS) == 2 else 4)  # Ajuste largeur selon le nombre
                        for col in OPTIONAL_OPER_COLUMNS
                    ])
                ],
                title=html.Span("Click to expand: Wind turbine operation", style={'textDecoration': 'underline'}),
                item_id="accordion-operation"
            ),

            # Bloc pour les colonnes de givre
            dbc.AccordionItem(
                children=[
                    html.H6("Icing Flags (optional)", className="mt-2"),
                    dbc.Row([
                        dbc.Col([
                            html.Div(col, style={'fontWeight': 'bold'}),
                            dcc.Dropdown(
                                id="column-mapper-icing-" + col,
                                options=[{'label': c, 'value': c} for c in uploaded_columns],
                                placeholder=f"Select uploaded col name for {col}",
                            ),
                            dbc.Label(col  + " key"),
                            dcc.Dropdown(
                                id='column-key-icing-' + col,
                                options=[],
                                placeholder=f"Choose key",
                            )
                        ], width=6 if len(OPTIONAL_ICING_COLUMNS) == 2 else 4)
                        for col in OPTIONAL_ICING_COLUMNS
                    ])
                ],
                title=html.Span("Click to expand: Icing flags", style={'textDecoration': 'underline'}),
                item_id="accordion-icing"
            ),
        ],
            id="accordion-advanced-options",
            active_item=None  # Aucun ouvert par défaut
        )
    )

    # Retourne le bloc complet : nom du fichier + tableau + mapping + bouton
    return html.Div([
  
        table,  # Aperçu tableau
        dbc.Row([
            dbc.Col([
                dcc.Upload(
                    id='settings-upload',
                    children=dbc.Button("Load Metadata", id="load-settings-btn", color="secondary"),
                    accept='.json',
                    multiple=False,
                    style={'cursor': 'pointer'}
                ),
            ], width="auto"),
        ],
            justify='start',
            className="my-3"
        ),

        html.H5(html.Span("Select the corresponding columns*: ", style={'fontWeight': 'bold', 'textDecoration': 'underline'})),
        dbc.Row(dropdowns, className="mt-4"),  # Menus dropdown pour associer les colonnes

        # Ligne d'alerte
        dbc.Alert(id='missing-columns-alert', color='danger', is_open=False),

        # Ligne des boutons
        dbc.Row([
            dbc.Col(
                dbc.Button("Download Clean Files", id='download-clean-files', color="primary"),
                width="auto"
            ),
        ],
            justify='center',
            className="my-3"
        ),

        # Add optional columns
        html.H5(html.Span("Select the corresponding parameters*: ",
                          style={'fontWeight': 'bold', 'textDecoration': 'underline'})),
        # Zone des paramètres supplémentaires
        dbc.Accordion([
            # --- Bloc 1 : Turbine Information ---
            dbc.AccordionItem(
                children=[
                    html.H6("Turbine information", className="mt-2"),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Name"),
                            dbc.Input(id='turbine-name', type='text', placeholder="Enter turbine name"),
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Rated power (kW)"),
                            dbc.Input(id='rated-power', type='number', placeholder="e.g., 800"),
                        ], width=6),
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Hub height (m)"),
                            dbc.Input(id='hub-height', type='number', placeholder="e.g., 50"),
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Elevation (m)"),
                            dbc.Input(id='elevation', type='number', placeholder="e.g., 10"),
                        ], width=6),
                    ]),
                ],
                title=html.Span("Turbine information", style={'textDecoration': 'underline'}),
                item_id="accordion-turbine-info"
            ),

            # --- Bloc 2 : Power Curve Options ---
            dbc.AccordionItem(
                children=[
                    html.H6("Power curves option", className="mt-2"),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Temperature threshold (°C)"),
                            dbc.Input(id='temperature-threshold', type='number', value=3),
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Output pathfile"),
                            dbc.Input(id='output-path', type='text', value="output/power_curve"),
                        ], width=6),
                    ]),
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Lower percentage limit (%)"),
                            dbc.Input(id='lower-limit', type='number', value=10),
                        ], width=6),
                        dbc.Col([
                            dbc.Label("Higher percentage limit (%)"),
                            dbc.Input(id='upper-limit', type='number', value=90),
                        ], width=6),
                    ]),
                    html.Div([
                        dbc.Label("Binning option", className="mt-3"),
                        dbc.Row([
                            dbc.Col([
                                dbc.Label("Min value"),
                                dbc.Input(id='binning-min', type='number', value=0),
                            ], width=4),
                            dbc.Col([
                                dbc.Label("Max value"),
                                dbc.Input(id='binning-max', type='number', value=30),
                            ], width=4),
                            dbc.Col([
                                dbc.Label("Increment value"),
                                dbc.Input(id='binning-step', type='number', value=1),
                            ], width=4),
                        ])
                    ])
                ],
                title=html.Span("Power curves option", style={'textDecoration': 'underline'}),
                item_id="accordion-power-curves"
            )
        ], start_collapsed=True),

        # Bouton de téléchargement JSON
        dbc.Row([
            dbc.Col(
                dbc.Button("Download Metadata (JSON)", id='download-json-btn', color="secondary", type="button"),
                width="auto"
            )
        ], justify='center', className="mb-4"),

        dcc.Graph(id='power-curve-graph'),
        dcc.Graph(id='time-series-graph'),
    ])