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
    class Entity:
        def __init__(self, name, output_context, question):
            self.name = name
            self.output_context = output_context
            self.question = question
        
    entities = [Entity('Location','LocationOutputContext','Which dining location?'),
                Entity('Meal','MealOutputContext','What meal would you like?')]

    #Setting up variables
    inputParams = req_data['queryResult']['parameters']
    additionalOutputParams = req_data['queryResult']['outputContexts'][0]['parameters']

    
    outputParams = {}
    responsedata = {}
    entityInputs = []
    entitySearchResponses = []
    validParams = True
    readyToOutput = False
    
    for entity in entities:

        #If parameter is filled, check if valid
        if inputParams[entity.name]:
            search = inputParams[entity.name]
            text = similarSearch(search, entity.name)

            #Parameter invalid
            if text != 'Found':
                validParams = False
                if not readyToOutput:
                    outputParams['Data'] = text
                    responsedata = addFollowupEventInput(responsedata, outputParams)
                    readyToOutput = True
            #Parameter valid
            else:
                entityInputs.append(search)
                entitySearchResponses.append(text)
                outputParams[entity.name + 'OutputContext'] = search

        #If paramater is unfilled, check if complementary output context parameter exists and is valid
        elif entity.output_context in additionalOutputParams:
            search = additionalOutputParams[entity.output_context]
            text = similarSearch(search, entity.name)

            #Parameter invalid
            if text != 'Found':
                validParams = False
                if not readyToOutput:
                    outputParams['Data'] = text
                    responsedata = addFollowupEventInput(responsedata, outputParams)

            #Parameter valid
            else:
                entityInputs.append(search)
                entitySearchResponses.append(text)
                outputParams[entity.name + 'OutputContext'] = search
            
        #If parameter is unfilled, request to be filled
        else:
            validParams = False
            if not readyToOutput:
                outputParams['Data'] = entity.question
                responsedata = addFollowupEventInput(responsedata, outputParams)
                readyToOutput = True

    #If parameters filled and valid, return data
    if validParams:
        outputParams['Data'] = [entityInputs[0], entityInputs[1]]
        responsedata = addFollowupEventInput(responsedata, outputParams)

    return responsedata



def findLocationAndMeal(req_data):
    """Dialogflow ``findLocationAndMeal`` intent handler. Checks for valid Location and Meal and sends HTTP response with appropriate data.

    :param req_data: Dialogflow POST request data
    :type req_data: JSON
    """

    #Check if date entered: if not, assume today
    inputParams = req_data['queryResult']['parameters']
    if inputParams['Date']:
        date_in = (inputParams['Date'])[:10]
        dateEntered = True
    else:
        date_in = datetime.date.today()
        dateEntered = False

    startText = ''
    temporaryResponse = ''
    
    responsedata = requiredEntitiesHandler(req_data, 'findLocationAndMeal')

    data = responsedata['followupEventInput']['parameters']['Data']
    if type(data) is list:
        temporaryResponse = requestLocationAndMeal(date_in,data[0],data[1])
        
        if dateEntered and req_data['queryResult']['outputContexts'][0]['parameters']['Date.original']:
            Date_original = req_data['queryResult']['outputContexts'][0]['parameters']['Date.original']

            temporaryResponse = temporaryResponse[:-1]
            if Date_original.lower() == 'yesterday' or Date_original.lower() == 'tomorrow' or Date_original.lower() == 'today':
                startText += (Date_original[0].upper() + Date_original[1:])
                
            else:
                startText += ('On ' + Date_original)

        if 'No meal is available' not in temporaryResponse:
            if startText:
                startText += ' there is '
            else:
                startText += 'There is '
        else:
            startText += ' '
            temporaryResponse= temporaryResponse[0].lower() + temporaryResponse[1:]
            
        startText += (temporaryResponse + '.')
        responsedata['followupEventInput']['parameters']['Data'] = startText
    
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
    meal_in = req_data['queryResult']['parameters']['Meal']
    
    if req_data['queryResult']['parameters']['Date']:
        date_in = (req_data['queryResult']['parameters']['Date'])[:10]
        dateEntered = True
    else:
        date_in = datetime.date.today()
        dateEntered = False

    text = similarSearch(loc_in, 'Location')
    if text == 'Found':
        outputParams['Data'] = requestItem(date_in, loc_in,
                                           req_data['queryResult']['parameters']['Item'], meal_in)['fulfillmentText']
        if dateEntered and req_data['queryResult']['outputContexts'][0]['parameters']['Date.original']:
            Date_original = req_data['queryResult']['outputContexts'][0]['parameters']['Date.original']

            outputParams['Data'] = (outputParams['Data'])[:-1]
            if Date_original.lower() == 'yesterday' or Date_original.lower() == 'tomorrow' or Date_original.lower() == 'today':
                outputParams['Data'] += (' ' + Date_original + '.')
            else:
                outputParams['Data'] += (' on ' + Date_original + '.')

                
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
