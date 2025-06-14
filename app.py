import os
import psycopg2 # New import for PostgreSQL
import psycopg2.extras # To fetch rows as dictionaries
from flask import Flask, request, jsonify, g, send_from_directory
from flask_cors import CORS
from urllib.parse import urlparse # New import to parse the database URL

app = Flask(__name__)
CORS(app, origins=["https://cryobullzststs.pages.dev"])

# Remove the old DATABASE = os.path.join(os.getcwd(), 'cryo_bullz.db') line

def get_db_connection():
    if 'db' not in g:
        # Get the database URL from environment variables
        DATABASE_URL = os.environ.get('DATABASE_URL')
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL environment variable not set.")

        # Parse the URL and connect
        url = urlparse(DATABASE_URL)
        g.db = psycopg2.connect(
            host=url.hostname,
            port=url.port,
            database=url.path[1:],  # Remove leading slash
            user=url.username,
            password=url.password,
            sslmode='require' # Required for Render PostgreSQL connections
        )
        # Use RealDictCursor to fetch rows as dictionaries, similar to sqlite3.Row
        g.db.cursor_factory = psycopg2.extras.RealDictCursor
    return g.db

def close_db_connection(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    conn = get_db_connection()
    # Use a regular cursor for DDL statements (CREATE TABLE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id SERIAL PRIMARY KEY, -- Changed from INTEGER PRIMARY KEY AUTOINCREMENT
            name TEXT NOT NULL UNIQUE,
            role TEXT,
            batting_style TEXT,
            bowling_style TEXT
        );
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS matches (
            id SERIAL PRIMARY KEY, -- Changed from INTEGER PRIMARY KEY AUTOINCREMENT
            player_id INTEGER NOT NULL,
            did_bat BOOLEAN NOT NULL,
            runs INTEGER NOT NULL DEFAULT 0,
            balls INTEGER NOT NULL DEFAULT 0,
            wickets INTEGER NOT NULL DEFAULT 0,
            runs_conceded INTEGER NOT NULL DEFAULT 0,
            overs_bowled REAL NOT NULL DEFAULT 0.0,
            date TEXT NOT NULL,
            match_type TEXT NOT NULL,
            FOREIGN KEY (player_id) REFERENCES players (id) ON DELETE CASCADE
        );
    ''')
    # Add a simple 'admin' user for login
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        );
    ''')
    # Check if admin user already exists before inserting
    cursor.execute("SELECT id FROM users WHERE username = 'admin';")
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO users (username, password) VALUES ('admin', 'admin');")
    conn.commit()
    cursor.close() # Close the cursor after use

# --- IMPORTANT: Update your existing API routes ---
# You need to change parameter placeholders from '?' to '%s' for all SQL queries.
# Also, ensure you are always using a cursor for execute calls.

# Example for /players POST route:
@app.route('/players', methods=['POST'])
def add_player():
    conn = get_db_connection()
    cursor = conn.cursor() # Create a cursor
    try:
        player_data = request.json
        name = player_data['name']
        role = player_data.get('role')
        batting_style = player_data.get('batting_style')
        bowling_style = player_data.get('bowling_style')

        cursor.execute(
            "INSERT INTO players (name, role, batting_style, bowling_style) VALUES (%s, %s, %s, %s) RETURNING id;", # %s placeholders
            (name, role, batting_style, bowling_style)
        )
        player_id = cursor.fetchone()[0] # Get the returned ID
        conn.commit()

        new_player_data = {
            "id": player_id,
            "name": name,
            "role": role,
            "batting_style": batting_style,
            "bowling_style": bowling_style
        }
        return jsonify(new_player_data), 201
    except psycopg2.errors.UniqueViolation as e: # Catch specific unique violation error
        conn.rollback()
        print(f"Error adding player: {e}")
        return jsonify({"error": f"Failed to add player: Name already exists. {e}"}), 409 # 409 Conflict for duplicates
    except Exception as e:
        conn.rollback()
        print(f"Error adding player: {e}")
        return jsonify({"error": f"Failed to add player: {e}"}), 500
    finally:
        cursor.close() # Close cursor in finally block

# Example for /players GET route:
@app.route('/players', methods=['GET'])
def get_players():
    conn = get_db_connection()
    cursor = conn.cursor() # Create a cursor
    try:
        # Fetch players, also fetch their matches
        cursor.execute('''
            SELECT p.*,
                   json_agg(
                       json_build_object(
                           'id', m.id,
                           'player_id', m.player_id,
                           'did_bat', m.did_bat,
                           'runs', m.runs,
                           'balls', m.balls,
                           'wickets', m.wickets,
                           'runs_conceded', m.runs_conceded,
                           'overs_bowled', m.overs_bowled,
                           'date', m.date,
                           'match_type', m.match_type
                       )
                   ) AS matches
            FROM players p
            LEFT JOIN matches m ON p.id = m.player_id
            GROUP BY p.id
            ORDER BY p.name;
        ''')
        players_data = cursor.fetchall()
        # Handle cases where json_agg returns null for players with no matches
        for player in players_data:
            if player['matches'] == [None]: # if no matches, json_agg might return [None]
                player['matches'] = []

        return jsonify(players_data), 200
    except Exception as e:
        print(f"Error fetching players: {e}")
        return jsonify({"error": f"Failed to fetch players: {e}"}), 500
    finally:
        cursor.close() # Close cursor

# You will need to apply similar changes to ALL your other routes (GET, PUT, DELETE for players and matches, and login)
# Always use cursor = conn.cursor() and cursor.execute() for your queries
# Change '?' placeholders to '%s'
# Make sure to close cursor in a finally block or after use
# For fetching single row, use cursor.fetchone()
# For fetching multiple rows, use cursor.fetchall()
# For commits and rollbacks, use conn.commit() and conn.rollback()
