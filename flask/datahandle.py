import urllib.parse
import requests
import urllib.request


###Helper functions


def formatItem(item):
    """Removes excess ending spaces/commas.

    :param item: The string to be manipulated
    :type item: string
    """
    while(item[-1] == ' ' or item[-1] == ','):
      item = item[:-1]
    return item

def formatPlural(text):
    """Adds 'and' before last item in list of items.

    :param text: The string to be manipulated
    :type text: string
    """
    if ',' in text:
        for i in range(len(text)):
            if i == 0:
                continue
            if text[(len(text) - i)] == ',':
                text = text[:(len(text) - i) + 2] + 'and ' + text[(len(text) - i) + 2:]
                break
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
    :type data: JSON
    :param meal: Name of meal
    :type meal: string
    """
    for key in data['menu']['meal']:
        if data['menu']['meal']['name'].upper() == meal.upper():
            if 'course' in data['menu']['meal']:
                #print('Found')
                return True
            #print('Not found')
            #print(data['menu']['meal']['message']['content'])
            return False

def checkCourseAvailable(data, course):
    """Searches response data to check if course is available in specified meal.

    :param data: MDining API HTTP response data
    :type data: JSON
    :param course: Name of course
    :type course: string
    """
    for i in range(len(data['menu']['meal']['course'])):
        for key, value in data['menu']['meal']['course'][i].items():
            if key == 'name':
                if value.upper() == course.upper():
                    return True
    return False

#Gets food items of specified valid course
def getItemsInCourse(coursedata, course, formatted):
    """Returns string of food items of specified valid course in response data for fulfillmentText in response to Dialogflow.

    :param coursedata: Chosen course subsection of MDining API HTTP response data
    :type coursedata: JSON
    :param course: Name of course
    :type course: string
    :param formatted: True/False - formats response string if true
    :type formatted: boolean
    """
    returndata = ""

    if formatted:
        prefix = '\t'
        suffix = '\n'
    else:
        prefix = ''
        suffix = ', '        
    for i in range(len(coursedata)):
        datatype = type(coursedata[i]['menuitem'])
        
        if coursedata[i]['name'].upper() == course.upper():
            if datatype is list:
                for j in range(len(coursedata[i]['menuitem'])):
                    returndata += (prefix + formatItem(coursedata[i]['menuitem'][j]['name']) + suffix)
            elif datatype is dict:
                if 'No Service at this Time' not in coursedata[i]['menuitem']['name']:
                    returndata += (prefix + formatItem(coursedata[i]['menuitem']['name']) + suffix)
    return returndata

def getCoursesAndItems(data, formatted):
    """Returns string of courses and food items of each course in response data for fulfillmentText in response to Dialogflow.

    :param data: MDining API HTTP response data
    :type data: JSON
    :param formatted: True/False - formats response string if true
    :type formatted: boolean
    """
    returndata = ""
    for i in range(len(data['menu']['meal']['course'])):
        for key, value in data['menu']['meal']['course'][i].items():
            if key == 'name':
                if(checkCourseAvailable(data,value)):
                    returndata += ('Items in ' + value + ' course:\n')

                    returndata += getItemsInCourse(data['menu']['meal']['course'], value, formatted)
    return returndata

def getItems(data, formatted):
    """Returns string of courses and food items of each course in response data for fulfillmentText in response to Dialogflow.

    :param data: MDining API HTTP response data
    :type data: JSON
    :param formatted: True/False - formats response string if true
    :type formatted: boolean
    """
    returndata = ""
    for i in range(len(data['menu']['meal']['course'])):
        for key, value in data['menu']['meal']['course'][i].items():
            if key == 'name':
                if(checkCourseAvailable(data,value)):
                    returndata += getItemsInCourse(data['menu']['meal']['course'], value, formatted)
    return returndata

def findItemFormatting(possiblematches):
    """Formatting list of possible matches into more natural sentence structure by removing redundancy:
    [Chicken during lunch, chicken wings during lunch, and chicken patty during dinner] -> [Chicken, chicken wings during lunch, and chicken patty during dinner]
    
    :param possiblematches: List of food items in data that matched user input
    :type possiblematches: list
    """
    for i in range(len(possiblematches)):
        if i == 0:
            continue
        words = possiblematches[i].split()
        
        #If previous term has same ending ("Dinner") as current term, remove it
        if(possiblematches[i].split()[-1] == possiblematches[i - 1].split()[-1]):
            #8 = amount of characters taken up by [' during ']
            length = len(possiblematches[i].split()[-1]) + 8
            possiblematches[i - 1] = possiblematches[i - 1][:length*-1]
            
    return possiblematches


def findMatches(coursedata, possiblematches, item_in, mealname):
    """Appends matches of specified food item in data of an individual course to list of possible matches.

    :param coursedata: Chosen course subsection of MDining API HTTP response data
    :type coursedata: JSON
    :param possiblematches: List of food items in data that matched user input
    :type possiblematches: list
    :param item_in: User input food item
    :type item_in: string
    :param mealname: Name of meal
    :type mealname: string
    """
    datatype = type(coursedata)

    if datatype is list:
        for k in range(len(coursedata)):
            if item_in.upper() in coursedata[k]['name'].upper():
                if coursedata[k]['name'][-1] == ' ':
                    coursedata[k]['name'] = coursedata[k]['name'][:-1]
                    
                possiblematches.append(coursedata[k]['name'] + ' during ' + mealname)

    elif datatype is dict:
        if item_in.upper() in coursedata['name'].upper():
            if coursedata['name'][-1] == ' ':
                coursedata['name'] = coursedata['name'][:-1]
                
            possiblematches.append(coursedata['name'] + ' during ' + mealname)    

    return possiblematches



#########################################################################
###Primary Handler Functions


def requestLocationAndMeal(date_in, loc_in, meal_in):
    """Handles searching for appropriate data response for valid specified location and meal entities from ``findLocationAndMeal`` intent.

    :param date_in: Input date
    :type date_in: string
    :param loc_in: Input location
    :type loc_in: string
    :param meal_in: Input meal
    :type meal_in: string
    """
    #date_in='2019-05-15'
    
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
        return formatPlural(formatItem(getItems(data, False)))
    else:
        return "No meal is available."

#Handle meal item data request
def requestItem(date_in, loc_in, item_in, meal_in):
    """Handles searching for appropriate data response for valid specified location and food item entities (and meal entity if included) from ``findItem`` intent.

    :param date_in: Input date
    :type date_in: string
    :param loc_in: Input location
    :type loc_in: string
    :param item_in: Input food item
    :type item_in: string
    :param meal_in: Input meal, can be empty string if not specified
    :type meal_in: string
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
    
    possiblematches = []
    
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
                    coursedata = j['menuitem']
                    mealname = i['name']
                    #Append matches to specified item to possiblematches list
                    possiblematches = findMatches(coursedata, possiblematches, item_in, mealname)
         
    #Specified item found
    if len(possiblematches) > 0:
        possiblematches = findItemFormatting(possiblematches)   
        text = 'Yes, there is '
        for i in range(len(possiblematches)):
            if len(possiblematches) > 1 and (i == len(possiblematches) - 1):
                text += ' and'
            text += ' ' + possiblematches[i]
            if i != len(possiblematches) - 1:
                text += ','
            else:
                text += '.'
    #Specified item not found
    else:
        text = 'Sorry, that is not available.'

    
    return { 'fulfillmentText': text}

