import urllib.parse
import requests
import urllib.request

#remove spaces in url string
def removeSpaces(url_block):
    temp = ""
    for i in range(len(url_block)):
        if url_block[i] == ' ':
            temp += '+'
        else:
            temp += url_block[i]
    return temp

#check if meal is available at specified location/date
def checkMealAvailable(data,meal):
    for key in data['menu']['meal']:
        if data['menu']['meal']['name'].upper() == meal.upper():
            if 'course' in data['menu']['meal']:
                #print('Found')
                return True
            #print('Not found')
            #print(data['menu']['meal']['message']['content'])
            return False

#check if course is available in specified meal
def checkCourseAvailable(data, course):
    for i in range(len(data['menu']['meal']['course'])):
        for key, value in data['menu']['meal']['course'][i].items():
            if key == 'name':
                if value.upper() == course.upper():
                    return True
    return False

#gets food items of specified valid course
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

def getCoursesAndItems(data):
    returndata = ""
    for i in range(len(data['menu']['meal']['course'])):
        for key, value in data['menu']['meal']['course'][i].items():
            if key == 'name':
                if(checkCourseAvailable(data,value)):
                    returndata += ('Items in ' + value + ' course:\n')

                    returndata += getItemsInCourse(data['menu']['meal']['course'], value)
    return returndata

#########################################################################

def datahandle(date_in,loc_in, meal_in):

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
        return getCoursesAndItems(data)
    else:
        return "No meal is available."

