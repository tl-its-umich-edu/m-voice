import json


with open('ignore.json') as f:
  ignoredata = json.load(f)
#print(ignoredata)




def removeIgnoreEntities(file, category):

    with open(file, "r") as f:
        originallines = f.readlines()
    
    with open(file, "w") as f:
        for term in originallines:
            copy = True
            for ignoreterm in ignoredata[category]:
                if (term.strip('\n') == ignoreterm):
                    copy = False
            if copy:
                f.write(term)
        


removeIgnoreEntities('temp_original.txt', 'Meal')
removeIgnoreEntities('temp_original.txt', 'Meal')

