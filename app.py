import os
import sqlite3
from flask import Flask, request, jsonify, g, send_from_directory # send_from_directory is new import
from flask_cors import CORS

app = Flask(__name__)
CORS(app) # Enable CORS for all origins (for local development)

DATABASE = os.path.join(os.getcwd(), 'cryo_bullz.db')

def get_db_connection():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db_connection(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            role TEXT,
            batting_style TEXT,
            bowling_style TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            did_bat BOOLEAN NOT NULL,
            runs INTEGER NOT NULL DEFAULT 0,
            balls INTEGER NOT NULL DEFAULT 0,
            wickets INTEGER NOT NULL DEFAULT 0,
            overs REAL NOT NULL DEFAULT 0.0,
            conceded INTEGER NOT NULL DEFAULT 0,
            catches INTEGER NOT NULL DEFAULT 0,
            stumpings INTEGER NOT NULL DEFAULT 0,
            run_outs INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (player_id) REFERENCES players (id) ON DELETE CASCADE
        )
    ''')
    conn.commit()
    print("Database initialized or already exists.")

app.teardown_appcontext(close_db_connection)

# Serve the index.html file from the 'static' folder
@app.route('/')
def serve_index():
    return send_from_directory('static', 'index.html')

# Basic route to confirm backend is running (optional, but good for testing)
@app.route('/api_status')
def api_status():
    return jsonify({"status": "Cryo Bullz Backend is running!"})


@app.route('/players', methods=['GET', 'POST'])
def handle_players():
    conn = get_db_connection()
    if request.method == 'GET':
        players_cursor = conn.execute('SELECT * FROM players ORDER BY id').fetchall()
        players_list = []
        for player_row in players_cursor:
            player_data = dict(player_row)
            matches_cursor = conn.execute('SELECT * FROM matches WHERE player_id = ? ORDER BY id', (player_data['id'],)).fetchall()
            player_data['matches'] = [dict(m) for m in matches_cursor]
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

        try:
            cursor = conn.execute(
                "INSERT INTO players (name, role, batting_style, bowling_style) VALUES (?, ?, ?, ?)",
                (name, role, batting_style, bowling_style)
            )
            conn.commit()
            new_player_id = cursor.lastrowid
            return jsonify({
                "id": new_player_id,
                "name": name,
                "role": role,
                "batting_style": batting_style,
                "bowling_style": bowling_style,
                "matches": []
            }), 201
        except sqlite3.IntegrityError:
            return jsonify({"error": "Player with this name already exists"}), 409
        except Exception as e:
            print(f"Error adding player: {e}")
            return jsonify({"error": f"Failed to add player: {e}"}), 500

@app.route('/players/<int:player_id>', methods=['GET', 'PUT', 'DELETE'])
def handle_player(player_id):
    conn = get_db_connection()

    if request.method == 'GET':
        player_row = conn.execute('SELECT * FROM players WHERE id = ?', (player_id,)).fetchone()
        if not player_row:
            return jsonify({"message": "Player not found"}), 404

        player_data = dict(player_row)
        matches_cursor = conn.execute('SELECT * FROM matches WHERE player_id = ? ORDER BY id', (player_id,)).fetchall()
        player_data['matches'] = [dict(m) for m in matches_cursor]
        return jsonify(player_data)

    elif request.method == 'PUT':
        data = request.json
        name = data.get('name')
        role = data.get('role')
        batting_style = data.get('batting_style')
        bowling_style = data.get('bowling_style')

        try:
            cursor = conn.execute(
                "UPDATE players SET name = ?, role = ?, batting_style = ?, bowling_style = ? WHERE id = ?",
                (name, role, batting_style, bowling_style, player_id)
            )
            conn.commit()
            if cursor.rowcount == 0:
                return jsonify({"message": "Player not found or no changes made"}), 404
            return jsonify({"message": "Player updated successfully"}), 200
        except sqlite3.IntegrityError:
            return jsonify({"error": "Player with this name already exists"}), 409
        except Exception as e:
            print(f"Error updating player {player_id}: {e}")
            return jsonify({"error": f"Failed to update player: {e}"}), 500

    elif request.method == 'DELETE':
        try:
            cursor = conn.execute('DELETE FROM players WHERE id = ?', (player_id,))
            conn.commit()
            if cursor.rowcount == 0:
                return jsonify({"message": "Player not found"}), 404
            return jsonify({"message": "Player and associated matches deleted successfully"}), 200
        except Exception as e:
            print(f"Error deleting player {player_id}: {e}")
            return jsonify({"error": f"Failed to delete player: {e}"}), 500

@app.route('/players/<int:player_id>/matches', methods=['POST'])
def add_match_to_player(player_id):
    conn = get_db_connection()
    data = request.json
    did_bat = data.get('did_bat', False)
    runs = data.get('runs', 0)
    balls = data.get('balls', 0)
    wickets = data.get('wickets', 0)
    overs = data.get('overs', 0.0)
    conceded = data.get('conceded', 0)
    catches = data.get('catches', 0)
    stumpings = data.get('stumpings', 0)
    run_outs = data.get('run_outs', 0)

    player_exists = conn.execute('SELECT 1 FROM players WHERE id = ?', (player_id,)).fetchone()
    if not player_exists:
        return jsonify({"error": "Player not found"}), 404

    try:
        cursor = conn.execute(
            """INSERT INTO matches (player_id, did_bat, runs, balls, wickets, overs, conceded, catches, stumpings, run_outs)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (player_id, did_bat, runs, balls, wickets, overs, conceded, catches, stumpings, run_outs)
        )
        conn.commit()
        new_match_id = cursor.lastrowid
        return jsonify({
            "id": new_match_id,
            "player_id": player_id,
            "did_bat": did_bat,
            "runs": runs,
            "balls": balls,
            "wickets": wickets,
            "overs": overs,
            "conceded": conceded,
            "catches": catches,
            "stumpings": stumpings,
            "run_outs": run_outs
        }), 201
    except Exception as e:
        print(f"Error adding match for player {player_id}: {e}")
        return jsonify({"error": f"Failed to add match: {e}"}), 500

@app.route('/matches/<int:match_id>', methods=['PUT', 'DELETE'])
def handle_match(match_id):
    conn = get_db_connection()

    if request.method == 'PUT':
        data = request.json
        did_bat = data.get('did_bat')
        runs = data.get('runs')
        balls = data.get('balls')
        wickets = data.get('wickets')
        overs = data.get('overs')
        conceded = data.get('conceded')
        catches = data.get('catches')
        stumpings = data.get('stumpings')
        run_outs = data.get('run_outs')

        update_fields = []
        update_values = []
        if did_bat is not None: update_fields.append("did_bat = ?"); update_values.append(did_bat)
        if runs is not None: update_fields.append("runs = ?"); update_values.append(runs)
        if balls is not None: update_fields.append("balls = ?"); update_values.append(balls)
        if wickets is not None: update_fields.append("wickets = ?"); update_values.append(wickets)
        if overs is not None: update_fields.append("overs = ?"); update_values.append(overs)
        if conceded is not None: update_fields.append("conceded = ?"); update_values.append(conceded)
        if catches is not None: update_fields.append("catches = ?"); update_values.append(catches)
        if stumpings is not None: update_fields.append("stumpings = ?"); update_values.append(stumpings)
        if run_outs is not None: update_fields.append("run_outs = ?"); update_values.append(run_outs)

        if not update_fields:
            return jsonify({"message": "No fields provided for update"}), 400

        update_query = f"UPDATE matches SET {', '.join(update_fields)} WHERE id = ?"
        update_values.append(match_id)

        try:
            cursor = conn.execute(update_query, tuple(update_values))
            conn.commit()
            if cursor.rowcount == 0:
                return jsonify({"message": "Match not found or no changes made"}), 404
            updated_match_row = conn.execute('SELECT * FROM matches WHERE id = ?', (match_id,)).fetchone()
            return jsonify(dict(updated_match_row)), 200
        except Exception as e:
            print(f"Error updating match {match_id}: {e}")
            return jsonify({"error": f"Failed to update match: {e}"}), 500

    elif request.method == 'DELETE':
        try:
            cursor = conn.execute('DELETE FROM matches WHERE id = ?', (match_id,))
            conn.commit()
            if cursor.rowcount == 0:
                return jsonify({"message": "Match not found"}), 404
            return jsonify({"message": "Match deleted successfully"}), 200
        except Exception as e:
            print(f"Error deleting match {match_id}: {e}")
            return jsonify({"error": f"Failed to delete match: {e}"}), 500

with app.app_context():
    init_db()

if __name__ == '__main__':
    # Use environment variable PORT if available (e.g., in cloud hosting), otherwise default to 5000
    port = int(os.getenv("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
