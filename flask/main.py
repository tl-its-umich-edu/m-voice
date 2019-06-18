from functools import wraps
from flask import Flask, request, jsonify, Response, abort
import json, requests, urllib.parse,urllib.request
import filecmp, difflib, shutil
from remove_ignore_entities import removeIgnoreEntities

app = Flask(__name__)

#Basic homepage for checking successful deployment
@app.route('/')
def home():
    return "Success"

#Authentication
def check_auth(name,passw):
    return (name=='user' and passw=='pass')
def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            abort(401)
        return f(*args, **kwargs)
    return decorated



#Check if input term is part of a larger official term
def isPartialTerm(search, filename):
    list_data = open(filename)
    for i in list_data:
        if search.upper() == str(i.rstrip("\n\r")).upper():
            return True
    return False


def similarSearch(search, category):

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
    
    return outputstring[:-4]


#Webhook call
@app.route('/webhook',methods=['POST'])
@requires_auth
def webhookPost():
    #name = request.args.get("name", "World")
    #return f'Hello, {name}!'
    req_data = request.get_json()

    if 'Location' in req_data['queryResult']['parameters']:
        category = 'Location'
        search = req_data['queryResult']['parameters']['Location']
    elif 'Meal' in req_data['queryResult']['parameters']:
        category = 'Meal'
        search = req_data['queryResult']['parameters']['Meal']
    #return req_data['queryResult']['intent']['displayName']
    else:
        search = 'Error'
        category = 'Error'
    text = similarSearch(search, category)
    
    return jsonify(
      fulfillmentText=text
    )

@app.route('/cron',methods=['POST'])
def cronUpdate():
    #Cron authentication through post request data
    req_data = request.get_json()
    if (req_data['user'] != 'user') or (req_data['pass'] != 'pass'):
        text = 'Authentication failed.'
    
    else:
        #Meal Diff
        mealchanged = False
        locationchanged = False
        mealreq = requests.post('http://api.studentlife.umich.edu/menu/menu_generator/meal.php')
        mealdata = mealreq.json()
                
        newmeal = open('temp_new.txt.','w').close()
        newmeal = open('temp_new.txt.','w')
        for i in mealdata:
            if i['optionValue'] != "":
                newmeal.write(i['optionValue'] + '\n')
        newmeal.close()

        shutil.copy2('MealMain.txt', 'temp_original.txt')
        removeIgnoreEntities('temp_original.txt', 'Meal')
        removeIgnoreEntities('temp_new.txt', 'Meal')


        newmeal = open('temp_new.txt', 'r').readlines()
        originalmeal = open('MealMain.txt', 'r').readlines()

        diffmeal = open('MealDiff.txt','w').close()
        diffmeal = open('MealDiff.txt','w')
        for line in difflib.unified_diff(originalmeal, newmeal):
            mealchanged = True
            diffmeal.write(line)

        
        #Location Diff
        locationreq = requests.post('http://api.studentlife.umich.edu/menu/menu_generator/location.php')
        locationdata = locationreq.json()

        newlocation = open('temp_new.txt.','w').close()
        newlocation = open('temp_new.txt.','w')
        for i in locationdata:
            if i['optionValue'] != "":
                newlocation.write(i['optionValue'] + '\n')
        newlocation.close()

        shutil.copy2('LocationMain.txt', 'temp_original.txt')
        removeIgnoreEntities('temp_original.txt', 'Location')
        removeIgnoreEntities('temp_new.txt', 'Location')
        
        newlocation = open('temp_new.txt', 'r').readlines()
        originallocation = open('LocationMain.txt', 'r').readlines()

        difflocation = open('LocationDiff.txt','w').close()
        difflocation = open('LocationDiff.txt','w')
        for line in difflib.unified_diff(originallocation, newlocation):
            locationchanged = True
            difflocation.write(line)

        #Check for file changes for appropriate http response
        if locationchanged or mealchanged:
            text = "Update "
            if locationchanged:
                text += "location"
            if mealchanged:
                if locationchanged:
                    text += " and meal"
                else:
                    text += "meal"
            text += "."
            
        else:
            text = "Data up to date"

    return jsonify(
      text
    )

