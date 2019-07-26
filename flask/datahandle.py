import urllib.parse
import requests
import urllib.request


###Helper functions

def formatRequisites(text, requisites):
    """If any item requisites specified, adds them to response text data for more holistic response.

    :param text: The response text data to be formatted
    :type texta: string
    :param requisites: Contains information food item must comply with (traits, allergens, etc)
    :type requisites: dict
    """
    traitsText = ''
    allergensText = ''

    #If traits specified, extract into a string
    for trait in requisites['trait']:
        if traitsText:
            traitsText += ', '
        if trait == 'mhealthy':
            trait = 'healthy'
        traitsText += trait
    traitsText = formatPlural(traitsText.rstrip(', '))

    #If allergens specified, extract into a string
    for allergen in requisites['allergens']:
        if allergensText:
            allergensText += ', '
        if allergen == 'sesame-seed':
            allergen = 'sesame seeds'
        elif allergen == 'tree-nuts':
            allergen = 'tree nuts'
        elif allergen == 'wheat_barley_rye':
            allergen = 'wheat or barley or rye'
        allergensText += allergen
    allergensText = formatPlural(allergensText.rstrip(', '))
    allergensText = allergensText.replace('and','or')

    #Requisite-specific language
    if allergensText:
        allergensText = ' without ' + allergensText
    if traitsText:
        traitsText = ' that is ' + traitsText
        
    #Return combined string
    if (allergensText or traitsText) and 'Sorry, that is not available' in text:
        text = text.replace('that is not available', 'a meal')
        return text + traitsText + allergensText + ' is not available'
    else:
        return text + traitsText + allergensText

def formatPlural(text):
    """Adds 'and' before last item in list of items.

    :param text: The string to be manipulated
    :type text: string
    """
    if ',' in text:
      index = text.rfind(',')  + 2
      text = text[:index] + 'and ' + text[index:]
    return text

def removeSpaces(url_block):
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

def checkMealAvailable(data, meal):
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

def checkCourseAvailable(data, course):
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



def checkItemSpecifications(item, traits, allergens):
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
                #print(allergen + ' in ' + item['name'])
                return False

    #Return true if traits list empty
    if not traits:
        return True

    #Return false if traits list isn't empty and any traits are missing
    if 'trait' in item:
        for trait in traits:
            if trait not in item['trait']:
                #print(trait + ' not in ' + item['name'])
                return False

        #All traits found, return true
        return True
    else:
        #print('No traits found')
        return False

def getItems(data, requisites, formatted):
    """Returns string of food items of each course in response data for fulfillmentText in response to Dialogflow.

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
        itemData = []
        datatype = type(course['menuitem'])
        
        if datatype is list:
            itemData += course['menuitem']
        else:
            itemData.append(course['menuitem'])

        for item in itemData:
            if checkItemSpecifications(item, traits, allergens) and 'No Service at this Time' not in item['name']:
                returndata += (prefix + (item['name']).rstrip(', ') + suffix)
        
    return returndata

def findItemFormatting(possibleMatches):
    """Formatting list of possible matches into more natural sentence structure by removing redundancy:
    [Chicken during lunch, chicken wings during lunch, and chicken patty during dinner] -> [Chicken, chicken wings during lunch, and chicken patty during dinner]
    
    :param possibleMatches: List of food items in data that matched user input
    :type possibleMatches: list
    """
    for i in range(len(possibleMatches)):
        if i == 0:
            continue
        words = possibleMatches[i].split()
        
        #If previous term has same ending ("Dinner") as current term, remove it
        if(possibleMatches[i].split()[-1] == possibleMatches[i - 1].split()[-1]):
            #8 = amount of characters taken up by [' during ']
            length = len(possibleMatches[i].split()[-1]) + 8
            possibleMatches[i - 1] = possibleMatches[i - 1][:length*-1]
            
    return possibleMatches


def findMatches(courseData, possibleMatches, item_in, mealName, requisites):
    """Appends matches of specified food item in data of an individual course to list of possible matches.

    :param courseData: Chosen course subsection of MDining API HTTP response data
    :type courseData: dict
    :param possibleMatches: List of food items in data that matched user input
    :type possibleMatches: list
    :param item_in: User input food item
    :type item_in: string
    :param mealName: Name of meal
    :type mealName: string
    :param requisites: Contains information food item must comply with (traits, allergens, etc)
    :type requisites: dict
    """

    traits = requisites['trait']
    allergens = requisites['allergens']

    itemData = []
    datatype = type(courseData)
    
    if datatype is list:
        itemData += courseData
    else:
        itemData.append(courseData)

    for item in itemData:
        if checkItemSpecifications(item, traits, allergens) == False:
            continue
        if item_in.upper() in item['name'].upper():
            if item['name'][-1] == ' ':
                item['name'] = item['name'][:-1]
                
            possibleMatches.append(item['name'] + ' during ' + mealName)

    return possibleMatches



#########################################################################
###Primary Handler Functions


def requestLocationAndMeal(date_in, loc_in, meal_in, requisites):
    """Handles searching for appropriate data response for valid specified location and meal entities from ``findLocationAndMeal`` intent.

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
    url = removeSpaces(url)
    
    #fetching json
    data = requests.get(url).json()
    
    #checking if specified meal available
    if checkMealAvailable(data, meal_in):
        returnstring = (getItems(data, requisites, False)).rstrip(', ')
        return formatPlural(returnstring)
    else:
        return "No meal is available"

#Handle meal item data request
def requestItem(date_in, loc_in, item_in, meal_in, requisites):
    """Handles searching for appropriate data response for valid specified location and food item entities (and meal entity if included) from ``findItem`` intent.

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
    url = 'http://api.studentlife.umich.edu/menu/xml2print.php?controller=&view=json'
    location = '&location='
    date = '&date='
    meal = '&meal='

    #API url concatenation
    location += loc_in
    date += str(date_in)
    url = url + location + date + meal
    url = removeSpaces(url)

    if meal_in == '':
        mealEntered = False
    else:
        mealEntered = True
    
    #fetching json
    data = requests.get(url).json()
    
    possibleMatches = []
    
    firstRound = True
    
    #Loop through meals
    for i in data['menu']['meal']:
        
        #If meal specified, only check specified meal
        if mealEntered and i['name'].upper() != meal_in.upper():
            continue
        #Skip meal if no food items available
        if 'course' not in i:
            continue

        #Loop through food items in course
        for j in i['course']:
            for key, value in j.items():
                if key == 'name':
                    courseData = j['menuitem']
                    mealName = i['name']
                    #Append matches to specified item to possibleMatches list
                    possibleMatches = findMatches(courseData, possibleMatches, item_in, mealName, requisites)
         
    #Specified item found
    if len(possibleMatches) > 0:
        possibleMatches = findItemFormatting(possibleMatches)   
        text = 'Yes, there is '
        for i in range(len(possibleMatches)):
            if len(possibleMatches) > 1 and (i == len(possibleMatches) - 1):
                text += ' and'
            text += ' ' + possibleMatches[i]
            if i != len(possibleMatches) - 1:
                text += ','

    #Specified item not found
    else:
        text = 'Sorry, that is not available'

    
    return { 'fulfillmentText': text}

