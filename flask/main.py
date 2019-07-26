from functools import wraps
import datetime
import json, requests
import numpy as np
from flask import Flask, request, jsonify, abort
from google.cloud import datastore
from datahandle import request_location_and_meal, request_item, format_requisites

app = Flask(__name__)

###Helper functions

#Authentication
def check_auth(name, passw):
    return name == 'user' and passw == 'pass'
def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            abort(401)
        return f(*args, **kwargs)
    return decorated

def remove_ignore_entities(data, category):
    """Removes entity terms to be ignored found in ``ignore.json``
       when comparing current local data and potentially updated MDining API data.

    :param data: List of items in current version of specified entity
    :type data: list
    :param category: Entity category of the search term ('Location'/'Meal')
    :type category: string
    """
    with open('ignore.json') as file:
        ignoredata = json.load(file)
    newdata = []
    for term in data:
        copy = True
        for ignoreterm in ignoredata[category]:
            if term.strip('\n') == ignoreterm:
                copy = False
        if copy:
            newdata.append(term)
    return newdata

def is_partial_term(search, filename):
    """Checks if input term is part of a larger official term by looking for any matches with
       split up versions of regular terms.

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

def similar_search(search, category):
    """Handles user input that doesn't match official terms exactly using `is_partial_term`.
       If input ``search`` is a partial term of any official terms,
       returns list of recommended official terms.

    :param search: The searched term (e.g. 'north quad')
    :type search: string
    :param category: Entity category of the search term ('Location'/'Meal')
    :type filename: string
    """

    #Check type of term and adjust file searched accordingly
    if category.upper() == 'LOCATION':
        extras_filename = 'LocationExtra.txt'
        main_filename = 'LocationMain.txt'
    elif category.upper() == 'MEAL':
        extras_filename = 'MealExtra.txt'
        main_filename = 'MealMain.txt'
    else:
        return "File error"

    #Check if input term is part of a larger official term
    if is_partial_term(search, extras_filename) == False:
        return "Found"

    #If it is, suggest possible full terms

    #Go through list of full terms and check for possibilities
    list_data = open(main_filename, 'r')
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

def add_followup_event_input(responsedata, output_params):
    """Helper function for adding followupEventInput trigger to send data to queryHelper intent.

    :param responsedata: The HTTP response data
    :type responsedata: dict
    :param output_params: Output context paramaters to send to queryHelper
    :type output_params: dict
    """
    if output_params == {}:
        return responsedata

    if 'followupEventInput' in responsedata:
        responsedata['followupEventInput']['parameters'].update(output_params)
    else:
        responsedata['followupEventInput'] = {
            'name': 'queryHelperEvent',
            'parameters': output_params
        }
    return responsedata

def requisites_setup(requisites, input_params, output_params, additional_output_params):
    """If any requisities specified in context parameters,
       extracts them and adds them to ``output_params`` to remember for next query.

    :param requisites: Contains information food item must comply with (traits, allergens, etc)
    :type requisites: dict
    :param input_params: Input context paramaters containing user specifications
    :type input_params: dict
    :param output_params: Output context paramaters to send to queryHelper
    :type output_params: dict
    :param additional_output_params: Additional remembered context paramaters containing user
                                     specifications from previous query if needed
    :type additional_output_params: dict
    """
    #Adds trait to requisites if specified
    if input_params['itemTrait'] == [] and 'itemTraitOutputContext' in additional_output_params:
        requisites['trait'] = additional_output_params['itemTraitOutputContext']
    else:
        requisites['trait'] = input_params['itemTrait']

    #Adds allergens to requisites if specified
    if input_params['itemAllergens'] == [] and 'itemAllergensOutputContext' in additional_output_params:
        requisites['allergens'] = additional_output_params['itemAllergensOutputContext']
    else:
        requisites['allergens'] = input_params['itemAllergens']

    if 'nuts' in requisites['allergens']:
        requisites['allergens'].remove('nuts')
        requisites['allergens'].append('tree-nuts')
        requisites['allergens'].append('peanuts')

    #Adds requisites to output_params if specified
    if requisites['trait']:
        output_params['itemTraitOutputContext'] = requisites['trait']
    if requisites['allergens']:
        output_params['itemAllergensOutputContext'] = requisites['allergens']


    return {'requisites': requisites,
            'input_params': input_params,
            'output_params': output_params,
            'additional_output_params': additional_output_params}

def required_entities_handler(req_data, intentname):
    """Handles response for intents with 2 or more entities that are required and
       need to be handled manually,
       returns approriate parameters for specific intent handler to take care of.
       Will return list of entities in Data paramater of responsedata
       if all input parameters were valid,
       or a string response in the Data parameter containing response of issue to user.

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

    if intentname == 'find_location_and_meal':
        entities = [Entity('Location', 'LocationOutputContext', 'Which dining location?'),
                    Entity('Meal', 'MealOutputContext', 'Which meal of the day would you like?')]

    #Setting up variables
    input_params = req_data['queryResult']['parameters']
    additional_output_params = req_data['queryResult']['outputContexts'][0]['parameters']


    output_params = {}
    responsedata = {}
    entity_inputs = []
    entity_search_responses = []
    valid_params = True
    ready_to_output = False

    for entity in entities:

        #If parameter is filled, check if valid
        if input_params[entity.name]:
            search = input_params[entity.name]
            text = similar_search(search, entity.name)

            #Parameter invalid
            if text != 'Found':
                valid_params = False
                if not ready_to_output:
                    output_params['Data'] = text
                    responsedata = add_followup_event_input(responsedata, output_params)
                    ready_to_output = True
            #Parameter valid
            else:
                entity_inputs.append(search)
                entity_search_responses.append(text)
                output_params[entity.name + 'OutputContext'] = search

        #If paramater unfilled, check if complementary output context parameter exists and is valid
        elif entity.output_context in additional_output_params:
            search = additional_output_params[entity.output_context]
            text = similar_search(search, entity.name)

            #Parameter invalid
            if text != 'Found':
                valid_params = False
                if not ready_to_output:
                    output_params['Data'] = text
                    responsedata = add_followup_event_input(responsedata, output_params)

            #Parameter valid
            else:
                entity_inputs.append(search)
                entity_search_responses.append(text)
                output_params[entity.name + 'OutputContext'] = search

        #If parameter is unfilled, request to be filled
        else:
            valid_params = False
            if not ready_to_output:
                output_params['Data'] = entity.question
                responsedata = add_followup_event_input(responsedata, output_params)
                ready_to_output = True

    #If parameters filled and valid, return data
    if valid_params:
        output_params['Data'] = []
        for entity in entity_inputs:
            output_params['Data'].append(entity)
        responsedata = add_followup_event_input(responsedata, output_params)

    return responsedata

