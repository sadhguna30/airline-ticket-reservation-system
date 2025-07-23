from flask import Flask, render_template, request, redirect, session, send_file
from pymongo import MongoClient
from bson.objectid import ObjectId
from fpdf import FPDF
import os

app = Flask(__name__)
app.secret_key = 'sadhguna'

client = MongoClient("mongodb://localhost:27017")
db = client['airline_db']
users = db['users']
flights = db['flights']
bookings = db['bookings']

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        user = {
            'username': request.form['username'],
            'password': request.form['password'],
            'is_admin': request.form.get('admin') == 'on'
        }
        users.insert_one(user)
        if user['is_admin']:
            return redirect('/admin_login')
        else:
            return redirect('/login')
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = users.find_one({'username': username, 'password': password})
        if user:
            session['user_id'] = str(user['_id'])
            session['username'] = username  # Store username
            session['is_admin'] = user['is_admin']
            return redirect('/dashboard')
        return 'Invalid credentials'
    return render_template('login.html')

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        admin = users.find_one({'username': username, 'password': password, 'is_admin': True})
        if admin:
            session['user_id'] = str(admin['_id'])
            session['username'] = username  # Store username
            session['is_admin'] = True
            return redirect('/admin_dashboard')
        return 'Invalid admin credentials'
    return render_template('admin_login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('is_admin', None)
    session.pop('username', None)  # Clear username
    return redirect('/')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    if session['is_admin']:
        return redirect('/admin_dashboard')
    return render_template('dashboard.html')

@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user_id' not in session or not session['is_admin']:
        return redirect('/admin_login')
    return render_template('admin_dashboard.html', flights=flights.find())

@app.route('/add_flight', methods=['POST'])
def add_flight():
    flight = {
        'flight_no': request.form['flight_no'],
        'origin': request.form['origin'],
        'destination': request.form['destination'],
        'date': request.form['date'],
        'economy_seats': int(request.form['economy_seats']),
        'business_seats': int(request.form['business_seats']),
        'economy_cost': float(request.form['economy_cost']),
        'business_cost': float(request.form['business_cost'])
    }
    flights.insert_one(flight)
    return redirect('/admin_dashboard')

@app.route('/edit_flight/<flight_id>', methods=['GET', 'POST'])
def edit_flight(flight_id):
    flight = flights.find_one({'_id': ObjectId(flight_id)})
    if request.method == 'POST':
        updated_flight = {
            'flight_no': request.form['flight_no'],
            'origin': request.form['origin'],
            'destination': request.form['destination'],
            'date': request.form['date'],
            'economy_seats': int(request.form['economy_seats']),
            'business_seats': int(request.form['business_seats']),
            'economy_cost': float(request.form['economy_cost']),
            'business_cost': float(request.form['business_cost'])
        }
        flights.update_one({'_id': ObjectId(flight_id)}, {'$set': updated_flight})
        return redirect('/admin_dashboard')
    return render_template('edit_flight.html', flight=flight)

@app.route('/search', methods=['GET'])
def search():
    origin = request.args.get('origin')
    destination = request.args.get('destination')
    date = request.args.get('date')
    results = flights.find({'origin': origin, 'destination': destination, 'date': date})
    return render_template('flights.html', flights=results)

@app.route('/book/<flight_id>')
def book(flight_id):
    flight = flights.find_one({'_id': ObjectId(flight_id)})
    return render_template('book.html', flight=flight)

@app.route('/confirm_booking/<flight_id>', methods=['POST'])
def confirm_booking(flight_id):
    flight = flights.find_one({'_id': ObjectId(flight_id)})
    economy_tickets = int(request.form.get('economy_tickets', 0))
    business_tickets = int(request.form.get('business_tickets', 0))

    total_cost = (economy_tickets * flight['economy_cost']) + (business_tickets * flight['business_cost'])

    if (flight['economy_seats'] >= economy_tickets and flight['business_seats'] >= business_tickets):
        new_booking = {
            'user_id': session['user_id'],
            'username': session['username'],
            'flight_id': flight_id,
            'economy_tickets': economy_tickets,
            'business_tickets': business_tickets,
            'total_cost': total_cost
        }
        result = bookings.insert_one(new_booking)

        flights.update_one({'_id': ObjectId(flight_id)}, {'$inc': {'economy_seats': -economy_tickets, 'business_seats': -business_tickets}})
        return redirect(f'/payment/{result.inserted_id}')
    else:
        return "Not enough seats available in one or both classes."

@app.route('/payment/<booking_id>')
def payment(booking_id):
    booking = bookings.find_one({'_id': ObjectId(booking_id)})
    flight = flights.find_one({'_id': ObjectId(booking['flight_id'])})
    return render_template('payment.html',
                           booking=booking,
                           flight=flight,
                           total_amount=booking['total_cost'])

@app.route('/confirm_payment/<booking_id>')
def confirm_payment(booking_id):
    booking = bookings.find_one({'_id': ObjectId(booking_id)})
    return render_template('payment_success.html', booking=booking)

@app.route('/history')
def history():
    user_id = session['user_id']
    user_bookings = list(bookings.find({'user_id': user_id}))
    for booking in user_bookings:
        booking['flight'] = flights.find_one({'_id': ObjectId(booking['flight_id'])})
    return render_template('history.html', bookings=user_bookings)

@app.route('/cancel/<booking_id>')
def cancel(booking_id):
    booking = bookings.find_one({'_id': ObjectId(booking_id)})
    flights.update_one({'_id': ObjectId(booking['flight_id'])}, {'$inc': {'economy_seats': booking['economy_tickets'], 'business_seats': booking['business_tickets']}})
    bookings.delete_one({'_id': ObjectId(booking_id)})
    return redirect('/history')

@app.route('/ticket/<booking_id>')
def ticket(booking_id):
    booking = bookings.find_one({'_id': ObjectId(booking_id)})
    flight = flights.find_one({'_id': ObjectId(booking['flight_id'])})

    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("Arial", style="B", size=16)
    pdf.cell(200, 10, txt="SkyHigh Airlines - Flight Ticket", ln=True, align="C")
    pdf.ln(10) 

    pdf.set_font("Arial", style="I", size=15)
    pdf.cell(200, 10, txt=f"Booked by: {booking['username']}", ln=True)

    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Flight number: {flight['flight_no']}", ln=True)
    pdf.cell(200, 10, txt=f"Origin: {flight['origin']}", ln=True) 
    pdf.cell(200, 10, txt=f"Destination: {flight['destination']}", ln=True) 
    pdf.cell(200, 10, txt=f"Date: {flight['date']}", ln=True)
    pdf.cell(200, 10, txt=f"Economy Tickets: {booking['economy_tickets']}", ln=True)
    pdf.cell(200, 10, txt=f"Business Tickets: {booking['business_tickets']}", ln=True)
    pdf.cell(200, 10, txt=f"Total Cost: ${booking['total_cost']}", ln=True)

    pdf.ln(15)  # Add a line break
    pdf.set_font("Arial", style="I", size=10)
    pdf.cell(200, 10, txt="Thank you for choosing SkyHigh Airlines!", ln=True, align="C")

    file_path = f"ticket_{booking_id}.pdf"
    pdf.output(file_path)
    return send_file(file_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
