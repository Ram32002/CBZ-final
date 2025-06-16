import os
import json
from flask import Flask, request, jsonify, g, send_from_directory
from flask_cors import CORS
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

app = Flask(__name__)
# Configure CORS to allow requests specifically from your Cloudflare Pages domain
# This has been updated with the domain confirmed from your screenshot.
CORS(app, origins=["https://cryobullzststs.pages.dev"])

# --- Google Sheets API Configuration ---
# Path to your service account key file
# IMPORTANT: Ensure this file is in the same directory as app.py
SERVICE_ACCOUNT_FILE = 'service_account.json'
# API scopes required for reading and writing to Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Your Google Sheet ID - This has been updated with the ID you provided.
SPREADSHEET_ID = '1dA0WEi2upLDYpGy8xkQo9_SQsj672BaRa40iUytqQu8' 

# Sheet names within your Google Spreadsheet (these must exactly match your tab names)
PLAYERS_SHEET_NAME = 'Players'
MATCHES_SHEET_NAME = 'Matches'

def get_sheets_service():
    """
    Initializes and returns a Google Sheets API service object.
    Authenticates using the service account credentials.
    """
    creds = None
    try:
        # Load credentials from the service account JSON file
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    except Exception as e:
        # Print error if credentials cannot be loaded (e.g., file not found, invalid format)
        print(f"Error loading service account credentials: {e}")
        raise # Re-raise the exception to stop app startup if critical files are missing

    try:
        # Build the Sheets API service client
        service = build('sheets', 'v4', credentials=creds)
        # Corrected service call: it should be .spreadsheets() for the top-level Sheets service
        # .sheets() is not a valid method on the discovery object.
        return service.spreadsheets() 
    except HttpError as err:
        # Handle HTTP errors from Google API (e.g., permissions, sheet not found)
        print(f"Error building Sheets API service: {err}")
        raise # Re-raise to indicate a critical setup issue

# A simple in-memory cache to reduce frequent API calls to Google Sheets.
# For production, consider more robust caching or direct row updates if data is very large.
# This cache will be reloaded after every write operation to ensure consistency.
_cached_data = {
    'players': [],
    'matches': [],
    'next_player_id': 1, # Tracks the next available player ID for new entries
    'next_match_id': 1   # Tracks the next available match ID for new entries
}

