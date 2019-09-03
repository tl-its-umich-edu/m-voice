import requests
from google.cloud import datastore
import google.cloud.logging

###Helper functions

def report_error(error_text):
    """Logs error to Stackdriver.
    :param error_text: The text to log to Stackdriver
    :type error_text: string
    """
    client = google.cloud.logging.Client()
    logger = client.logger("automated_error_catch")
    logger.log_text(error_text)

def get_secrets():
    """Fetches secrets from Datastore and returns them as a list.
    """
    client = datastore.Client()
    query = client.query(kind='env_vars')
    entity = query.fetch()
    secrets = list(entity)[0]
    return secrets

def format_requisites(text, requisites):
    """If any item requisites specified, adds them to response text data for more holistic response.

    :param text: The response text data to be formatted
    :type text: string
    :param requisites: Contains information food item must comply with (traits, allergens, etc)
    :type requisites: dict
    """
    traits_text = ''
    allergens_text = ''

    req_map = {'trait': {'mhealthy': 'healthy'},
               'allergens': {'sesame-seed': 'sesame seeds',
                             'tree-nuts': 'tree nuts',
                             'wheat_barley_rye': 'wheat or barley or rye'}}

    #If traits specified, extract into a string
    for i, trait in enumerate(requisites['trait']):
        if traits_text:
            traits_text += ', '
        traits_text += req_map['trait'].get(trait, trait)
    traits_text = format_plural(traits_text.rstrip(', '))

    #If allergens specified, extract into a string
    for i, allergen in enumerate(requisites['allergens']):
        if allergens_text:
            allergens_text += ', '
        allergens_text += req_map['allergens'].get(allergen, allergen)
    allergens_text = format_plural(allergens_text.rstrip(', '))
    allergens_text = allergens_text.replace('and', 'or')

    #Requisite-specific language
    if allergens_text:
        allergens_text = ' without ' + allergens_text
    if traits_text:
        traits_text = ' that is ' + traits_text

    #Return combined string
    if (allergens_text or traits_text) and 'Sorry, that is not available' in text:
        traits_text = traits_text.replace(' that is ', '')
        text = text.replace('Sorry, ', 'Sorry, ' + traits_text + ' ')
        text = text.replace('that is not available', '[meal]')
        return text + allergens_text + ' is not available'
    else:
        return text + traits_text + allergens_text

def format_plural(text):
    """Adds 'and' before last item in list of items.

    :param text: The string to be manipulated
    :type text: string
    """
    if ',' in text:
        index = text.rfind(',')  + 2
        text = text[:index] + 'and ' + text[index:]
    return text

def remove_spaces(url_block):
    """Removes spaces in url string to create valid url string.

    :param url_block: The url string to be manipulated
    :type search: string
    """
    temp = ""
    for i in range(len(url_block)):
        if url_block[i] == ' ':
            temp += '+'
        else:
            temp += url_block[i]
    return temp

def check_meal_available(data, meal):
    """Searches response data to check if meal is available at specified location/date.

    :param data: MDining API HTTP response data
    :type data: dict
    :param meal: Name of meal
    :type meal: string
    """
    for key in data['menu']['meal']:
        if data['menu']['meal']['name'].upper() == meal.upper():
            if 'course' in data['menu']['meal']:
                return True
            return False
    return False

def check_course_available(data, course):
    """Searches response data to check if course is available in specified meal.

    :param data: MDining API HTTP response data
    :type data: dict
    :param course: Name of course
    :type course: string
    """
    for i in range(len(data['menu']['meal']['course'])):
        for key, value in data['menu']['meal']['course'][i].items():
            if key == 'name':
                if value.upper() == course.upper():
                    return True
    return False



def check_item_specifications(item, traits, allergens):
    """Returns true if food item is satisfactory with specified traits and allergens.

    :param item: Data of specific food item
    :type item: dict
    :param traits: List of specified traits item must have, can be empty
    :type traits: list
    :param allergens: List of allergens item cannot have, can be empty
    :type allergens: list
    """
    #Return false if allergens list isn't empty and any allergens found
    if allergens and 'allergens' in item:
        for allergen in allergens:
            if allergen in item['allergens']:
                return False

    #Return true if traits list empty
    if not traits:
        return True

    #Return false if traits list isn't empty and any traits are missing
    if 'trait' in item:
        for trait in traits:
            if trait not in item['trait']:
                return False

        #All traits found, return true
        return True
    else:
        return False

def get_items(data, requisites, formatted):
    """Returns string of food items of each course in response data for
       fulfillmentText in response to Dialogflow.

    :param data: MDining API HTTP response data
    :type data: dict
    :param requisites: Contains information food item must comply with (traits, allergens, etc)
    :type requisites: dict
    :param formatted: True/False - formats response string if true
    :type formatted: boolean
    """
    returndata = ""
    traits = requisites['trait']
    allergens = requisites['allergens']

    if formatted:
        prefix = '\t'
        suffix = '\n'
    else:
        prefix = ''
        suffix = ', '

    for course in data['menu']['meal']['course']:
        item_data = []
        datatype = type(course['menuitem'])

        if datatype is list:
            item_data += course['menuitem']
        else:
            item_data.append(course['menuitem'])

        for item in item_data:
            if check_item_specifications(item, traits, allergens) and 'No Service at this Time' not in item['name']:
                returndata += (prefix + (item['name']).rstrip(', ') + suffix)

    return returndata

