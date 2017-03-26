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
            return render_template('signin.html', error_message='Signin before continuing')
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
AUTH_SUCCESS = 'AUTH_SUCCESS'
AUTH_FAIL = 'AUTH_FAIL'
WRONG_USER = 'WRONG_USER'
ACCOUNT_ALREADY_CONFIRMED = 'ACCOUNT_ALREADY_CONFIRMED'
ACCOUNT_CONFIRMED = 'ACCOUNT_CONFIRMED'
ACCOUNT_NOT_CONFIRMED = 'ACCOUNT_NOT_CONFIRMED'
PASSWORD_RESET_SUCCESSFUL = 'PASSWORD_RESET_SUCCESSFUL'

# Messages
success_message = 'Email sent to {}. Please click the link given in the email to activate the account!'
user_exists_message = 'The user with given email id is registered. Login to continue.'
auth_failed_message = 'Password entered did not match our records. Try again. To reset use Forgot Password.' 
wrong_user_message = 'The user provided does not exist. Please signup is you are new to the website.'
account_confirmed_message = 'Thank you for confirming the account. Please login to continue.'
account_already_confirmed_message = 'The link you used is expired, the account has been confirmed already. Please login to continue.'
account_needs_confirmation = 'Not Allowed! You need to confirm the account by clicking the link sent to your email id'
reset_link_sent_message = 'Reset link mailed to your email account, please follow the instructions in the email to reset your password'
reset_password_success_message = 'The password for account with email id - {} was reset'
incorrect_user_message = 'Wrong username entered. Please try again.'
password_reset_token_expired_message = 'Your token for password reset has expired. Please try again.'
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

def generate_token():
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
	
def password_reset_email_template(password_reset_url):
	template = """
		<p>Hi There! </p>
		<p>Please click the link below to reset your password</p>
		<p><a href="{}">{}</a></p>
		<br>
		<p>Cheers!</p>
	"""
	return template.format(password_reset_url, password_reset_url)

def format_email(recipient, confirmation_token):
	confirmation_url = 'login-testapp.mybluemix.net/confirm_account/{}'.format(confirmation_token)
	email_content = email_template(confirmation_url)
	subject = 'Please confirm your account!'
	try:
		send_email(recipient, subject, email_content)
	except Exception:
		print "Could not send email. Traceback:"
		traceback.format_exc()

