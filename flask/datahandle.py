import urllib.parse
import requests
import urllib.request


###Helper functions

#Removes spaces in url string
def removeSpaces(url_block):
    temp = ""
    for i in range(len(url_block)):
        if url_block[i] == ' ':
            temp += '+'
        else:
            temp += url_block[i]
    return temp

#Checks if meal is available at specified location/date
def checkMealAvailable(data,meal):
    for key in data['menu']['meal']:
        if data['menu']['meal']['name'].upper() == meal.upper():
            if 'course' in data['menu']['meal']:
                #print('Found')
                return True
            #print('Not found')
            #print(data['menu']['meal']['message']['content'])
            return False

#Checks if course is available in specified meal
def checkCourseAvailable(data, course):
    for i in range(len(data['menu']['meal']['course'])):
        for key, value in data['menu']['meal']['course'][i].items():
            if key == 'name':
                if value.upper() == course.upper():
                    return True
    return False

#Gets food items of specified valid course
def getItemsInCourse(coursedata, course):
    returndata = ""

    for i in range(len(coursedata)):
        datatype = type(coursedata[i]['menuitem'])
        
        if coursedata[i]['name'].upper() == course.upper():
            if datatype is list:
                for j in range(len(coursedata[i]['menuitem'])):
                    returndata += ('\t' + coursedata[i]['menuitem'][j]['name'] + '\n')
            elif datatype is dict:
                returndata += ('\t' + coursedata[i]['menuitem']['name'] + '\n')
    return returndata

#Gets courses and food items of each course
def getCoursesAndItems(data):
    returndata = ""
    for i in range(len(data['menu']['meal']['course'])):
        for key, value in data['menu']['meal']['course'][i].items():
            if key == 'name':
                if(checkCourseAvailable(data,value)):
                    returndata += ('Items in ' + value + ' course:\n')

                    returndata += getItemsInCourse(data['menu']['meal']['course'], value)
    return returndata

#Formatting list of possible matches into more natural sentence structure by removing redundancy
#[Chicken during lunch, chicken wings during lunch, and chicken patty during dinner] ->
    #[Chicken, chicken wings during lunch, and chicken patty during dinner]
def findItemFormatting(possiblematches):

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


#Find possible matches to specified food item
def findMatches(coursedata, possiblematches, item_in, mealname, i):
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


#Handle location + meal data request
def requestLocationAndMeal(date_in,loc_in, meal_in):

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
        print(getCoursesAndItems(data))
        return getCoursesAndItems(data)
    else:
        return "No meal is available."

#Handle meal item data request
def requestItem(date_in,loc_in, meal_in, item_in):
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
    for i in range(len(data['menu']['meal'])):
        
        #If meal specified, only check specified meal
        if mealEntered and data['menu']['meal'][i]['name'].upper() != meal_in.upper():
            continue
        #Skip meal if no food items available
        if 'course' not in data['menu']['meal'][i]:
            continue

        #Loop through food items in course
        for j in range(len(data['menu']['meal'][i]['course'])):
            for key, value in data['menu']['meal'][i]['course'][j].items():
                if key == 'name':
                    coursedata = data['menu']['meal'][i]['course'][j]['menuitem']
                    mealname = data['menu']['meal'][i]['name']
                    #Append matches to specified item to possiblematches list
                    possiblematches = findMatches(coursedata, possiblematches, item_in, mealname, i)
         
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

