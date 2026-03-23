from datetime import datetime
from pathlib import Path
import io
import socket

import dash
from dash import Input, Output, State, dcc, html, dash_table, ctx
from bs4 import BeautifulSoup
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests


NIFS_URL = "https://www.nifs.no/tabell.php?countryId=1&tournamentId=5&stageId=700911"



def find_predictions_file() -> Path:
    # Always resolve relative to this source file, regardless of cwd or how the app is launched.
    here = Path(__file__).resolve().parent
    candidates = [
        here / "Tipps.csv",
        here.parent / "Tipps.csv",
        here.parent / "src" / "Tipps.csv",
    ]
    for file_path in candidates:
        if file_path.exists():
            return file_path
    checked = [str(p) for p in candidates]
    raise FileNotFoundError(f"Could not find Tipps.csv. Checked: {checked}")


def load_predictions() -> pd.DataFrame:
    predictions = pd.read_csv(find_predictions_file(), encoding="latin1", sep=";")
    predictions["Lag"] = predictions["Lag"].astype(str).str.strip()

    for col in predictions.columns:
        if col != "Lag":
            predictions[col] = pd.to_numeric(predictions[col], errors="coerce")

    return predictions.dropna(subset=["Lag"])


def fetch_live_standings() -> pd.DataFrame:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(NIFS_URL, headers=headers, timeout=(4, 8))
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    table = soup.find("table")
    if table is None:
        raise ValueError("Could not find standings table in source page")

    standings = pd.read_html(io.StringIO(str(table)))[0]
    rename_map = {
        "Unnamed: 1": "Lag",
        "Unnamed: 6": "For",
        "Unnamed: 7": "_",
        "Unnamed: 8": "Imot",
    }
    standings = standings.rename(columns=rename_map)

    if "Lag" not in standings.columns and len(standings.columns) > 1:
        standings = standings.rename(columns={standings.columns[1]: "Lag"})
    if "Nr" not in standings.columns and len(standings.columns) > 0:
        standings = standings.rename(columns={standings.columns[0]: "Nr"})

    standings = standings.loc[:, [c for c in standings.columns if c != "Form"]]
    standings = standings.loc[:, ~standings.columns.astype(str).str.startswith("Unnamed")]

    standings["Lag"] = standings["Lag"].astype(str).str.strip()
    standings["Nr"] = pd.to_numeric(standings["Nr"], errors="coerce")
    standings = standings.dropna(subset=["Lag", "Nr"]).sort_values("Nr")
    standings["Nr"] = standings["Nr"].astype(int)

    return standings


def calculate_leaderboard(standings: pd.DataFrame, predictions: pd.DataFrame) -> pd.DataFrame:
    merged = standings[["Lag", "Nr"]].merge(predictions, on="Lag", how="inner")
    participant_columns = [col for col in predictions.columns if col != "Lag"]

    if merged.empty:
        raise ValueError("No overlapping teams between standings and predictions")
    if not participant_columns:
        raise ValueError("No participant columns found in Tipps.csv")

    total_error = {
        name: (merged["Nr"] - merged[name]).abs().sum()
        for name in participant_columns
    }
    leaderboard = pd.DataFrame(
        {
            "Name": list(total_error.keys()),
            "TotalError": list(total_error.values()),
        }
    ).sort_values(["TotalError", "Name"], ascending=[True, True])

    max_error = leaderboard["TotalError"].max()
    leaderboard["Score"] = max_error - leaderboard["TotalError"]
    leaderboard["Rank"] = leaderboard["TotalError"].rank(method="min", ascending=True).astype(int)

    return leaderboard


def create_figure(leaderboard: pd.DataFrame) -> go.Figure:
    fig = px.bar(
        leaderboard.sort_values("Score", ascending=True),
        x="Score",
        y="Name",
        orientation="h",
        color="Rank",
        color_continuous_scale=["#f7b267", "#f4845f", "#8ecae6", "#219ebc"],
        text="TotalError",
    )
    fig.update_traces(texttemplate="Error %{text}", textposition="outside")
    fig.update_layout(
        title="Leaderboard",
        xaxis_title="Points (higher is better)",
        yaxis_title="",
        coloraxis_showscale=False,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin={"l": 20, "r": 20, "t": 60, "b": 20},
    )
    return fig


def empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font={"size": 16, "color": "#334155"},
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
    )
    return fig