def format_password_reset_email(recipient, password_reset_token):
	password_reset_url = 'login-testapp.mybluemix.net/reset_password/{}'.format(password_reset_token)
	email_content = password_reset_email_template(password_reset_url)
	subject = 'Reset your password'
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
		confirmation_token = generate_token()
		password
		time_last_visited -> last 5 logins
		full_name
		password_reset_token
	"""
	if client:
		data = {
        	'_id': email,
        	'full_name': full_name,
        	'password': password,
        	'confirmation_token': confirmation_token,
        	'time_last_login': get_current_timestamp(),
        	'confirmed_account': 'False',
        	'password_reset_token': ''
        	}
        new_document = db.create_document(data)
        if new_document.exists():
        	return True
	return False

def is_authenticated(email, password):
	existing_user_entries = client[db_name]
	if check_if_user_exists(email):
		if existing_user_entries[email]['password'] == password:
			if existing_user_entries[email]['confirmed_account'] == 'False':
				return ACCOUNT_NOT_CONFIRMED
			else:	
				return AUTH_SUCCESS
		else:
			return AUTH_FAIL
	return WRONG_USER

def update_user_password(email, password, token):
	user_data = client[db_name][email]
	if user_data['password_reset_token'] == token:
		user_data['password'] = password
		user_data['password_reset_token'] = ''
		user_data.save()
		return PASSWORD_RESET_SUCCESSFUL
	else:
		return WRONG_USER
	

def get_last_login_and_update_to_current(email):
	existing_user_entries = client[db_name]
	time_last_login = existing_user_entries[email]['time_last_login']
	existing_user_entries[email]['time_last_login'] = get_current_timestamp()
	existing_user_entries[email].save()
	return time_last_login

def check_if_user_exists(email):
	existing_user_entries = client[db_name]
	for user_data in existing_user_entries:
		if user_data['_id'] == email:
			return True
	return False
	
def confirm_user_with_confirmation_token(token):
	existing_user_entries = client[db_name]
	for user_data in existing_user_entries:
		print user_data['confirmation_token']
		print token
		if user_data['confirmation_token'] == token:
			if user_data['confirmed_account'] == 'True':
				return ACCOUNT_ALREADY_CONFIRMED
			else:
				user_data['confirmed_account'] = 'True'
				user_data.save()
				print user_data
				return ACCOUNT_CONFIRMED

def confirm_user_with_password_reset_token(token):
	existing_user_entries = client[db_name]
	for user_data in existing_user_entries:
		print user_data['confirmation_token']
		if user_data['password_reset_token'] == token:
			return True
		else:
			return False

def set_reset_password_token_field(email, password_reset_token):
	existing_user_entries = client[db_name]
	existing_user_entries[email]['password_reset_token'] = password_reset_token
	existing_user_entries[email].save()

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

#elif os.path.isfile('vcap-local.json'):
#    with open('vcap-local.json') as f:
#        vcap = json.load(f)
#        print('Found local VCAP_SERVICES')
#        creds = vcap['services']['cloudantNoSQLDB'][0]['credentials']
#        user = creds['username']
#        password = creds['password']
#        url = 'https://' + creds['host']
#        client = Cloudant(user, password, url=url, connect=True)
#        db = client.create_database(db_name, throw_on_exists=False)

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
		return render_template('signin.html', error_message=user_exists_message)
	else:
		print "Creating User with email : {}".format(email)
		confirmation_token = generate_token()
		create_user(email, confirmation_token, password, name)
		format_email(email, confirmation_token)
		return render_template('success.html', success_message = success_message.format(email))

@app.route('/login_user', methods=['POST'])
def login_user():
	email = request.form['email']
	password = request.form['password']
	auth_result = is_authenticated(email, password)
	if auth_result == ACCOUNT_NOT_CONFIRMED:
		return render_template('error.html', error_message=account_needs_confirmation)
	if auth_result == AUTH_SUCCESS:
		g.user = email
		last_login_time = get_last_login_and_update_to_current(email)
		return render_template('last_login.html', last_login_time=last_login_time)
	if auth_result == AUTH_FAIL:
		return render_template('signin.html', error_message=auth_failed_message)
	if auth_result == WRONG_USER:
		return render_template('signin.html', error_message=wrong_user_message)

@app.route('/confirm_account/<token>')
def confirm_account(token):
	status = confirm_user_with_confirmation_token(token)
	if status == ACCOUNT_ALREADY_CONFIRMED:
		return render_template('signin.html', error_message=account_already_confirmed_message)
	if status == ACCOUNT_CONFIRMED:
		return render_template('signin.html', success_message=account_confirmed_message)	

@app.route('/forgot_password')
def forgot_password():
	return render_template('forgot_password.html')	

@app.route('/send_reset_link', methods=['POST'])
def send_reset_link():
	email = request.form['email']
	if check_if_user_exists(email):
		password_reset_token = generate_token()
		set_reset_password_token_field(email, password_reset_token)
		format_password_reset_email(email, password_reset_token)
		return render_template('success.html', success_message=reset_link_sent_message)
	else:
		return render_template('signup.html', error_message=incorrect_user_message)

@app.route('/reset_password/<token>')
def reset_password(token):
	if confirm_user_with_password_reset_token(token):
		return render_template('reset_password.html', token = token)
	else:
		return render_template('error.html', error_message = password_reset_token_expired_message)
	
@app.route('/update_password', methods=['POST'])
def update_password():
	email = request.form['email']
	token = request.form['token']
	password = request.form['password']
	if check_if_user_exists(email):
		status = update_user_password(email, password, token)
		if status == PASSWORD_RESET_SUCCESSFUL:
			return render_template('signin.html', success_message = reset_password_success_message.format(email))
	else:
		return render_template('error.html', error_message = incorrect_user_message)

@atexit.register
def shutdown():
    if client:
        client.disconnect()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port, debug=True)
