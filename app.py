from flask import Flask, render_template, request, redirect, url_for, session, flash
import cv2
import face_recognition
import numpy as np
import pickle
from db_config import get_connection
import os
import base64
from io import BytesIO
from PIL import Image

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Replace with a real secret in production

# Face encoding helper
def get_face_encoding(image):
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    boxes = face_recognition.face_locations(rgb)
    encodings = face_recognition.face_encodings(rgb, boxes)
    return encodings[0] if encodings else None

# Route: Home
@app.route('/')
def home():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')
# Route: Register
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Get form fields
        name = request.form['name']
        username = request.form['username']
        password = request.form['password']
        image_data = request.form.get('image_data')

        # Check if any required field is blank
        if not name or not username or not password or not image_data:
            flash("All fields are required. Please fill out all fields and provide an image.")
            return redirect(url_for('register'))

        # Decode the base64 image
        try:
            image_data = image_data.split(',')[1]  # Remove the header
            image_bytes = base64.b64decode(image_data)
            img = Image.open(BytesIO(image_bytes)).convert('RGB')
            frame = np.array(img)
        except Exception:
            flash("Invalid image data.")
            return redirect(url_for('register'))

        # Get face encoding
        encoding = get_face_encoding(frame)
        if encoding is None:
            flash("Face not detected. Try again.")
            return redirect(url_for('register'))

        # Check if face data already exists in the database
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT face_encoding FROM users")
        existing_face_data = cursor.fetchall()

        for face_data in existing_face_data:
            db_encoding = np.frombuffer(face_data[0], dtype=np.float64)
            matches = face_recognition.compare_faces([db_encoding], encoding)
            if matches[0]:
                flash("This face data already exists.")
                return redirect(url_for('register'))

        # Save the new user data to the database
        try:
            cursor.execute("INSERT INTO users (name, username, password, face_encoding) VALUES (%s, %s, %s, %s)",
                           (name, username, password, encoding.tobytes()))
            conn.commit()
            flash("Registered successfully!")
            return redirect(url_for('login'))
        except Exception as e:
            conn.rollback()
            flash("Voter ID already exists or database error.")
            return redirect(url_for('register'))
        finally:
            cursor.close()
            conn.close()

    return render_template('register.html')

# Route: Login with Face
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        image_data = request.form['image_data']
        if not image_data:
            flash("No image received.")
            return redirect(url_for('login'))

        # Decode base64 image
        image_data = image_data.split(',')[1]  # Remove the header
        image_bytes = base64.b64decode(image_data)
        img = Image.open(BytesIO(image_bytes)).convert('RGB')
        frame = np.array(img)  # Convert to numpy array (RGB)

        encoding = get_face_encoding(frame)
        if encoding is None:
            flash("Face not detected.")
            return redirect(url_for('login'))

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, face_encoding FROM users")
        users = cursor.fetchall()

        for user_id, face_data in users:
            db_encoding = np.frombuffer(face_data, dtype=np.float64)
            matches = face_recognition.compare_faces([db_encoding], encoding)
            if matches[0]:
                session['user_id'] = user_id
                return redirect(url_for('vote'))

        flash("Face not recognized.")
        return redirect(url_for('login'))

    return render_template('login.html')

# Route: Vote
@app.route('/vote', methods=['GET', 'POST'])
def vote():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT has_voted FROM users WHERE id = %s", (user_id,))
    has_voted = cursor.fetchone()[0]

    if has_voted:
        return redirect(url_for('vote_confirmation'))

    if request.method == 'POST':
        candidate_id = request.form['candidate']

        # Get candidate name for confirmation
        cursor.execute("SELECT name FROM candidates WHERE id = %s", (candidate_id,))
        candidate_name = cursor.fetchone()[0]

        cursor.execute("INSERT INTO votes (user_id, candidate_id) VALUES (%s, %s)", (user_id, candidate_id))
        cursor.execute("UPDATE users SET has_voted = TRUE WHERE id = %s", (user_id,))
        conn.commit()
        session['voted_candidate'] = candidate_name
        return redirect(url_for('vote_confirmation'))

    cursor.execute("SELECT id, name FROM candidates")
    candidates = cursor.fetchall()
    return render_template('vote.html', candidates=candidates)

@app.route('/vote_confirmation')
def vote_confirmation():
    return render_template('vote_confirmation.html')


# Route: Results
@app.route('/results')
def results():
    conn=get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT c.name, COUNT(v.id) as vote_count FROM candidates c LEFT JOIN votes v ON c.id = v.candidate_id GROUP BY c.id")
    results = cursor.fetchall()
    return render_template("results.html", results=results)

# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)