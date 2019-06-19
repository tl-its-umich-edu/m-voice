import json

with open('ignore.json') as f:
  ignoredata = json.load(f)
#print(ignoredata)

def removeIgnoreEntities(data, category):
    newdata = []
    for term in data:
        copy = True
        for ignoreterm in ignoredata[category]:
            if (term.strip('\n') == ignoreterm):
                copy = False
        if copy:
            newdata.append(term)
    return newdata
