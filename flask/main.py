from functools import wraps
from flask import Flask, request, jsonify, Response, abort
import json, requests, urllib.parse,urllib.request
import filecmp, difflib, shutil
import numpy as np
from google.cloud import datastore
import datetime
from remove_ignore_entities import removeIgnoreEntities
from datahandle import requestLocationAndMeal, requestItem, formatPlural, formatRequisites

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
    if outputParams == {}:
        return responsedata
    
    if 'followupEventInput' in responsedata:
        responsedata['followupEventInput']['parameters'].update(outputParams)
    else:
        responsedata['followupEventInput'] = {
            'name': 'queryHelperEvent',
            'parameters': outputParams
        }
    return responsedata

def requisitesSetup(requisites, inputParams, outputParams, additionalOutputParams):
    """If any requisities specified in context parameters, extracts them and adds them to ``outputParams`` to remember for next query. 

    :param requisites: Contains information food item must comply with (traits, allergens, etc)
    :type requisites: dict
    :param inputParams: Input context paramaters containing user specifications
    :type inputParams: dict
    :param outputParams: Output context paramaters to send to queryHelper
    :type outputParams: dict
    :param additionalOutputParams: Additional remembered context paramaters containing user specifications from previous query if needed
    :type additionalOutputParams: dict
    """
    #Adds trait to requisites if specified
    if inputParams['itemTrait'] == [] and 'itemTraitOutputContext' in additionalOutputParams:
        requisites['trait'] = additionalOutputParams['itemTraitOutputContext']
    else:
        requisites['trait'] = inputParams['itemTrait']
        
    #Adds allergens to requisites if specified
    if inputParams['itemAllergens'] == [] and 'itemAllergensOutputContext' in additionalOutputParams:
        requisites['allergens'] = additionalOutputParams['itemAllergensOutputContext']
    else:
        requisites['allergens'] = inputParams['itemAllergens']

    if 'nuts' in requisites['allergens']:
        requisites['allergens'].remove('nuts')
        requisites['allergens'].append('tree-nuts')
        requisites['allergens'].append('peanuts')

    #Adds requisites to outputParams if specified    
    if requisites['trait']:
        outputParams['itemTraitOutputContext'] = requisites['trait']
    if requisites['allergens']:
        outputParams['itemAllergensOutputContext'] = requisites['allergens']

    return requisites, inputParams, outputParams, additionalOutputParams

def requiredEntitiesHandler(req_data, intentname):
    """Handles response for intents with 2 or more entities that are required and need to be handled manually, returns approriate parameters for specific intent handler to take care of.
       Will return list of entities in Data paramater of responsedata if all input parameters were valid, or a string response in the Data parameter containing response of issue to user.

    :param req_data: The HTTP response data
    :type req_data: dict
    :param intentname: Output context paramaters to send to queryHelper
    :type intentname: string
    """
    class Entity:
        def __init__(self, name, output_context, question):
            self.name = name
            self.output_context = output_context
            self.question = question
            
    if intentname == 'findLocationAndMeal':
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
        outputParams['Data'] = []
        for entity in entityInputs:
            outputParams['Data'].append(entity)
        responsedata = addFollowupEventInput(responsedata, outputParams)

    return responsedata
    