def find_open_port(start_port: int = 8050, end_port: int = 8100, host: str = "127.0.0.1") -> int:
    for port in range(start_port, end_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue
    raise OSError(f"No available port in range {start_port}-{end_port}")


def start_dash_app(host: str = "127.0.0.1", start_port: int = 8050, end_port: int = 8100) -> None:
    last_error = None
    for port in range(start_port, end_port + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((host, port))

            print(f"Starting Dash app on http://{host}:{port}")

            # Prefer run_server for widest Dash compatibility.
            app.run_server(debug=False, host=host, port=port, use_reloader=False)
            return
        except OSError as exc:
            last_error = exc
            continue
        except Exception as exc:
            print(f"Failed to start server on port {port}: {exc}")
            raise

    raise OSError(f"Unable to start web server on ports {start_port}-{end_port}: {last_error}")


app = dash.Dash(__name__)
app.title = "Tippetabellen"
server = app.server


app.layout = html.Div(
    style={
        "minHeight": "100vh",
        "background": "linear-gradient(135deg, #f7f3e9 0%, #cde7f0 45%, #f7c8a0 100%)",
        "padding": "24px",
        "fontFamily": "'Segoe UI', 'Trebuchet MS', sans-serif",
    },
    children=[
        html.Div(
            style={
                "maxWidth": "1100px",
                "margin": "0 auto",
                "backgroundColor": "rgba(255,255,255,0.85)",
                "backdropFilter": "blur(8px)",
                "borderRadius": "18px",
                "padding": "20px",
                "boxShadow": "0 16px 40px rgba(15, 23, 42, 0.15)",
            },
            children=[
                html.H1("Eliteserien Tippetabell", style={"margin": "0 0 8px 0", "color": "#0f172a"}),
                html.P(
                    "Live standings + prediction race, refreshed manually or automatically.",
                    style={"margin": "0 0 20px 0", "color": "#334155"},
                ),
                html.Div(
                    style={
                        "display": "flex",
                        "flexWrap": "wrap",
                        "gap": "12px",
                        "alignItems": "center",
                        "marginBottom": "14px",
                    },
                    children=[
                        html.Button(
                            "Refresh now",
                            id="update-button",
                            n_clicks=0,
                            style={
                                "backgroundColor": "#0f766e",
                                "color": "white",
                                "border": "none",
                                "padding": "10px 16px",
                                "borderRadius": "10px",
                                "fontWeight": "600",
                                "cursor": "pointer",
                            },
                        ),
                        dcc.Checklist(
                            id="auto-refresh",
                            options=[{"label": "Auto refresh", "value": "auto"}],
                            value=["auto"],
                            style={"color": "#0f172a"},
                        ),
                        dcc.Dropdown(
                            id="refresh-seconds",
                            options=[
                                {"label": "Every 60 sec", "value": 60},
                                {"label": "Every 120 sec", "value": 120},
                                {"label": "Every 300 sec", "value": 300},
                            ],
                            value=120,
                            clearable=False,
                            style={"width": "180px"},
                        ),
                        html.Div(id="status-text", style={"color": "#1e293b", "fontWeight": "600"}),
                        html.Div(id="updated-at", style={"color": "#475569"}),
                    ],
                ),
                dcc.Graph(id="graph", figure=empty_figure("Click 'Refresh now' to load data"), config={"displayModeBar": False}),
                dash_table.DataTable(
                    id="table",
                    data=[],
                    columns=[],
                    page_size=20,
                    sort_action="native",
                    style_table={"overflowX": "auto", "borderRadius": "12px"},
                    style_cell={
                        "padding": "10px",
                        "backgroundColor": "#f8fafc",
                        "color": "#0f172a",
                        "textAlign": "left",
                        "minWidth": "90px",
                        "width": "90px",
                        "maxWidth": "180px",
                    },
                    style_header={
                        "backgroundColor": "#0f172a",
                        "color": "#f8fafc",
                        "fontWeight": "700",
                    },
                ),
                dcc.Interval(id="refresh-interval", interval=120000, n_intervals=0, disabled=False),
            ],
        )
    ],
)


@app.callback(
    Output("refresh-interval", "disabled"),
    Output("refresh-interval", "interval"),
    Input("auto-refresh", "value"),
    Input("refresh-seconds", "value"),
)
def configure_auto_refresh(auto_refresh_value, refresh_seconds):
    enabled = "auto" in (auto_refresh_value or [])
    seconds = refresh_seconds if refresh_seconds else 120
    return (not enabled), int(seconds) * 1000


@app.callback(
    Output("table", "data"),
    Output("table", "columns"),
    Output("graph", "figure"),
    Output("status-text", "children"),
    Output("updated-at", "children"),
    Input("update-button", "n_clicks"),
    Input("refresh-interval", "n_intervals"),
    State("auto-refresh", "value"),
    prevent_initial_call=True,
)
def refresh_data(_n_clicks, _n_intervals, auto_refresh_value):
    try:
        standings = fetch_live_standings()
        predictions = load_predictions()
        merged_view = standings.merge(predictions, on="Lag", how="left")

        leaderboard = calculate_leaderboard(standings, predictions)
        figure = create_figure(leaderboard)

        trigger = ctx.triggered_id
        if trigger == "refresh-interval" and "auto" in (auto_refresh_value or []):
            status = "Auto refresh succeeded"
        elif trigger == "update-button":
            status = "Manual refresh succeeded"
        else:
            status = "Initial load succeeded"

        timestamp = datetime.now().strftime("Last updated %Y-%m-%d %H:%M:%S")
        columns = [{"name": col, "id": col} for col in merged_view.columns]
        return merged_view.to_dict("records"), columns, figure, status, timestamp
    except Exception as exc:
        timestamp = datetime.now().strftime("Attempted %Y-%m-%d %H:%M:%S")
        return [], [], empty_figure("Unable to load data right now"), f"Refresh failed: {exc}", timestamp


if __name__ == "__main__":
    try:
        start_dash_app()
    except OSError as exc:
        print(f"Unable to start web server: {exc}")

