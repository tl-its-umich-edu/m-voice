from functools import wraps
from flask import Flask, request, jsonify, Response, abort
import json, requests, urllib.parse,urllib.request
import filecmp, difflib, shutil
from remove_ignore_entities import removeIgnoreEntities
from deepdiff import DeepDiff
import numpy as np
from google.cloud import datastore

app = Flask(__name__)

#Basic homepage for checking successful deployment
@app.route('/')
def home():
    return "Success"

#Authentication
def check_auth(name,passw):
    return (name=='user' and passw=='pass')
def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            abort(401)
        return f(*args, **kwargs)
    return decorated



#Check if input term is part of a larger official term
def isPartialTerm(search, filename):
    list_data = open(filename)
    for i in list_data:
        if search.upper() == str(i.rstrip("\n\r")).upper():
            return True
    return False


def similarSearch(search, category):

    #Check type of term and adjust file searched accordingly
    if category.upper() == 'LOCATION':
        extrasFilename = 'LocationExtra.txt'
        mainFilename = 'LocationMain.txt'
    elif category.upper() == 'MEAL':
        extrasFilename = 'MealExtra.txt'
        mainFilename = 'MealMain.txt'
    else:
        return "File error"

    
    #Check if input term is part of a larger official term
    if isPartialTerm(search, extrasFilename) == False:
        return "Found"


    #If it is, suggest possible full terms
    
    #Go through list of full terms and check for possibilities
    list_data = open(mainFilename, 'r')
    possible_searches = []
    for i in list_data:
        if search.upper() in str(i.rstrip("\n\r")).upper():
            possible_searches.append(str(i.rstrip("\n\r")))

    #Suggest list of possibilities
    outputstring = "Did you mean "
    for i in possible_searches:
        outputstring += i
        outputstring += ' or '
    
    return outputstring[:-4]





#Webhook call
@app.route('/webhook',methods=['POST'])
@requires_auth
def webhookPost():
    #name = request.args.get("name", "World")
    #return f'Hello, {name}!'
    req_data = request.get_json()

    if 'Location' in req_data['queryResult']['parameters']:
        category = 'Location'
        search = req_data['queryResult']['parameters']['Location']
    elif 'Meal' in req_data['queryResult']['parameters']:
        category = 'Meal'
        search = req_data['queryResult']['parameters']['Meal']
    #return req_data['queryResult']['intent']['displayName']
    else:
        search = 'Error'
        category = 'Error'
    text = similarSearch(search, category)
    
    return jsonify(
      fulfillmentText=text
    )

@app.route('/cron',methods=['POST'])
def cronUpdate():
    #Cron authentication through post request data
    req_data = request.get_json()
    responsedata = ''

    #Get secret values from Datastore environment variables
    client = datastore.Client()
    query = client.query(kind = 'env_vars')
    entity = query.fetch()

    secretindex = 0
    for secrets in entity:
        for secret in secrets:
            if secretindex == 0:
                user = secret
            elif secretindex == 1:
                passw = secret
            else:
                slackurl = secret
            secretindex += 1
    
    if (req_data['user'] != user) or (req_data['pass'] != passw):
        message = 'Authentication failed.'
        
    else:

        with open('ignore.json') as f:
            ignoredata = json.load(f)
        mealchanged = False
        locationchanged = False
        
        #Meal Diff
        mealreq = requests.post('http://api.studentlife.umich.edu/menu/menu_generator/meal.php')
        mealdata = mealreq.json()

        newmeal = []
        for entry in mealdata:
            if entry['optionValue'] != "":
                newmeal.append(entry['optionValue'])

        originalmealfile = open('MealMain.txt', 'r').readlines()
        originalmeal = []
        for entry in originalmealfile:
            originalmeal.append(entry.strip('\n'))

        originalmeal = np.array(removeIgnoreEntities(originalmeal, 'Meal'))
        newmeal = np.array(removeIgnoreEntities(newmeal, 'Meal'))


        mealremoved = np.setdiff1d(originalmeal, newmeal).tolist()
        mealadded = np.setdiff1d(newmeal, originalmeal).tolist()
        mealchanged = False
        if bool(mealremoved) or bool(mealadded):
            mealchanged = True


        #Location Diff
        locationreq = requests.post('http://api.studentlife.umich.edu/menu/menu_generator/location.php')
        locationdata = locationreq.json()

        newlocation = []
        for entry in locationdata:
            if entry['optionValue'] != "":
                newlocation.append(entry['optionValue'])

        originallocationfile = open('LocationMain.txt', 'r').readlines()
        originallocation = []
        for entry in originallocationfile:
            originallocation.append(entry.strip('\n'))

        originallocation = np.array(removeIgnoreEntities(originallocation, 'Location'))
        newlocation = np.array(removeIgnoreEntities(newlocation, 'Location'))

        locationremoved = np.setdiff1d(originallocation, newlocation).tolist()
        locationadded = np.setdiff1d(newlocation, originallocation).tolist()
        locationchanged = False
        if bool(locationremoved) or bool(locationadded):
            locationchanged = True

        
        #Check for file changes for appropriate response to slack if needed
        if locationchanged or mealchanged:
            slackresponse = {}
            slackresponse['attachments'] = []
            
            message = "Update needed for "
            if locationchanged:
                message += "location"
                if bool(locationadded):
                    newlocationsstr = ''
                    for i in locationadded:
                        newlocationsstr = newlocationsstr + i + '\n'
                    slackresponse['attachments'].append( { "title": "New locations", "text": newlocationsstr } )
                if bool(locationremoved):
                    removedlocationsstr = ''
                    print(locationremoved)
                    for i in locationremoved:
                        removedlocationsstr = removedlocationsstr + i + '\n'
                    slackresponse['attachments'].append( { "title": "Removed locations", "text": removedlocationsstr } )
            if mealchanged:
                if bool(mealadded):
                    newmealsstr = ''
                    for i in mealadded:
                        newmealsstr = newmealsstr + i + '\n'
                    slackresponse['attachments'].append( { "title": "New meals", "text": newmealsstr } )
                if bool(mealremoved):
                    removedmealsstr = ''
                    for i in mealremoved:
                        removedmealsstr = removedmealsstr + i + '\n'
                    slackresponse['attachments'].append( { "title": "Removed meals", "text": removedmealsstr } )
                if locationchanged:
                    message += " and meal"
                else:
                    message += "meal"
            message += " in m-voice."
            
            slackresponse['text'] = message

            slackpostdata = requests.post(slackurl, json=slackresponse)
            
        else:
            message = "Data up to date"

    return jsonify(
      message=message,
      locationadded=locationadded,
      locationremoved=locationremoved,
      mealadded=mealadded,
      mealremoved=mealremoved
    )

