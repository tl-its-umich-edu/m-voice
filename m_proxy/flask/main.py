from functools import wraps
import datetime
import json, requests
from flask import Flask, request, jsonify, abort
from google.cloud import datastore
import dialogflow_v2
import uuid
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
    req_data = request.get_json()

    project = req_data['project'] #project id
    user_query = req_data['user_query'] #user question
    if ('session_id' in req_data):
        session_id = req_data['session_id']
    else:
        session_id = uuid.uuid1()
    client = dialogflow_v2.SessionsClient()
    session = client.session_path(project, session_id)
    
    query_input = {
        "text": {
            "text": user_query,
            "language_code": "en-US"
        }
    }
    response = client.detect_intent(session, query_input) #response is returned as DetectIntentResponse class
    responsedata = {'project': project,
                    'user_query': user_query,
                    'response': response.query_result.fulfillment_text,
                    'session_id': session_id}
    response = jsonify(responsedata)
    # https://enable-cors.org/server_appengine.html
    response.headers.add_header("Access-Control-Allow-Origin", "*")
    return response