def load_data_from_sheets():
    """
    Loads all player and match data from Google Sheets into the in-memory cache (_cached_data).
    This function is called on application startup and after any write operation to ensure data freshness.
    """
    global _cached_data
    try:
        service = get_sheets_service()

        # --- Load Players Data ---
        # Define the range to fetch from the Players sheet (A to Z columns for flexibility)
        players_range = f'{PLAYERS_SHEET_NAME}!A:Z'
        # Execute the GET request to retrieve player values
        players_result = service.values().get(
            spreadsheetId=SPREADSHEET_ID, range=players_range).execute()
        # Get the list of lists representing rows and columns
        player_values = players_result.get('values', [])
        
        # Process player data: Assume the first row is headers and subsequent rows are data
        if player_values and len(player_values) > 1:
            headers = [h.strip().lower().replace(' ', '_') for h in player_values[0]] # Normalize headers
            players_data = []
            max_player_id = 0
            for row in player_values[1:]: # Iterate through data rows (skip header)
                player = {}
                for i, header in enumerate(headers):
                    # Assign value, or empty string if column is missing in the row
                    player[header] = row[i] if i < len(row) else ''
                
                # Convert ID to integer and track the maximum ID to ensure unique new IDs
                try:
                    player['id'] = int(player.get('id', 0))
                    max_player_id = max(max_player_id, player['id'])
                except ValueError:
                    player['id'] = 0 # Default to 0 if ID is not a valid integer
                players_data.append(player)
            _cached_data['players'] = players_data
            _cached_data['next_player_id'] = max_player_id + 1
        else:
            # If no data or only headers, initialize players list and ID counter
            _cached_data['players'] = []
            _cached_data['next_player_id'] = 1

        # --- Load Matches Data ---
        # Define the range to fetch from the Matches sheet
        matches_range = f'{MATCHES_SHEET_NAME}!A:Z'
        # Execute the GET request to retrieve match values
        matches_result = service.values().get(
            spreadsheetId=SPREADSHEET_ID, range=matches_range).execute()
        # Get the list of lists representing rows and columns
        match_values = matches_result.get('values', [])

        # Process match data, similar to players
        if match_values and len(match_values) > 1:
            headers = [h.strip().lower().replace(' ', '_') for h in match_values[0]] # Normalize headers
            matches_data = []
            max_match_id = 0
            for row in match_values[1:]: # Iterate through data rows
                match = {}
                for i, header in enumerate(headers):
                    val = row[i] if i < len(row) else ''
                    # Type conversion for specific fields
                    if header == 'did_bat':
                        match[header] = val.lower() == 'true' # Convert string "TRUE"/"FALSE" to boolean
                    elif header in ['runs', 'balls', 'wickets', 'conceded', 'catches', 'stumpings', 'run_outs', 'player_id', 'id']:
                        try:
                            match[header] = int(val) # Convert to integer
                        except ValueError:
                            match[header] = 0 # Default to 0 if not a valid integer
                    elif header == 'overs':
                        try:
                            match[header] = float(val) # Convert to float for overs (e.g., 4.2)
                        except ValueError:
                            match[header] = 0.0 # Default to 0.0 if not a valid float
                    else:
                        match[header] = val
                
                # Track maximum match ID
                try:
                    max_match_id = max(max_match_id, match.get('id', 0))
                except ValueError:
                    pass # Ignore if ID is not convertable to int

                matches_data.append(match)
            _cached_data['matches'] = matches_data
            _cached_data['next_match_id'] = max_match_id + 1
        else:
            # If no data or only headers, initialize matches list and ID counter
            _cached_data['matches'] = []
            _cached_data['next_match_id'] = 1

        print("Data loaded from Google Sheets successfully.")

    except HttpError as err:
        # Catch specific API errors from Google (e.g., sheet not found, permission denied)
        print(f"An HTTP error occurred loading data from Google Sheets: {err}")
        print("Please ensure the spreadsheet ID and sheet names are correct and the service account has access.")
        # Clear cache to prevent serving stale or incorrect data if loading fails
        _cached_data['players'] = []
        _cached_data['matches'] = []
        _cached_data['next_player_id'] = 1
        _cached_data['next_match_id'] = 1
    except Exception as e:
        # Catch any other unexpected errors during data loading
        print(f"An unexpected error occurred during data loading: {e}")
        _cached_data['players'] = []
        _cached_data['matches'] = []
        _cached_data['next_player_id'] = 1
        _cached_data['next_match_id'] = 1


def update_sheet(sheet_name, values):
    """
    Updates an entire Google Sheet with the given values.
    This method overwrites all data in the specified sheet starting from cell A1.
    """
    try:
        service = get_sheets_service()
        body = {'values': values} # The data to write
        range_name = f'{sheet_name}!A1' # Target range to update
        
        # Execute the UPDATE request
        result = service.values().update(
            spreadsheetId=SPREADSHEET_ID, range=range_name,
            valueInputOption='RAW', # 'RAW' means values are inserted as-is without parsing
            body=body).execute()
        print(f"{result.get('updatedCells')} cells updated in {sheet_name}.")
    except HttpError as err:
        # Handle API specific errors during update
        print(f"Error updating sheet {sheet_name}: {err}")
        raise # Re-raise to be caught by calling functions
    except Exception as e:
        # Handle general errors during update
        print(f"An unexpected error occurred during sheet update for {sheet_name}: {e}")
        raise

# Initialize the database (load data from sheets) when the application context is ready
# This runs once on app startup
with app.app_context():
    load_data_from_sheets()

# Route to serve the index.html file.
# Assumes index.html is in a 'static' folder relative to app.py.
# If your frontend is hosted separately (e.g., Cloudflare Pages), this route might not be strictly necessary
# for production, but it's useful for local testing or if Flask serves the frontend.
@app.route('/')
def serve_index():
    # It's good practice to place your HTML, CSS, JS in a 'static' folder.
    # In a real-world scenario with Cloudflare Pages, this HTML would be served directly by Cloudflare,
    # and this Flask route would only be hit for API calls.
    return send_from_directory('static', 'index.html')

