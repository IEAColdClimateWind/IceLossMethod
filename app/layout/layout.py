import dash_bootstrap_components as dbc     
import dash_mantine_components as dmc       
from dash import dcc, html                   

import pandas as pd
import base64
import io
import csv

navbar = dbc.NavbarSimple(
    children=[
        dbc.DropdownMenu(
            children=[
                # dbc.DropdownMenuItem("About Us", disabled=True),
                dbc.DropdownMenuItem(
                    "Github",
                    href='https://github.com/IEAColdClimateWind/IceLossMethod',
                    # href='https://github.com/IEAWind-Task19/T19IceLossMethod',
                    target='_blank'
                ),
            ],
            nav=True,
            in_navbar=True,
            label="Options",  
        ),
    ],
    brand="Ice Loss Method 3.0",              
    color="primary",            
    dark=True                   
)



layout = dmc.MantineProvider(children=[
    navbar,
    html.H3(
        "Welcome To Your Ice Loss Assesment Tool!",
        className="my-5 text-center",
        style={'font-weight': 'bold'}
    ),
    dmc.Stepper(
        id="stepper",
        active=0,
        className='mx-3 mt-4 mb-4',
        children=[
            # Step 1
            dmc.StepperStep(
                # label="Upload and process data",
                label="Step 1",
                description="Upload and Process Data",
                children=[
                    html.H4(
                        "Step 1.1. Upload Data",
                        className="my-4 text-center",               
                        style={'font-weight': 'bold', 'text-decoration': 'underline'}
                    ),
                    dbc.Row([
                        dbc.Col(
                            dcc.Upload(
                                id='upload-data',
                                children=html.Div([
                                    'Drag & Drop or ',
                                    html.A('Browse', style={'textDecoration': 'underline'}),
                                    ' csv files.'
                                ]),
                                style={
                                    'height': '100px',
                                    'lineHeight': '100px',
                                    'borderWidth': '1px',
                                    'borderStyle': 'dashed',
                                    'borderRadius': '20px',
                                    'textAlign': 'center',
                                    'background-color': '#f9f9f9'
                                },
                                multiple=True  
                            ),
                            width={"size": 6, "offset": 3}, 
                        ),
                    ],
                    class_name='mt-2'
                    ),
                    html.Div(id='uploaded-data-output'),
                ]
            ),
            dmc.StepperStep(
                # label="Compute Reference Power Curve",
                label="Step 2",
                description="Compute Reference Power Curve",
                children=[
                    # dbc.Row([
                    #     dbc.Col(
                    #         dbc.Checklist(
                    #             options=[{
                    #                 "label": "Use temperature corrections",
                    #                 "value": "use_temp_correction",
                    #             }],
                    #             value=[],
                    #             id="temp-correction-checklist",
                    #             switch=False,
                    #         ),
                    #         width="auto",
                    #         className="me-5",  # real breathing room
                    #     ),
                    #     dbc.Col(
                    #         dbc.RadioItems(
                    #             options=[
                    #                 {
                    #                     "label": "Use full dataset",
                    #                     "value": "full_dataset",
                    #                 },
                    #                 {
                    #                     "label": "Reference power curve",
                    #                     "value": "reference_curve",
                    #                 },
                    #             ],
                    #             value="full_dataset",
                    #             id="dataset-selection-radio",
                    #         ),
                    #         width="auto",
                    #     ),
                    # ],
                    #     justify="center",
                    #     className="my-3",
                    # ),

                     html.H4(
                        "Step 2.1. Import or Filter Points Out of Reference Power Curve",
                        className="mt-4 text-center",               
                        style={'font-weight': 'bold', 'text-decoration': 'underline'}
                    ),
                   
                    dcc.Graph(id='time-series-graph'),

                    html.Div(id='currently-selected-points-container-div'),
                    html.Div(id='all-points-to-filter-out-ref-pc-store-div'),

                    dmc.Group(
                        justify="center",
                        mt='xs',
                        children=[
                            dcc.Upload(
                                id='ref-pc-upload',
                                children=dbc.Button(
                                    'Import Custom Reference Power Curve',
                                    id='import-ref-pc', 
                                    color="secondary",
                                    outline=True,
                                    type="button"
                                ),
                                accept='.json',
                                multiple=False,
                                style={'cursor': 'pointer'}
                            ),
                            dmc.Button('Generate Reference Power Curve', id='generate-ref-pc', 
                                     #  color='green'
                                       ),
                            
                        ],
                    ),

                    dcc.Graph(id='reference-power-curve-graph'),
                    
                   
                    dmc.Group(
                        justify="center",
                        mt='xs',
                        children=[
                            dmc.Button('Download Generated Reference Power Curve', id='dl-ref-pc', 
                                     #  color='green'
                                       ),
                            
                        ],
                    ),

                    html.H4(
                        "Step 2.2. Filter Out Unwanted Data",
                        className="my-4 text-center",               
                        style={'font-weight': 'bold', 'text-decoration': 'underline'}
                    ),

                    
                ],
            ),
            dmc.StepperStep(
                # label="Compute Ice Losses",
                label="Step 3",
                description="Compute Ice Losses",
                children=[
                     html.H4(
                        "Step 3.1. Filter Icing Losses Dataset & Compute Losses Statistics",
                        className="my-4 text-center",               
                        style={'font-weight': 'bold', 'text-decoration': 'underline'}
                    ),
                     dmc.Group(
                        justify="center",
                        mt='xs',
                        children=[
                            dmc.Button('Compute Icing Losses Power Curve', 
                                id='compute-icing-losses-btn', 
                                color='green'
                            ),
                        ],
                    ),
                    
                    dcc.Graph(id='icing-losses-power-curve-graph'),
                    html.Div(id='currently-selected-points-icing-pc-container-div'),
                    html.Div(id='all-points-to-filter-out-icing-pc-store-div'),
                    html.Div(id='farm-stats'),
                    
                ],
            ),
        ],
    ),
    dmc.Group(
        justify="center",
        mt="xl",
        children=[
            dmc.Button("Back", id="stepper-back-btn", variant="default"),
            dmc.Button("Next step", id="stepper-next-btn"),
        ],
    ),
    dmc.Space(h=20),

    dcc.Download(id="data-to-download"),
    dcc.Download(id="json-download"),
    dcc.Download(id="settings-download"),
    dcc.Download(id="farm-data-download"),
    dcc.Upload(id="settings-upload", style={"display": "none"}),

    dcc.Store(id='intermediate-json-config'),
    dcc.Store(id="cleaned-files-store", storage_type="memory"),

    dcc.Store(id="points-to-filter-out-ref-pc-store", storage_type="memory", data=[]),
    dcc.Store(id="last-selected-points-ref-pc-store", data=None),

    dcc.Store(id="points-to-filter-out-icing-pc-store", storage_type="memory", data=[]),
    dcc.Store(id="last-selected-points-icing-pc-store", data=None),
    
])




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

