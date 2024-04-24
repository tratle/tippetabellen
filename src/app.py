import dash
from dash import html, dcc, dash_table
import pandas as pd
import requests
from bs4 import BeautifulSoup
import pandas as pd
import plotly.graph_objects as go
import io

# Dash app
app = dash.Dash(__name__)
server = app.server

# Initialize df and df_friends as empty DataFrames
url = 'https://www.nifs.no/tabell.php?countryId=1&tournamentId=5&stageId=694961'
page = requests.get(url)
soup = BeautifulSoup(page.content, 'html.parser')
table = soup.find_all('table')[0]

# Creating a pandas dataframe from the table
df = pd.read_html(io.StringIO(str(table)))[0]

# Rename some columns
df = df.rename(columns={"Unnamed: 1": 'Lag', "Unnamed: 6": 'For', "Unnamed: 7": '_', "Unnamed: 8" : 'Imot'})
# Rename some team names
df['Lag'] = df['Lag'].replace({"KFUM Oslo": 'KFUM', "Sarpsborg 08": 'Sarpsborg_08'})

# Remove 'Form' column
df = df.drop(columns=['Form'])

# Import the predictions of the final table from 'Tipps.xlsx'
friends = pd.read_excel(r"C:\Users\tosol\OneDrive - Forsvarets forskningsinstitutt\Vscode\Tippetabell_ny\Tipps.xlsx")

# Create a dataframe from the predictions
df_friends = pd.DataFrame(friends)

# make the column 'Lag' the index in both df and df_friends
df = df.set_index('Lag')
df_friends = df_friends.set_index('Lag')

# Merge the two dataframes
df = df.merge(df_friends, left_index=True, right_index=True)

# The leaderboard of the predictions is the sum of the absolute difference between the 'Plassering' and each friend's predictions, assuming the 'Lag' column is the index in both df and df_friends
df_score = pd.DataFrame()
df_score['Are'] = abs(df['Nr'] - df['Are'])
df_score['Doffy'] = abs(df['Nr'] - df['Doffy'])
df_score['Hallvard'] = abs(df['Nr'] - df['Hallvard'])
df_score['Rune'] = abs(df['Nr'] - df['Rune'])
df_score['SteinErik'] = abs(df['Nr'] - df['SteinErik'])
df_score['Tommy'] = abs(df['Nr'] - df['Tommy'])
df_score['Tor_Atle'] = abs(df['Nr'] - df['Tor_Atle'])

# Sum the scores
df_score = 136 - df_score.sum()

# reset the index in df and df_friends
df = df.reset_index()
df_friends = df_friends.reset_index()

# Convert df_score to a DataFrame
df_score = df_score.to_frame().reset_index()

# Rename the columns
df_score.columns = ['Name', 'Score']

# Sort df_score in descending order based on 'Score'
df_score = df_score.sort_values('Score', ascending=False)

# Add a 'Rank' column
df_score['Rank'] = df_score['Score'].rank(ascending=True).astype(int)

# Create a bar chart
fig = go.Figure(data=[
    go.Bar(
        x=df_score.Name,
        y=df_score.Rank,
    )
    
])

# Add a title and labels
fig.update_layout(
    title="Ledertavla",
    xaxis_title="Tabelltippere",
    yaxis_title="Score",
    barcornerradius=15,
)

# Color the bars as a function of the rank
colors = []

for i in range(len(df_score)):
    if df_score['Rank'].iloc[i] == 7:
        colors.append('gold')
    elif df_score['Rank'].iloc[i] == 6:
        colors.append('silver')
    elif df_score['Rank'].iloc[i] == 5:
        colors.append('brown')
    else:
        colors.append('blue')
        
# Update the colors
fig.update_traces(marker_color=colors)

# Dash layout
app.layout = html.Div([
    dash_table.DataTable(
        id='table',
        columns=[{"name": i, "id": i} for i in df.columns],
        data=df.to_dict('records'),
        style_cell={'whiteSpace': 'normal', 'height': 'auto'},  
    ),

    dcc.Graph(
        id='graph',
        figure=fig
    )
])



if __name__ == '__main__':
    app.run_server(debug=True)