def find_location_and_meal(req_data):
    """Dialogflow ``find_location_and_meal`` intent handler.
       Checks for valid Location and Meal and sends HTTP response with appropriate data.

    :param req_data: Dialogflow POST request data
    :type req_data: dict
    """

    input_params = req_data['queryResult']['parameters']
    additional_output_params = req_data['queryResult']['outputContexts'][0]['parameters']
    output_params = {}
    requisites = {'trait': [], 'allergens': []}

    #Check if date entered: if not, assume today
    if input_params['Date']:
        date_in = (input_params['Date'])[:10]
        date_entered = True
    else:
        date_in = datetime.date.today()
        date_entered = False

    #Set up requisites
    requisites_setup_output = requisites_setup(requisites, input_params, output_params,
                                               additional_output_params)
    requisites = requisites_setup_output['requisites']
    input_params = requisites_setup_output['input_params']
    output_params = requisites_setup_output['output_params']
    additional_output_params = requisites_setup_output['additional_output_params']

    start_text = ''
    temporary_response = ''

    responsedata = required_entities_handler(req_data, 'find_location_and_meal')
    responsedata = add_followup_event_input(responsedata, output_params)

    data = responsedata['followupEventInput']['parameters']['Data']

    #If data parameter has list of entities (valid user request), retrieve data and create response
    if type(data) is list:
        temporary_response = request_location_and_meal(date_in, data[0], data[1], requisites)
        if temporary_response == '':
            temporary_response = 'No meal is available'

        temporary_response = format_requisites(temporary_response, requisites)

        #If date specified, adds it to end of response text to data for more holistic response
        if date_entered and additional_output_params['Date.original']:
            date_original = additional_output_params['Date.original']

            informal_date_types_check = ['next' in date_original.lower(), 'this' in date_original.lower(),
                                         date_original.lower() == 'yesterday', date_original.lower() == 'tomorrow',
                                         date_original.lower() == 'today']
            if any(informal_date_types_check):
                start_text += (date_original[0].upper() + date_original[1:])
            else:
                start_text += ('On ' + date_original)

        #Linguistic semantics if no meal returned
        if 'No meal is available' in temporary_response:
            if start_text:
                start_text += ' '
                temporary_response = temporary_response[0].lower() + temporary_response[1:]
        else:
            if start_text:
                start_text += ' there is '
            else:
                start_text += 'There is '

        responsedata['followupEventInput']['parameters']['Data'] = (start_text +
                                                                    temporary_response +
                                                                    '.').replace('  ', ' ')

    #Else (invalid user request),
    #response text in Data parameter contains error handling output from required_entities_handler

    return responsedata

