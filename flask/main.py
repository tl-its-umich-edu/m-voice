from functools import wraps
from flask import Flask, request, jsonify, Response, abort
import json, requests, urllib.parse,urllib.request
import filecmp, difflib, shutil
import numpy as np
from google.cloud import datastore
import datetime
from remove_ignore_entities import removeIgnoreEntities
from datahandle import requestLocationAndMeal, requestItem

app = Flask(__name__)

###Helper functions

#Authentication
def check_auth(name, passw):
    return (name=='user' and passw=='pass')
def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            abort(401)
        return f(*args, **kwargs)
    return decorated

def isPartialTerm(search, filename):
    """Checks if input term is part of a larger official term by looking for any matches with split up versions of regular terms.

    :param search: The searched term (e.g. 'north quad')
    :type search: string
    :param filename: Name of the file the term is being searched for in ('LocationExtra.txt')
    :type filename: string
    """
    list_data = open(filename)
    for i in list_data:
        if search.upper() == str(i.rstrip("\n\r")).upper():
            return True
    return False

def similarSearch(search, category):
    """Handles user input that doesn't match official terms exactly using `isPartialTerm`. If input ``search`` is a partial term of any official terms, returns list of recommended official terms.

    :param search: The searched term (e.g. 'north quad')
    :type search: string
    :param category: Entity category of the search term ('Location'/'Meal')
    :type filename: string
    """
    
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



def addFollowupEventInput(responsedata, outputParams):
    """Helper function for adding followupEventInput trigger to send data to queryHelper intent.

    :param responsedata: The HTTP response data
    :type responsedata: dict
    :param outputParams: Output context paramaters to send to queryHelper
    :type outputParams: dict
    """
    responsedata['followupEventInput'] = {
        'name': 'queryHelperEvent',
        'parameters': outputParams
    }
    return responsedata

def requiredEntitiesHandler(req_data, intentname):
    """Handles response for intents with 2 entities that are both required and need to be handled manually, returns approriate parameters for specific intent handler to take care of.

    :param req_data: The HTTP response data
    :type req_data: JSON
    :param intentname: Output context paramaters to send to queryHelper
    :type intentname: string
    """
    if intentname == 'findLocationAndMeal':
        entity1 = 'Location'
        entity2 = 'Meal'
        entity1OutputContext = 'LocationOutputContext'
        entity2OutputContext = 'MealOutputContext'
        entity1Question = 'Which dining location?'
        entity2Question = 'What meal would you like?'


    entity1Entered = False
    entity2Entered = False
    entity2_in = ""
    entity1_in = ""


    inputParams = req_data['queryResult']['parameters']
    outputParams = {}

    #Check for Location and Meal parameters in Dialogflow request
    if inputParams[entity1]:
        category = entity1
        search = req_data['queryResult']['parameters'][entity1]
        entity1_in = search
        outputParams[category] = search
        entity1Entered = True
        
    if inputParams[entity2]:
        if entity1Entered == False:
            category = entity2
            search = req_data['queryResult']['parameters'][entity2]
            entity2_in = search
            outputParams[category] = search
        entity2Entered = True
        
    #Error if neither are found
    if (entity1Entered == False) and (entity2Entered == False):
        search = 'Error'
        category = 'Error'

    #Handle search for location or meal, location first if both parameters are in request
    text = similarSearch(search, category)
    
    #Setting up response data
    responsedata = {}
    
    #Text is valid    
    if text == 'Found':
        validParams = True
        
        if entity1Entered:
            outputParams[entity1 + 'OutputContext'] = search
        elif entity2Entered:
            outputParams[entity2 + 'OutputContext'] = search
    
        additionalOutputParams = req_data['queryResult']['outputContexts'][0]['parameters']
        if entity1OutputContext in additionalOutputParams and inputParams[entity1] == '':
            inputParams[entity1] = additionalOutputParams[entity1OutputContext]
        if entity2OutputContext in additionalOutputParams and inputParams[entity2] == '':
            inputParams[entity2] = additionalOutputParams[entity2OutputContext]
       
        #If both location and meal parameters included in request, now handle meal
        if entity1Entered and entity2Entered:
            category = entity2
            search = inputParams[entity2]
            entity2_in = search
            text = similarSearch(search, category)

            if text == 'Found':
                outputParams[category] = search
                outputParams[category + 'OutputContext'] = search
            else:
                validParams = False

        #If location/meal/both search is fully valid, send response triggering Dialogflow event
        if validParams:

            if len(outputParams) <= 2:
                if entity1 in outputParams and (inputParams[entity2] == ''):
                    outputParams['Data'] = entity2Question
                    responsedata = addFollowupEventInput(responsedata, outputParams)

                elif entity2 in outputParams and (inputParams[entity1] == ''):
                    outputParams['Data'] = entity1Question
                    responsedata = addFollowupEventInput(responsedata, outputParams)
                    
                else:
                    
                    if entity1 not in outputParams:
                        entity1_in  = inputParams[entity1]
                    if entity2 not in outputParams:
                        entity2_in = inputParams[entity2]

                    date_in = datetime.date.today()
                    outputParams['Data'] = [date_in, entity1_in, entity2_in]
                    responsedata = addFollowupEventInput(responsedata, outputParams)
            
            else:
                date_in = datetime.date.today()
                outputParams['Data'] = [date_in, entity1_in, entity2_in]
                responsedata = addFollowupEventInput(responsedata, outputParams)
                
                
        #Else, send suggestion to user for the parameter that was invalid
        #If both parameters invalid, prioritize location
        else:
            outputParams['Data'] = text
            responsedata = addFollowupEventInput(responsedata, outputParams)
    else:
        outputParams['Data'] = text
        responsedata = addFollowupEventInput(responsedata, outputParams)

    return responsedata


