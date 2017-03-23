import os
import json
import uuid
import atexit
import datetime
import traceback
import cf_deployment_tracker
from flask_mail import Mail
from functools import wraps
from flask import g, request
from cloudant import Cloudant
from flask.ext.mail import Message
from cloudant.result import Result
from flask import Flask, render_template, request, jsonify

# Decorators

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            return render_template('signin.html', signin_needed = 'Signin before continuing')
        return f(*args, **kwargs)
    return decorated_function

# Emit Bluemix deployment event
cf_deployment_tracker.track()

MAIL_SERVER='smtp.gmail.com'
MAIL_PORT=465
MAIL_USE_TLS = False
MAIL_USE_SSL= True
MAIL_USERNAME = os.getenv('GMAIL_USERNAME')
MAIL_PASSWORD = os.getenv('GMAIL_PASSWORD')

#Messages
success_message = 'Email sent to {}. Please click the link given in the email to activate the account!'
user_exists_message = 'The user with given email id is registered. Login to continue'

app = Flask(__name__)
app.config.from_object(__name__)
mail = Mail(app)

db_name = 'users'
keys_db_name = 'keys'
client = None
db = None
keys_db = None

# Utility functions

def send_email(to, subject, template):
	msg = Message(
        subject,
        recipients=[to],
        html=template,
        sender="testloginapp111@gmail.com")
	mail.send(msg)

def generate_confirmation_token():
	return uuid.uuid4().hex
	
def email_template(confirmation_url):
	template = """
		<p>Hi There! </p>
		<p>Thank you for signing up. Please click the link below to activate your account:</p>
		<p><a href="{}">{}</a></p>
		<br>
		<p>Cheers!</p>
	"""
	return template.format(confirmation_url, confirmation_url)

def format_email(recipient, confirmation_token):
	confirmation_url = 'login-testapp.mybluemix.net/confirm-account/{}'.format(confirmation_token)
	email_content = email_template(confirmation_url)
	subject = 'Please confirm your account!'
	try:
		send_email(recipient, subject, email_content)
	except Exception:
		print "Could not send email. Traceback:"
		traceback.format_exc()

def get_current_timestamp():
	timestamp = '{:%m-%d-%Y %H:%M:%S}'.format(datetime.datetime.now())
	return timestamp

def create_user(email, confirmation_token, password, full_name):
	"""
		Fields:
		_id = email
		confirmed_acc = False (by default)
		confirmation_token = generate_confirmation_token()
		password
		time_last_visited -> last 5 logins
		full_name
	"""
	if client:
		data = {
        	'_id': email,
        	'full_name': full_name,
        	'password': password,
        	'confirmation_token': confirmation_token,
        	'time_last_login': get_current_timestamp(),
        	'confirmed_account': 'False',
        	}
        new_document = db.create_document(data)
        if new_document.exists():
        	return True
	return False

def is_authenticated(email, password):
	existing_user_entries = client['users']
	if existing_user_entries[email]:
		return existing_user_entries[email]['password'] == password
	 

def get_last_login_and_update_to_current(email):
	existing_user_entries = client['users']
	time_last_login = existing_user_entries[email]['time_last_login']
	existing_user_entries[email]['time_last_login'] = get_current_timestamp()
	return time_last_login

def check_if_user_exists(email):
	existing_user_entries = client['users']
	for user_data in existing_user_entries:
		print user_data
		print user_data['_id']
		if user_data['_id'] == email:
			print 'Got there'
			return True
	return False
	
# Configs

if 'VCAP_SERVICES' in os.environ:
    vcap = json.loads(os.getenv('VCAP_SERVICES'))
    print('Found VCAP_SERVICES')
    if 'cloudantNoSQLDB' in vcap:
        creds = vcap['cloudantNoSQLDB'][0]['credentials']
        user = creds['username']
        password = creds['password']
        url = 'https://' + creds['host']
        client = Cloudant(user, password, url=url, connect=True)
        db = client.create_database(db_name, throw_on_exists=False)
        print('DB CONNECTED')

elif os.path.isfile('vcap-local.json'):
    with open('vcap-local.json') as f:
        vcap = json.load(f)
        print('Found local VCAP_SERVICES')
        creds = vcap['services']['cloudantNoSQLDB'][0]['credentials']
        user = creds['username']
        password = creds['password']
        url = 'https://' + creds['host']
        client = Cloudant(user, password, url=url, connect=True)
        db = client.create_database(db_name, throw_on_exists=False)

# On Bluemix, get the port number from the environment variable PORT
# When running this app on the local machine, default the port to 8080
port = int(os.getenv('PORT', 8080))

@app.before_request
def before_request():
    g.user = None

#Views

@app.route('/')
def home():
	return render_template('signup.html')

@app.route('/signup')
def signup():
    return render_template('signup.html')

@app.route('/signin')
def signin():
    return render_template('signin.html')

@app.route('/new_user', methods=['POST'])
def new_user():
	email = request.form['email']
	name = request.form['name']
	password = request.form['password']
	if check_if_user_exists(email):
		print "User already exists. Redirecting to signin page"
		return render_template('signin.html', user_exists_message= user_exists_message)
	else:
		print "Creating User with email : {}".format(email)
		confirmation_token = generate_confirmation_token()
		create_user(email, confirmation_token, password, name)
		format_email(email, confirmation_token)
		return render_template('success.html', success_message = success_message.format(email))

@app.route('/login_user', methods=['POST'])
def login_user():
	email = request.form['email']
	password = request.form['password']
	if is_authenticated(email, password):
		g.user = email
		last_login_time = get_last_login_and_update_to_current(email)
		return render_template('last_login.html', last_login_time = last_login_time)

@atexit.register
def shutdown():
    if client:
        client.disconnect()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port, debug=True)