def findLocationAndMeal(req_data):
    """Dialogflow ``findLocationAndMeal`` intent handler. Checks for valid Location and Meal and sends HTTP response with appropriate data.

    :param req_data: Dialogflow POST request data
    :type req_data: dict
    """

    inputParams = req_data['queryResult']['parameters']
    additionalOutputParams = req_data['queryResult']['outputContexts'][0]['parameters']
    outputParams = {}
    requisites = {'trait': [], 'allergens': []}

    #Check if date entered: if not, assume today    
    if inputParams['Date']:
        date_in = (inputParams['Date'])[:10]
        dateEntered = True
    else:
        date_in = datetime.date.today()
        dateEntered = False

    #Set up requisites
    requisites, inputParams, outputParams, additionalOutputParams = requisitesSetup(requisites, inputParams, outputParams, additionalOutputParams)
    
    startText = ''
    temporaryResponse = ''
    
    responsedata = requiredEntitiesHandler(req_data, 'findLocationAndMeal')
    responsedata = addFollowupEventInput(responsedata, outputParams)
    
    data = responsedata['followupEventInput']['parameters']['Data']

    #If data parameter has list of entities (valid user request), retrieve data and formulate response
    if type(data) is list:
        temporaryResponse = requestLocationAndMeal(date_in,data[0],data[1], requisites)
        if temporaryResponse == '':
            temporaryResponse = 'No meal is available'

        temporaryResponse = formatRequisites(temporaryResponse, requisites)

        #If date specified, adds it to end of response text to data for more holistic response
        if dateEntered and additionalOutputParams['Date.original']:
            Date_original = additionalOutputParams['Date.original']

            informalDateTypesCheck = ['next' in Date_original.lower(), 'this' in Date_original.lower(),
                         Date_original.lower() == 'yesterday', Date_original.lower() == 'tomorrow',
                         Date_original.lower() == 'today']
            if any(informalDateTypesCheck):
                startText += (Date_original[0].upper() + Date_original[1:])
                
            else:
                startText += ('On ' + Date_original)

        #Linguistic semantics if no meal returned
        if 'No meal is available' in temporaryResponse:
            if startText:
                startText += ' '
                temporaryResponse=  temporaryResponse[0].lower() + temporaryResponse[1:]
        else:
            if startText:
                startText += ' there is '
            else:
                startText += 'There is '

        responsedata['followupEventInput']['parameters']['Data'] = startText + temporaryResponse + '.'

    #Else (invalid user request), response text in Data parameter contains error handling taken care of by requiredEntitiesHandler
    
    return responsedata

#findItem intent handling
def findItem(req_data):
    """Dialogflow ``findItem`` intent handler. Checks for valid Location and Item and sends HTTP response with appropriate data.

    :param req_data: Dialogflow POST request data
    :type req_data: dict
    """
    
    inputParams = req_data['queryResult']['parameters']
    additionalOutputParams = req_data['queryResult']['outputContexts'][0]['parameters']
    outputParams = {}
    requisites = {'trait': [], 'allergens': []}
    responsedata = {}
    
    loc_in = inputParams['Location']
    item_in = inputParams['Item']
    meal_in = inputParams['Meal']

    #Set up requisites
    requisites, inputParams, outputParams, additionalOutputParams = requisitesSetup(requisites, inputParams, outputParams, additionalOutputParams)


    #Check if date entered: if not, assume today
    if inputParams['Date']:
        date_in = (inputParams['Date'])[:10]
        dateEntered = True
    else:
        date_in = datetime.date.today()
        dateEntered = False

    #Check if Location valid
    text = similarSearch(loc_in, 'Location')
    if text == 'Found':

        #Setup 'Data' output context parameter with appropriate gathered data to send to queryHelper intent
        temporaryResponse = requestItem(date_in, loc_in, inputParams['Item'], meal_in, requisites)['fulfillmentText']
        outputParams['Data'] = formatRequisites(temporaryResponse, requisites)

        #Include date in response if specified
        if dateEntered and additionalOutputParams['Date.original']:
            Date_original = additionalOutputParams['Date.original']

            if Date_original.lower() == 'yesterday' or Date_original.lower() == 'tomorrow' or Date_original.lower() == 'today':
                outputParams['Data'] += (' ' + Date_original + '.')
            else:
                outputParams['Data'] += (' on ' + Date_original + '.')

        else:
            outputParams['Data'] += '.'
        
        outputParams['LocationOutputContext'] = loc_in
        responsedata = addFollowupEventInput(responsedata, outputParams)

    #If Location invalid, output appropiate response
    else:
        outputParams['Data'] = text
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
