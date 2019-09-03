from functools import wraps
import datetime
import json, requests
from flask import Flask, request, jsonify, abort
from google.cloud import datastore
#import google.cloud.logging

app = Flask(__name__)

#TODO: Move this into a common library
def get_secrets():
    """Fetches secrets from Datastore and returns them as a list.
    """
    client = datastore.Client()
    query = client.query(kind='env_vars')
    entity = query.fetch()
    secrets = list(entity)[0]
    return secrets

#Authentication
def check_auth(name, passw):
    secrets = get_secrets()
    passwcheck = secrets.get('pass')
    usercheck = secrets.get('user')
    return name == usercheck and passw == passwcheck
def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            abort(401)
        return f(*args, **kwargs)
    return decorated

#Basic homepage for checking successful deployment
@app.route('/')
def home():
    """Web app home page for quick successful deployment check.
    """
    return "Success"

#Webhook call
@app.route('/proxy', methods=['POST'])
@requires_auth
def proxy_post():
    """ Proxy to DialogFlow
    """
    secrets = get_secrets()
#    req_data = request.get_json()

    return jsonify("")
