# m-voice
### Documentation: https://m-voice.readthedocs.io/en/latest/
Voice interface implementation for University of Michigan applications using Dialogflow. Currently focusing on MDining.
**MDining API:** http://api.studentlife.umich.edu/menu/menu_generator/generator.html



---

Dialogflow submits `POST` request to https://vast-castle-65537.herokuapp.com/webhook

Flask server receives request and extracts key information:
* Parameters: `responsedata['queryResult']['parameters']['parameter_name'] = parameter_value`
* Type of parameter (Location or Meal)
* Dialogflow will only send valid parameter values to Flask server 
    * these are either a full Location or Meal name or a partial name for the Flask server to use to suggest to the user actual names
    * Dialogflow will take care of handling otherwise invalid user input parameters

Dialogflow then receives appropriate information back from Flask server and responds appropriately.


*Dialogflow fulfillment documentation: https://dialogflow.com/docs/fulfillment/how-it-works*

---
Matthew Jones and Ibrahim Kosgi