def findLocationAndMeal(req_data):
    """Dialogflow ``findLocationAndMeal`` intent handler. Checks for valid Location and Meal and sends HTTP response with appropriate data.

    :param req_data: Dialogflow POST request data
    :type req_data: JSON
    """
    responsedata = requiredEntitiesHandler(req_data, 'findLocationAndMeal')
    if 'followupEventInput' in responsedata:
        data = responsedata['followupEventInput']['parameters']['Data']
        if type(data) is list:
            responsedata['followupEventInput']['parameters']['Data'] = requestLocationAndMeal(data[0],data[1],data[2])
            
    return responsedata

#findItem intent handling
def findItem(req_data):
    """Dialogflow ``findItem`` intent handler. Checks for valid Location and Item and sends HTTP response with appropriate data.

    :param req_data: Dialogflow POST request data
    :type req_data: JSON
    """
    responsedata = {}
    outputParams = {}

    date_in = datetime.date.today()
    loc_in = req_data['queryResult']['parameters']['Location']
    item_in = req_data['queryResult']['parameters']['Item']
    if 'Meal' in req_data['queryResult']['parameters']:
        meal_in = req_data['queryResult']['parameters']['Meal']
    else:
        meal_in = ''
    

    text = similarSearch(loc_in, 'Location')
    if text == 'Found':
        outputParams['Data'] = requestItem(date_in, loc_in,
                                           req_data['queryResult']['parameters']['Item'], meal_in)['fulfillmentText']
                
        outputParams['LocationOutputContext'] = loc_in
        responsedata = addFollowupEventInput(responsedata, outputParams)
                        
    else:
        outputParams['Data'] = text  
        responsedata = addFollowupEventInput(responsedata, outputParams)
            
    responsedata = addFollowupEventInput(responsedata, outputParams)
    

    return responsedata
#########################################################################
###Primary Handler Functions

#Basic homepage for checking successful deployment
@app.route('/')
def home():
    """Web app home page for quick successful deployment check.
    """
    return "Success"

#Webhook call
@app.route('/webhook',methods=['POST'])
@requires_auth
def webhookPost():
    """Dialogflow webhook POST Request handler requiring authentication. Uses `findLocationAndMeal` or `findItem` intent handlers and returns appropriate JSON response.
    """
    req_data = request.get_json()
    
    intentname = req_data['queryResult']['intent']['displayName']

    if 'queryHelper' in intentname:
        responsedata = ''
        for i in req_data['queryResult']['outputContexts']:
            if 'parameters' in i:
                if 'Data' in i['parameters']:
                    responsedata = i['parameters']['Data']
                    break
        responsedata = { 'fulfillmentText': responsedata }
    elif 'findLocationAndMeal' in intentname:
        responsedata = findLocationAndMeal(req_data)
    elif 'findItem' in intentname:
        responsedata = findItem(req_data)


    return jsonify ( responsedata )

#Google Cron update handler
@app.route('/cron',methods=['POST'])
def cronUpdate(): 
    """Google Cloud Platform scheduled CRON request handler. Checks for changes to MDining API data (Location/Meal), sends notification to Slack channel if change detected. Ignores changes to specified terms in ``ignore.json`` file. Authenticates requests by checking for user and passw in POST request body.
    """
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
