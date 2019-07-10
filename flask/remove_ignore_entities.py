import json


def removeIgnoreEntities(data, category):
    """Removes entity terms to be ignored found in ``ignore.json`` when comparing current local data and potentially updated MDining API data.

    :param data: List of items in current version of specified entity
    :type data: list
    :param category: Entity category of the search term ('Location'/'Meal')
    :type category: string
    """
    with open('ignore.json') as f:
      ignoredata = json.load(f)
    newdata = []
    for term in data:
        copy = True
        for ignoreterm in ignoredata[category]:
            if (term.strip('\n') == ignoreterm):
                copy = False
        if copy:
            newdata.append(term)
    return newdata
