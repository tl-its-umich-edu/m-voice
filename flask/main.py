from functools import wraps
from flask import Flask, request, jsonify, Response, abort
import json, requests, urllib.parse,urllib.request
import filecmp, difflib, shutil
import numpy as np
from google.cloud import datastore
import datetime
from remove_ignore_entities import removeIgnoreEntities
from datahandle import datahandle

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

#Handling non-exact search terminology
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
    
    return outputstring[:-4] + '?'


#Webhook call
@app.route('/webhook',methods=['POST'])
@requires_auth
def webhookPost():
    req_data = request.get_json()

    parameters = {}
    
    locationEntered = False
    mealEntered = False
    meal_in = ""
    loc_in = ""
    #Check for Location and Meal parameters in Dialogflow request
    if 'Location' in req_data['queryResult']['parameters']:
        category = 'Location'
        search = req_data['queryResult']['parameters']['Location']
        loc_in = search
        parameters[category] = category 
        locationEntered = True
    if 'Meal' in req_data['queryResult']['parameters']:
        if locationEntered == False:
            category = 'Meal'
            search = req_data['queryResult']['parameters']['Meal']
            meal_in = search
            parameters[category] = category
        mealEntered = True
    #Error if neither are found
    if (locationEntered == False) and (mealEntered == False):
        search = 'Error'
        category = 'Error'

    #Handle search for location or meal, location first if both parameters are in request
    text = similarSearch(search, category)
    
    #Setting up response data
    responsedata = { 'fulfillmentText': text }

    #Text is valid    
    if text == 'Found': 
        validParams = True

        #If both location and meal parameters included in request, now handle meal
        if locationEntered and mealEntered:
            category = 'Meal'
            search = req_data['queryResult']['parameters']['Meal']
            meal_in = search
            text = similarSearch(search, category)
            
            if text == 'Found':
                parameters[category] = category
            else:
                validParams = False

        #If location/meal/both search is fully valid, send response triggering Dialogflow event
        if validParams:
            outputcontextparams = req_data['queryResult']['outputContexts'][0]['parameters']
            if len(parameters) == 1:
                
                if 'Location' in parameters and ('Meal' not in outputcontextparams):
                    eventname = 'valid_location'
                    responsedata = { 'fulfillmentText': 'What meal would you like?' }

                elif 'Meal' in parameters and ('Location' not in outputcontextparams):
                    eventname = 'valid_meal'
                    responsedata = { 'fulfillmentText': 'Which dining location?' }
                    
                else:
                    if 'Location' not in parameters:
                        loc_in  = req_data['queryResult']['outputContexts'][0]['parameters']['Location']
                    if 'Meal' not in parameters:
                        meal_in = req_data['queryResult']['outputContexts'][0]['parameters']['Meal']
                    date_in = datetime.date.today()
                    responsedata['fulfillmentText'] = datahandle(date_in, loc_in, meal_in)
            else:
                date_in = datetime.date.today()
                responsedata['fulfillmentText'] = datahandle(date_in, loc_in, meal_in)
                
        #Else, send suggestion to user for the parameter that was invalid
        #If both parameters invalid, prioritize location
        else:
            responsedata['fulfillmentText'] = text

    return jsonify ( responsedata )

@app.route('/cron',methods=['POST'])
def cronUpdate():
    #Cron authentication through post request data
    req_data = request.get_json()
    responsedata = ''

    #Get secret values from Datastore environment variables
    client = datastore.Client()
    query = client.query(kind = 'env_vars')
    entity = query.fetch()

    secrets = list(entity)[0]
    slackurl = secrets.get('slack_api')
    passw = secrets.get('pass')
    user = secrets.get('user')
    
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
