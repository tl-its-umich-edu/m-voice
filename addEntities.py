#run following commands in notebook before proceeding

#!pip uninstall -y google-cloud-datastore
#!pip install google-cloud-datastore
#!pip install --upgrade pip
#!yes | pip uninstall dialogflow
#!pip install dialogflow==0.3.0


#Must have empty entity created on Dialogflow before executing
#continue


from google.cloud import datastore
import dialogflow

client = datastore.Client()


#add location and meal entities to Google Cloud Datastore from file input

def addEntitiesToDatastore(datafile, dataStoreKind):
    file = open(datafile,'r')
    for i in file:
        locations_key = client.key(dataStoreKind, i.rstrip("\n\r"))
        locations = datastore.Entity(key=locations_key)
        client.put(locations)

addEntitiesToDatastore('MDiningAPILocations.txt','Locations')
addEntitiesToDatastore('MDiningAPIMeals.txt','Meals')

#########################################################################


#add location and meal entities from Google Cloud Datastore to Dialogflow

def addEntityToDialogflow(dataStoreKind, dialogflowEntityName):
  query = client.query(kind=dataStoreKind)
  results = list(query.fetch())

  entity_types_client = dialogflow.EntityTypesClient()


  project_id = !(gcloud config get-value project)

  project_agent_path = entity_types_client.project_agent_path(
          project_id[0])

  for element in entity_types_client.list_entity_types(project_agent_path):
    if (element.display_name == dialogflowEntityName):
      entity_type_path = element.name

  project_id = !(gcloud config get-value project)

  entities = []

  for result in results:
    entity = dialogflow.types.EntityType.Entity()
    print(entity.value)
    entity.value = result.key.name
    entity.synonyms.append(result.key.name)

    entities.append(entity)

  #print entities

  response = entity_types_client.batch_create_entities(
          entity_type_path, entities)

  #print('Entity created: {}'.format(response))


addEntityToDialogflow('Locations','Locations')
addEntityToDialogflow('Meals','Meals')