def find_item(req_data):
    """Dialogflow ``find_item`` intent handler.
       Checks for valid Location and Item and sends HTTP response with appropriate data.

    :param req_data: Dialogflow POST request data
    :type req_data: dict
    """

    input_params = req_data['queryResult']['parameters']
    additional_output_params = req_data['queryResult']['outputContexts'][0]['parameters']
    output_params = {}
    requisites = {'trait': [], 'allergens': []}
    responsedata = {}

    loc_in = input_params['Location']
    item_in = input_params['Item']
    meal_in = input_params['Meal']

    #Set up requisites
    requisites_setup_output = requisites_setup(requisites, input_params, output_params,
                                               additional_output_params)
    requisites = requisites_setup_output['requisites']
    input_params = requisites_setup_output['input_params']
    output_params = requisites_setup_output['output_params']
    additional_output_params = requisites_setup_output['additional_output_params']

    #Check if date entered: if not, assume today
    if input_params['Date']:
        date_in = (input_params['Date'])[:10]
        date_entered = True
    else:
        date_in = datetime.date.today()
        date_entered = False

    #Check if Location valid
    text = similar_search(loc_in, 'Location')
    if text == 'Found':

        #Setup 'Data' output context parameter with appropriate gathered data to send to queryHelper intent
        temporary_response = request_item(date_in, loc_in, input_params['Item'], meal_in, requisites)['fulfillmentText']
        temporary_response = format_requisites(temporary_response, requisites)

        if '[meal]' in temporary_response:
            temporary_response = temporary_response.replace('[meal]', item_in.lower())
            if item_in[-1] == 's' and ' is ' in temporary_response:
                temporary_response = temporary_response.replace(' is ', ' are ')
        output_params['Data'] = temporary_response

        #Include date in response if specified
        if date_entered and additional_output_params['Date.original']:
            date_original = additional_output_params['Date.original']


            informal_date_types_check = ['next' in date_original.lower(), 'this' in date_original.lower(),
                                         date_original.lower() == 'yesterday', date_original.lower() == 'tomorrow',
                                         date_original.lower() == 'today']
            if any(informal_date_types_check):
                output_params['Data'] += (' ' + date_original + '.')
            else:
                output_params['Data'] += (' on ' + date_original + '.')

        else:
            output_params['Data'] += '.'

        output_params['Data'] = output_params['Data'].replace('  ', ' ')
        output_params['LocationOutputContext'] = loc_in
        responsedata = add_followup_event_input(responsedata, output_params)

    #If Location invalid, output appropiate response
    else:
        output_params['Data'] = text.replace('  ', ' ')
        responsedata = add_followup_event_input(responsedata, output_params)


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
@app.route('/webhook', methods=['POST'])
@requires_auth
def webhook_post():
    """Dialogflow webhook POST Request handler requiring authentication.
       Uses `find_location_and_meal` or `find_item` intent handlers and returns appropriate
       JSON response.
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
        responsedata = {'fulfillmentText': responsedata}
    elif 'findLocationAndMeal' in intentname:
        responsedata = find_location_and_meal(req_data)
    elif 'findItem' in intentname:
        responsedata = find_item(req_data)
    else:
        responsedata = {'fulfillmentText': 'Not available.'}

    return jsonify(responsedata)

#Google Cron update handler
@app.route('/cron', methods=['POST'])
def cron_update():
    """Google Cloud Platform scheduled CRON request handler.
       Checks for changes to MDining API data (Location/Meal),
       sends notification to Slack channel if change detected.
       Ignores changes to specified terms in ``ignore.json`` file.
       Authenticates requests by checking for user and passw in POST request body.
    """
    #Cron authentication through post request data
    req_data = request.get_json()

    #Get secret values from Datastore environment variables
    client = datastore.Client()
    query = client.query(kind='env_vars')
    entity = query.fetch()

    secrets = list(entity)[0]
    slackurl = secrets.get('slack_api')
    passw = secrets.get('pass')
    user = secrets.get('user')

    if (req_data['user'] != user) or (req_data['pass'] != passw):
        message = 'Authentication failed.'
    else:
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

        originalmeal = np.array(remove_ignore_entities(originalmeal, 'Meal'))
        newmeal = np.array(remove_ignore_entities(newmeal, 'Meal'))


        mealremoved = np.setdiff1d(originalmeal, newmeal).tolist()
        mealadded = np.setdiff1d(newmeal, originalmeal).tolist()
        mealchanged = False
        if bool(mealremoved) or bool(mealadded):
            mealchanged = True


        #Location Diff
        m_dining_url = 'http://api.studentlife.umich.edu/menu/menu_generator/location.php'
        locationreq = requests.post(m_dining_url)
        locationdata = locationreq.json()

        newlocation = []
        for entry in locationdata:
            if entry['optionValue'] != "":
                newlocation.append(entry['optionValue'])

        originallocationfile = open('LocationMain.txt', 'r').readlines()
        originallocation = []
        for entry in originallocationfile:
            originallocation.append(entry.strip('\n'))

        originallocation = np.array(remove_ignore_entities(originallocation, 'Location'))
        newlocation = np.array(remove_ignore_entities(newlocation, 'Location'))

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
                    slackresponse['attachments'].append({"title": "New locations",
                                                         "text": newlocationsstr})
                if bool(locationremoved):
                    removedlocationsstr = ''
                    for i in locationremoved:
                        removedlocationsstr = removedlocationsstr + i + '\n'
                    slackresponse['attachments'].append({"title": "Removed locations",
                                                         "text": removedlocationsstr})
            if mealchanged:
                if bool(mealadded):
                    newmealsstr = ''
                    for i in mealadded:
                        newmealsstr = newmealsstr + i + '\n'
                    slackresponse['attachments'].append({"title": "New meals",
                                                         "text": newmealsstr})
                if bool(mealremoved):
                    removedmealsstr = ''
                    for i in mealremoved:
                        removedmealsstr = removedmealsstr + i + '\n'
                    slackresponse['attachments'].append({"title": "Removed meals",
                                                         "text": removedmealsstr})
                if locationchanged:
                    message += " and meal"
                else:
                    message += "meal"

            message += " in m-voice."
            slackresponse['text'] = message
            requests.post(slackurl, json=slackresponse)

        else:
            message = "Data up to date"

    return jsonify(
        message=message,
        locationadded=locationadded,
        locationremoved=locationremoved,
        mealadded=mealadded,
        mealremoved=mealremoved
    )
