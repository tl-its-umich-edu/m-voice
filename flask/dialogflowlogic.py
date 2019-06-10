import urllib.parse
import requests
import urllib.request

#remove spaces in url string
def removeSpaces(url_block):
    temp = ""
    for i in range(len(url_block)):
        if url[i] == ' ':
            temp += '+'
        else:
            temp += url_block[i]
    return temp

#allows for leeway in user input and gives options for recommended searches
def similarSearch(term_in, term_compare, filename):
    list_data = open(filename, 'r')
    if (term_in in term_compare):
        possible_searches = []
        for i in list_data:
            if term_in in str(i.rstrip("\n\r")):
                possible_searches.append(str(i.rstrip("\n\r")))

        validInput = False
        while(validInput is False):
            print("Did you mean:")
            for i in possible_searches:
                print('\t'+i)
            userin = input(': ')
            if userin.upper() in possible_searches:
                return userin.upper()
    return False

#finds input location/meal
def findInput(category,filename):
    found = False
    while(found == False):
        list_data = open(filename,'r')
        search = input(category + ': ')
        for i in list_data:
            if search.upper() == str(i.rstrip("\n\r")):
                found = True
                return search
        if (found == False):
            list_data = open(filename,'r')
            for i in list_data:
                similarsearch = similarSearch(search.upper(), i, filename)
                if similarsearch != False:
                    found = True
                    return similarsearch
            print(category + ' not found.')
    return search

#check if meal is available at specified location/date
def checkMealAvailable(data,meal):
    for key in data['menu']['meal']:
        if data['menu']['meal']['name'].upper() == meal.upper():
            if 'course' in data['menu']['meal']:
                #print('Found')
                return True
            #print('Not found')
            print(data['menu']['meal']['message']['content'])
            return False

#check if course is available in specified meal
def checkCourseAvailable(data, course):
    for i in range(len(data['menu']['meal']['course'])):
        for key, value in data['menu']['meal']['course'][i].items():
            if key == 'name':
                if value.upper() == course.upper():
                    return True
    return False

#prints food items of specified valid course
def printItemsInCourse(coursedata, course):
    #print('Printing items in course:',course)

    for i in range(len(coursedata)):
        datatype = type(coursedata[i]['menuitem'])
        
        if coursedata[i]['name'].upper() == course.upper():
            if datatype is list:
                for j in range(len(coursedata[i]['menuitem'])):
                    print('\t'+coursedata[i]['menuitem'][j]['name'])
            elif datatype is dict:
                print('\t'+coursedata[i]['menuitem']['name'])

#prints courses of specified valid meal              
def printCourses(data):
    #print('Printing courses:')
    for i in range(len(data['menu']['meal']['course'])):
        for key, value in data['menu']['meal']['course'][i].items():
            if key == 'name':
                print ('\t'+value)
                return True
                #printItemsInCourse(data['menu']['meal']['course'],value)


#########################################################################

while(True):
    #preset vars
    url = 'http://api.studentlife.umich.edu/menu/xml2print.php?controller=&view=json'
    location = '&location='
    date = '&date='
    meal = '&meal='

    #input location/meal/date(date preset for now)
    print('----------------\nBegin meal search')
    loc_in = findInput('Location','MDiningAPILocations.txt')
    meal_in = findInput('Meal','MDiningAPIMeals.txt')
    date_in = '2019-05-15'
    print('Date: ', date_in)

    #API url concatenation
    location += loc_in
    meal += meal_in
    date += date_in
    url = url + location + date + meal
    url = removeSpaces(url)
    
    #fetching json
    data = requests.get(url).json()

    #checking if specified meal available
    if (checkMealAvailable(data, meal_in) == False):
        continue

    #input course and receive data
    validInput = False
    while(validInput is False):
        print('Courses in', meal_in + ':')
        printCourses(data)

        #input course of meal
        course = input("\nFind items in which course: ")

        #check if course exists, receive data
        if(checkCourseAvailable(data,course)):
            print('Items in', course,'course during',meal_in, 'at',loc_in + ':')

            printItemsInCourse(data['menu']['meal']['course'], course)
            validInput = True
        else:
            print('Course not found')

