import pandas as pd
import base64
import io
import csv

from dash import html, dcc, ctx, dash_table
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc  

REQUIRED_COLUMNS = [
    'Timestamp',
    'Wind speed',
    'Ambient temperature',
    'Output Power',
    'Normal Operation'
]

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

    # Check if any column named 'id' exists, case-insensitive
    if "id" not in (c.lower() for c in df.columns):
        df["ID"] = "T1"

    return df


def parse_contents_to_html(contents, filename, prefilled_farm_dash_table = None):
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
        html.H5("Select the optional columns:", style={'fontWeight': 'bold', })
    )

    dropdowns.append(
        dbc.Accordion([
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

            
        ],
            id="accordion-advanced-options",
            active_item=None  # Aucun ouvert par défaut
        )
    )

    # Retourne le bloc complet : nom du fichier + tableau + mapping + bouton
    return html.Div([
        
        # Table header container
        html.Div(id='selected-turbine-csv-head-container', children=[table]),

        html.H4(
            "Step 1.2. Map the columns' names/units or Load settings.json",
            className="my-4 text-center",               
            style={'font-weight': 'bold', 'text-decoration': 'underline'}
        ),

        dbc.Row([
            dbc.Col(
                dcc.Upload(
                    id="settings-upload",
                    children=dmc.Button(
                        "Load settings.json",
                        id="load-settings-btn",
                        # color="secondary",
                        # outline=True,
                    ),
                    accept=".json",
                    multiple=False,
                ),
                width="auto",
                className="me-2"
            ),
            ],
            justify="center",
            className="my-3"
        ),

      

        html.H5(html.Span("Select the corresponding columns: ", style={'fontWeight': 'bold',})),
        dbc.Row(dropdowns, className="mt-4"),  # Menus dropdown pour associer les colonnes

        # Ligne d'alerte
        dbc.Alert(id='missing-columns-alert', color='danger', is_open=False),

        
        dmc.Space(h=10),
        # Add optional columns
        html.H5(html.Span("Select the corresponding parameters: ",
                          style={'fontWeight': 'bold',})),
        # Zone des paramètres supplémentaires
        dbc.Accordion([
            # --- Bloc 1 : Turbine Information ---
            dbc.AccordionItem(
                children=[
                    html.Div(
                        id="farm-csv-table-container", 
                        children=[prefilled_farm_dash_table] if prefilled_farm_dash_table is not None else []
                    ),
                    dbc.Row([
                        
                    ], justify='center', className="mb-4"),
                    dbc.Row([
                        dbc.Col(
                            dbc.Button("Download Wind Farm.csv", id='download-farm-info-btn', color="secondary", type="button"),
                            width="auto"
                        ),

                        dbc.Col([
                            dcc.Upload(
                                id='farm-csv-upload',
                                children=dbc.Button("Load Farm Data", id="load-wind-farm-info-btn", color="secondary"),
                                accept='.csv',
                                multiple=False,
                                style={'cursor': 'pointer'}
                            ),
                        ], width="auto"),
                    ],
                        justify='start',
                        className="my-3"
                    ),

                    
                ],
                title=html.Span("Wind Farm information", style={'textDecoration': 'underline'}),
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


        html.H4(
              "Step 1.3. Generate the Cleaned Dataset",
              className="my-4 text-center",               
              style={'font-weight': 'bold', 'text-decoration': 'underline'}
        ),

        dbc.Row([
            dbc.Col(
                dbc.Button(
                    "Download settings.json",
                    id="download-json-btn",
                    color="secondary",
                    outline=True,
                    type="button"
                ),
                width="auto"
            ),
            dbc.Col(
                dbc.Button("Generate Clean Dataset", id='download-clean-files-btn', color="primary"),
                width="auto"
            ),
            ],
            justify="center",
            className="mt-3"
        ),

        html.Div(style={'height': '20px'}),


        
    ])


def build_farm_table_from_timeseries_uploads(
    file_contents: list[str],
    file_names: list[str],
):
    rows = []

    for contents, filename in zip(file_contents, file_names):
        df = parse_contents_into_df(contents, filename)

        if "ID" not in df.columns:
            raise ValueError(f"File {filename} does not contain an 'ID' column")

        unique_ids = df["ID"].dropna().unique()

        for uid in unique_ids:
            rows.append(
                {
                    "file_name": filename,
                    "turbine_name": uid,
                    "rated_power": None,
                    "hub_height": None,
                    "elevation": None,
                }
            )

    table_df = pd.DataFrame(
        rows,
        columns=[
            "file_name",
            "turbine_name",
            "rated_power",
            "hub_height",
            "elevation",
        ],
    )

    return dash_table.DataTable(
        id="farm-csv-editable-table",
        data=table_df.to_dict("records"),
        columns=[
            {"name": "File name", "id": "file_name", "editable": False},
            {"name": "Turbine ID", "id": "turbine_name", "editable": False},
            {"name": "Rated power (kW)", "id": "rated_power", "editable": True},
            {"name": "Hub height (m)", "id": "hub_height", "editable": True},
            {"name": "Elevation (m)", "id": "elevation", "editable": True},
        ],
        editable=True,
        row_deletable=False,
        sort_action="native",
        filter_action="native",
        page_action="native",
        page_size=12,
        style_table={"overflowX": "auto"},
        style_cell={
            "textAlign": "left",
            "padding": "6px",
            "whiteSpace": "normal",
            "height": "auto",
        },
        style_header={"fontWeight": "bold"},
    )