# Basic route to confirm the backend is running and accessible
@app.route('/api_status')
def api_status():
    return jsonify({"status": "Cryo Bullz Backend is running (Google Sheets backend)!"})


@app.route('/players', methods=['GET', 'POST'])
def handle_players():
    """
    Handles GET requests to retrieve all players and POST requests to add a new player.
    """
    global _cached_data # Access the global cache

    if request.method == 'GET':
        players_list = []
        for player in _cached_data['players']:
            player_data = player.copy() # Create a copy to avoid modifying cached data directly
            # Attach matches relevant to this player from the cache
            player_data['matches'] = [
                m for m in _cached_data['matches'] if m['player_id'] == player['id']
            ]
            players_list.append(player_data)
        return jsonify(players_list)

    elif request.method == 'POST':
        data = request.json
        name = data.get('name')
        role = data.get('role', '')
        batting_style = data.get('batting_style', '')
        bowling_style = data.get('bowling_style', '')

        if not name:
            return jsonify({"error": "Player name is required"}), 400

        # Check for existing player name to prevent duplicates
        if any(p['name'].lower() == name.lower() for p in _cached_data['players']):
            return jsonify({"error": "Player with this name already exists"}), 409

        new_player_id = _cached_data['next_player_id'] # Get the next available ID
        new_player = {
            'id': new_player_id,
            'name': name,
            'role': role,
            'batting_style': batting_style,
            'bowling_style': bowling_style
        }

        _cached_data['players'].append(new_player) # Add new player to cache
        _cached_data['next_player_id'] += 1 # Increment next ID

        # Prepare data for Google Sheet update
        # The first row contains headers
        player_sheet_values = [['ID', 'Name', 'Role', 'Batting Style', 'Bowling Style']]
        # Add all cached players as rows
        for p in _cached_data['players']:
            player_sheet_values.append([
                p['id'], p['name'], p['role'], p['batting_style'], p['bowling_style']
            ])

        try:
            update_sheet(PLAYERS_SHEET_NAME, player_sheet_values) # Write updated players data to Google Sheet
            load_data_from_sheets() # Reload data to ensure cache is consistent with the sheet
            return jsonify({
                "id": new_player_id,
                "name": name,
                "role": role,
                "batting_style": batting_style,
                "bowling_style": bowling_style,
                "matches": [] # New players have no matches initially
            }), 201
        except Exception as e:
            # If sheet update fails, revert changes in local cache
            _cached_data['players'].remove(new_player)
            _cached_data['next_player_id'] -= 1
            print(f"Error adding player to Google Sheet: {e}")
            return jsonify({"error": f"Failed to add player: {e}"}), 500


