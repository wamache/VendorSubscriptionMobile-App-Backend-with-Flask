from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import datetime
import requests
import base64

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/mobiapppython'  # Replace with your database URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Model Definitions
class Vendor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    businesses = db.relationship('Business', backref='vendor', lazy=True)
    subscriptions = db.relationship('Subscription', backref='vendor', lazy=True)
    payments = db.relationship('Payment', backref='vendor', lazy=True)

class Business(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200))
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=False)
    branches = db.relationship('Branch', backref='business', lazy=True)
    products = db.relationship('Product', backref='business', lazy=True)

class Branch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200))
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)

class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plan = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    max_products = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=False)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Integer, nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    payment_method = db.Column(db.String(50), nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=False)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    business_id = db.Column(db.Integer, db.ForeignKey('business.id'), nullable=False)

# API Endpoints
@app.route('/vendors', methods=['POST'])
def create_vendor():
    try:
        data = request.json
        if not data.get('email') or not data.get('name'):
            return jsonify({"error": "Email and Name are required"}), 400

        new_vendor = Vendor(email=data['email'], name=data['name'])
        db.session.add(new_vendor)
        db.session.commit()
        return jsonify({"message": "Vendor created successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/businesses', methods=['POST'])
def create_business():
    try:
        data = request.json
        new_business = Business(
            name=data['name'],
            address=data['address'],
            vendor_id=data['vendor_id']
        )
        db.session.add(new_business)
        db.session.commit()
        return jsonify({"message": "Business created successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/subscriptions', methods=['POST'])
def create_subscription():
    try:
        data = request.json
        plan = data['plan']
        vendor_id = data['vendor_id']

        # Define subscription plans
        subscription_plans = {
            "starter": {"price": 300, "max_products": 10},
            "pro": {"price": 400, "max_products": 100},
            "enterprise": {"price": 600, "max_products": float('inf')}
        }

        if plan not in subscription_plans:
            return jsonify({"error": "Invalid subscription plan selected"}), 400

        plan_details = subscription_plans[plan]
        new_subscription = Subscription(
            plan=plan,
            price=plan_details['price'],
            max_products=plan_details['max_products'],
            vendor_id=vendor_id
        )
        db.session.add(new_subscription)
        db.session.commit()
        return jsonify({"message": "Subscription created successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/payments/<int:vendor_id>', methods=['POST'])
def process_payment(vendor_id):
    try:
        total_payment = calculate_total_payment(vendor_id)
        response = initiate_mpesa_stk_push(vendor_id, total_payment)
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# Helper Functions
def calculate_total_payment(vendor_id):
    vendor = Vendor.query.get(vendor_id)
    if not vendor:
        raise Exception("Vendor not found")

    total_payment = 0
    additional_branch_fee = 300

    for subscription in vendor.subscriptions:
        total_payment += subscription.price

    for business in vendor.businesses:
        total_payment += len(business.branches) * additional_branch_fee

    return total_payment

def initiate_mpesa_stk_push(vendor_id, amount):
    try:
        # M-Pesa API credentials
        consumer_key = 'your_consumer_key'
        consumer_secret = 'your_consumer_secret'
        shortcode = 'your_shortcode'
        lipa_na_mpesa_online_passkey = 'your_passkey'
        lipa_na_mpesa_online_url = 'https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest'

        # Generate access token
        api_url = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
        response = requests.get(api_url, auth=(consumer_key, consumer_secret))
        access_token = response.json().get('access_token')

        if not access_token:
            raise Exception("Failed to get access token")

        # Prepare the request payload
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        password = base64.b64encode((shortcode + lipa_na_mpesa_online_passkey + timestamp).encode('utf-8')).decode('utf-8')
        phone_number = request.json.get('phone_number')

        if not phone_number:
            raise Exception("Phone number is required for payment")

        payload = {
            "BusinessShortCode": shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": amount,
            "PartyA": phone_number,
            "PartyB": shortcode,
            "PhoneNumber": phone_number,
            "CallBackURL": "https://your_callback_url",
            "AccountReference": f"Vendor-{vendor_id}",
            "TransactionDesc": "Payment for subscription"
        }

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        response = requests.post(lipa_na_mpesa_online_url, json=payload, headers=headers)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

# Main entry point
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