def find_item_formatting(possible_matches):
    """Formatting list of possible matches into more natural sentence structure
       by removing redundancy:
       [Chicken during lunch, chicken wings during lunch, and chicken patty during dinner] ->
       [Chicken, chicken wings during lunch, and chicken patty during dinner]

    :param possible_matches: List of food items in data that matched user input
    :type possible_matches: list
    """
    for i in range(len(possible_matches)):
        if i == 0:
            continue
        words = possible_matches[i].split()

        #If previous term has same ending ("Dinner") as current term, remove it
        if possible_matches[i].split()[-1] == possible_matches[i - 1].split()[-1]:
            #8 = amount of characters taken up by [' during ']
            length = len(possible_matches[i].split()[-1]) + 8
            possible_matches[i - 1] = possible_matches[i - 1][:length*-1]

    return possible_matches


def find_matches(course_data, possible_matches, item_in, meal_name, requisites):
    """Appends matches of specified food item in data of an individual course to
       list of possible matches.

    :param course_data: Chosen course subsection of MDining API HTTP response data
    :type course_data: dict
    :param possible_matches: List of food items in data that matched user input
    :type possible_matches: list
    :param item_in: User input food item
    :type item_in: string
    :param meal_name: Name of meal
    :type meal_name: string
    :param requisites: Contains information food item must comply with (traits, allergens, etc)
    :type requisites: dict
    """

    traits = requisites['trait']
    allergens = requisites['allergens']

    item_data = []
    datatype = type(course_data)

    if datatype is list:
        item_data += course_data
    else:
        item_data.append(course_data)

    for item in item_data:
        if check_item_specifications(item, traits, allergens) == False:
            continue
        if item_in.upper() in item['name'].upper():
            if item['name'][-1] == ' ':
                item['name'] = item['name'][:-1]

            possible_matches.append(item['name'] + ' during ' + meal_name)

    return possible_matches



#########################################################################
###Primary Handler Functions


def request_location_and_meal(date_in, loc_in, meal_in, requisites):
    """Handles searching for appropriate data response for valid specified
       location and meal entities from ``findLocationAndMeal`` intent.

    :param date_in: Input date
    :type date_in: string
    :param loc_in: Input location
    :type loc_in: string
    :param meal_in: Input meal
    :type meal_in: string
    :param requisites: Contains information food item must comply with (traits, allergens, etc)
    :type requisites: dict
    """

    #preset vars
    url = 'http://api.studentlife.umich.edu/menu/xml2print.php?controller=&view=json'
    location = '&location='
    date = '&date='
    meal = '&meal='

    #API url concatenation
    location += loc_in
    meal += meal_in
    date += str(date_in)
    url = url + location + date + meal
    url = remove_spaces(url)

    #fetching json
    data = requests.get(url).json()

    #checking if specified meal available
    if check_meal_available(data, meal_in):
        returnstring = (get_items(data, requisites, False)).rstrip(', ')
        return format_plural(returnstring)
    else:
        return "No meal is available"

#Handle meal item data request
def request_item(date_in, loc_in, item_in, meal_in, requisites):
    """Handles searching for appropriate data response for valid specified
       location and food item entities (and meal entity if included) from ``findItem`` intent.

    :param date_in: Input date
    :type date_in: string
    :param loc_in: Input location
    :type loc_in: string
    :param item_in: Input food item
    :type item_in: string
    :param meal_in: Input meal, can be empty string if not specified
    :type meal_in: string
    :param requisites: Contains information food item must comply with (traits, allergens, etc)
    :type requisites: dict
    """
    secrets = get_secrets()
    url = secrets.get('m_dining_api_main')
    location = '&location='
    date = '&date='
    meal = '&meal='

    #API url concatenation
    location += loc_in
    date += str(date_in)
    url = url + location + date + meal
    url = remove_spaces(url)

    if meal_in == '':
        meal_entered = False
    else:
        meal_entered = True

    #fetching json
    data = requests.get(url).json()

    possible_matches = []

    #Loop through meals
    for i in data['menu']['meal']:

        #If meal specified, only check specified meal
        if meal_entered and i['name'].upper() != meal_in.upper():
            continue
        #Skip meal if no food items available
        if 'course' not in i:
            continue

        #Loop through food items in course
        for j in i['course']:
            for key, value in j.items():
                if key == 'name':
                    course_data = j['menuitem']
                    meal_name = i['name']
                    #Append matches to specified item to possible_matches list
                    possible_matches = find_matches(course_data, possible_matches,
                                                    item_in, meal_name, requisites)
    
    #Specified item found
    if possible_matches:
        possible_matches = find_item_formatting(possible_matches)
        text = 'Yes, there is '
        for i in range(len(possible_matches)):
            if len(possible_matches) > 1 and (i == len(possible_matches) - 1):
                text += ' and'
            text += ' ' + possible_matches[i]
            if i != len(possible_matches) - 1:
                text += ','

    #Specified item not found
    else:
        text = 'Sorry, that is not available'


    return {'fulfillmentText': text}