@app.route('/players/<int:player_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_player(player_id):
    """
    Handles GET, PUT, and DELETE requests for a specific player by ID.
    """
    global _cached_data

    # Find the player in the cache
    player = next((p for p in _cached_data['players'] if p['id'] == player_id), None)
    if not player:
        return jsonify({"message": "Player not found"}), 404

    if request.method == 'GET':
        player_data = player.copy()
        # Attach matches relevant to this player from the cache
        player_data['matches'] = [
            m for m in _cached_data['matches'] if m['player_id'] == player_id
        ]
        return jsonify(player_data)

    elif request.method == 'PUT':
        data = request.json
        # Get fields to update, defaulting to current values if not provided
        name = data.get('name', player['name'])
        role = data.get('role', player['role'])
        batting_style = data.get('batting_style', player['batting_style'])
        bowling_style = data.get('bowling_style', player['bowling_style'])

        # Check for duplicate name if name is being changed
        if name.lower() != player['name'].lower() and any(p['name'].lower() == name.lower() for p in _cached_data['players'] if p['id'] != player_id):
            return jsonify({"error": "Player with this name already exists"}), 409

        # Update cached player data
        player['name'] = name
        player['role'] = role
        player['batting_style'] = batting_style
        player['bowling_style'] = bowling_style

        # Prepare data for Google Sheet update
        player_sheet_values = [['ID', 'Name', 'Role', 'Batting Style', 'Bowling Style']]
        for p in _cached_data['players']:
            player_sheet_values.append([
                p['id'], p['name'], p['role'], p['batting_style'], p['bowling_style']
            ])

        try:
            update_sheet(PLAYERS_SHEET_NAME, player_sheet_values) # Write updated player data
            load_data_from_sheets() # Reload data to ensure cache is consistent
            return jsonify({"message": "Player updated successfully"}), 200
        except Exception as e:
            print(f"Error updating player in Google Sheet: {e}")
            return jsonify({"error": f"Failed to update player: {e}"}), 500

    elif request.method == 'DELETE':
        # Temporarily store old data for potential rollback
        original_players = list(_cached_data['players'])
        original_matches = list(_cached_data['matches'])

        # Remove player from cache
        _cached_data['players'] = [p for p in _cached_data['players'] if p['id'] != player_id]
        # Remove associated matches from cache
        _cached_data['matches'] = [m for m in _cached_data['matches'] if m['player_id'] != player_id]

        # Prepare data for Google Sheets update
        player_sheet_values = [['ID', 'Name', 'Role', 'Batting Style', 'Bowling Style']]
        for p in _cached_data['players']:
            player_sheet_values.append([
                p['id'], p['name'], p['role'], p['batting_style'], p['bowling_style']
            ])

        match_sheet_values = [['ID', 'Player ID', 'Did Bat', 'Runs', 'Balls', 'Wickets', 'Overs', 'Conceded', 'Catches', 'Stumpings', 'Run Outs']]
        for m in _cached_data['matches']:
            match_sheet_values.append([
                m['id'], m['player_id'], str(m['did_bat']), m['runs'], m['balls'], m['wickets'],
                m['overs'], m['conceded'], m['catches'], m['stumpings'], m['run_outs']
            ])

        try:
            update_sheet(PLAYERS_SHEET_NAME, player_sheet_values) # Update players sheet
            update_sheet(MATCHES_SHEET_NAME, match_sheet_values) # Update matches sheet
            load_data_from_sheets() # Reload to confirm write and keep cache fresh
            return jsonify({"message": "Player and associated matches deleted successfully"}), 200
        except Exception as e:
            # If deletion fails, revert local cache changes
            _cached_data['players'] = original_players
            _cached_data['matches'] = original_matches
            print(f"Error deleting player and matches from Google Sheet: {e}")
            return jsonify({"error": f"Failed to delete player: {e}"}), 500


@app.route('/players/<int:player_id>/matches', methods=['POST'])
def add_match_to_player(player_id):
    """
    Handles POST requests to add a new match for a specific player.
    """
    global _cached_data
    data = request.json
    # Extract match data, providing default values
    did_bat = data.get('did_bat', False)
    runs = data.get('runs', 0)
    balls = data.get('balls', 0)
    wickets = data.get('wickets', 0)
    overs = data.get('overs', 0.0)
    conceded = data.get('conceded', 0)
    catches = data.get('catches', 0)
    stumpings = data.get('stumpings', 0)
    run_outs = data.get('run_outs', 0)

    # Check if player exists
    player_exists = any(p['id'] == player_id for p in _cached_data['players'])
    if not player_exists:
        return jsonify({"error": "Player not found"}), 404

    new_match_id = _cached_data['next_match_id'] # Get the next available ID
    new_match = {
        'id': new_match_id,
        'player_id': player_id,
        'did_bat': did_bat,
        'runs': runs,
        'balls': balls,
        'wickets': wickets,
        'overs': overs,
        'conceded': conceded,
        'catches': catches,
        'stumpings': stumpings,
        'run_outs': run_outs
    }

    _cached_data['matches'].append(new_match) # Add new match to cache
    _cached_data['next_match_id'] += 1 # Increment next ID

    # Prepare data for Google Sheet update
    match_sheet_values = [['ID', 'Player ID', 'Did Bat', 'Runs', 'Balls', 'Wickets', 'Overs', 'Conceded', 'Catches', 'Stumpings', 'Run Outs']]
    for m in _cached_data['matches']:
        match_sheet_values.append([
            m['id'], m['player_id'], str(m['did_bat']), m['runs'], m['balls'], m['wickets'],
            m['overs'], m['conceded'], m['catches'], m['stumpings'], m['run_outs']
        ])

    try:
        update_sheet(MATCHES_SHEET_NAME, match_sheet_values) # Write updated matches data
        load_data_from_sheets() # Reload to confirm write and keep cache fresh
        return jsonify(new_match), 201
    except Exception as e:
        # If sheet update fails, revert changes in local cache
        _cached_data['matches'].remove(new_match)
        _cached_data['next_match_id'] -= 1
        print(f"Error adding match to Google Sheet: {e}")
        return jsonify({"error": f"Failed to add match: {e}"}), 500


@app.route('/matches/<int:match_id>', methods=['PUT', 'DELETE'])
def handle_match(match_id):
    """
    Handles PUT and DELETE requests for a specific match by ID.
    """
    global _cached_data

    # Find the match in the cache
    match_index = -1
    for i, m in enumerate(_cached_data['matches']):
        if m['id'] == match_id:
            match_index = i
            break
            
    if match_index == -1:
        return jsonify({"message": "Match not found"}), 404

    current_match = _cached_data['matches'][match_index]

    if request.method == 'PUT':
        data = request.json
        # Update match fields with provided data, defaulting to current values if not present
        current_match['did_bat'] = data.get('did_bat', current_match['did_bat'])
        current_match['runs'] = data.get('runs', current_match['runs'])
        current_match['balls'] = data.get('balls', current_match['balls'])
        current_match['wickets'] = data.get('wickets', current_match['wickets'])
        current_match['overs'] = data.get('overs', current_match['overs'])
        current_match['conceded'] = data.get('conceded', current_match['conceded'])
        current_match['catches'] = data.get('catches', current_match['catches'])
        current_match['stumpings'] = data.get('stumpings', current_match['stumpings'])
        current_match['run_outs'] = data.get('run_outs', current_match['run_outs'])

        # Prepare data for Google Sheet update
        match_sheet_values = [['ID', 'Player ID', 'Did Bat', 'Runs', 'Balls', 'Wickets', 'Overs', 'Conceded', 'Catches', 'Stumpings', 'Run Outs']]
        for m in _cached_data['matches']:
            match_sheet_values.append([
                m['id'], m['player_id'], str(m['did_bat']), m['runs'], m['balls'], m['wickets'],
                m['overs'], m['conceded'], m['catches'], m['stumpings'], m['run_outs']
            ])

        try:
            update_sheet(MATCHES_SHEET_NAME, match_sheet_values) # Write updated match data
            load_data_from_sheets() # Reload to confirm write and keep cache fresh
            return jsonify(current_match), 200
        except Exception as e:
            print(f"Error updating match in Google Sheet: {e}")
            return jsonify({"error": f"Failed to update match: {e}"}), 500

    elif request.method == 'DELETE':
        # Temporarily store old data for potential rollback
        original_matches = list(_cached_data['matches'])

        # Remove match from cache
        _cached_data['matches'].pop(match_index)
        
        # Prepare data for Google Sheet update
        match_sheet_values = [['ID', 'Player ID', 'Did Bat', 'Runs', 'Balls', 'Wickets', 'Overs', 'Conceded', 'Catches', 'Stumpings', 'Run Outs']]
        for m in _cached_data['matches']:
            match_sheet_values.append([
                m['id'], m['player_id'], str(m['did_bat']), m['runs'], m['balls'], m['wickets'],
                m['overs'], m['conceded'], m['catches'], m['stumpings'], m['run_outs']
            ])

        try:
            update_sheet(MATCHES_SHEET_NAME, match_sheet_values) # Write updated matches data
            load_data_from_sheets() # Reload to confirm write and keep cache fresh
            return jsonify({"message": "Match deleted successfully"}), 200
        except Exception as e:
            # If deletion fails, revert local cache changes
            _cached_data['matches'] = original_matches
            print(f"Error deleting match from Google Sheet: {e}")
            return jsonify({"error": f"Failed to delete match: {e}"}), 500

if __name__ == '__main__':
    # Use environment variable PORT if available (common in cloud hosting), otherwise default to 5000
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

