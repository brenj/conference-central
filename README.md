[![Live Demo](https://img.shields.io/badge/live%20demo-active-brightgreen.svg?style=flat-square)](https://digital-splicer-114902.appspot.com/#/)

Conference Organization App
===========================

About
-----

From Udacity:

> You will develop a cloud-based API server to support a provided conference organization application that exists on the web as well as a native Android application. The API supports the following functionality found within the app: user authentication, user profiles, conference information and various manners in which to query the data.

Supporting Course:

*  [Developing Scalable Apps in Python](https://www.udacity.com/course/developing-scalable-apps-in-python--ud858)

**Important Note**

The deliverable for this project is largely in the form of API endpoints for Conference Central, an application code-base provided by Udacity. These endpoints were created using `Google Cloud Endpoints` on the `Google App Engine` platform, and are only accessible using the `Google APIs Explorer`. Integrating these endpoints into the Conference Central front-end is not part of this project. 

Most of the code in this project was provided by Udacity and does not reflect my coding style or abilities. To highlight my contributions I have included references in this README to the functions, classes, etc... that I created to complete the project.

Tasks
-----

##### Add Sessions to a Conference

To support sessions I created:

* NDB Models: `Session`, `Speaker`
* Messages: `SessionRequestMessage`, `SessionResponseMessage`, `SessionsResponseMessage`, `SpeakerRequestMessage`, `SpeakerResponseMessage`
* Endpoints: `create_session`, `create_speaker`, `get_conference_sessions`, `get_conference_sessions_by_type`, `get_sessions_by_speaker`
* Helpers: `_get_entity_by_key`

Models and messages can be found in [models.py](https://github.com/brenj/udacity/blob/master/conference_organization_app/conference_central/models.py#L112), and endpoints (with related code) can be found in [conference.py](https://github.com/brenj/udacity/blob/master/conference_organization_app/conference_central/conference.py#L552).

> Explain in a couple of paragraphs your design choices for session and speaker implementation.

Sessions, in the context of this project, are blocks of time at a conference for a speaker to discuss a topic, run a workshop, etc… In a traditional RDBMS the relationship between session and conference would be one-to-many, where many sessions would relate to one, and only one, conference. To model this relationship in Google’s `Datastore` I chose to use the ancestor relationship (though other options are available e.g. `KeyProperty`). Entities can be given a hierarchical structure in `Datastore` by assigning a parent entity at the time of (child) entity creation. This allows corresponding entities to be retrieved from both sides of the relationship. So for a given session the conference that the session is scheduled in can be obtained, and similarly for a given conference, all sessions in that conference can be obtained.

Session properties `name`, `speaker_key`, `date`, and `start_time` are required. These values are necessary to define a session at a conference. `StringProperty` was chosen for `name`, `highlights`, and `type_of_session` because these properties should be indexed for searching and should be limited in their length. `duration` is an `IntegerProperty` to simplify queries using ranges and equalities. `date` and `start_time` are date and time properties respectively so that querying and handling can be done using Python's `datetime` module. Finally, `speaker_key` is a `KeyProperty` that references a particular speaker entity and functions sort of like a foreign key in a typical RDBMS.

```python
class Session(ndb.Model):

    """A session (e.g. talk, workshop) given at a `Conference`."""

    name = ndb.StringProperty(required=True)
    highlights = ndb.StringProperty()
    speaker_key = ndb.KeyProperty(kind='Speaker', required=True)
    duration = ndb.IntegerProperty()
    type_of_session = ndb.StringProperty(default='talk')
    date = ndb.DateProperty(required=True)
    start_time = ndb.TimeProperty(required=True)
```

A speaker is an individual who provides the content for a session at a conference. Rather than defining the speaker property as a `StringProperty`, I decided to use `KeyProperty` instead. The reason for this is that we may want to store more information about a speaker than just his or her name (e.g. for a speaker page on the `Conference Central` website), so Speaker should be defined as a separate model and associated with a session through it's unique key. 
Modeling speaker this way also means that there is a way to identify a speaker, a speakers sessions, etc… without relying on a non-unique attribute (e.g. name).

Though many other properties could be added in the future if needed, all that is required for a speaker entity is a speaker's name. Using a `StringProperty` for `name` ensures indexing for queries, limits the length, and minimizes storage requirements.

```python
class Speaker(ndb.Model):

    """A speaker at a conference session."""

    name = ndb.StringProperty(required=True)
```

Please note that this means a new session requires a `speaker_key ` (url-safe key) to specify a speaker. To store a new speaker use the `create_speaker` endpoint (the speaker's key will be in the response).

##### Add Sessions to User Wishlist

To support a user wishlist I created:

* Properties: `sessions_wishlist` in the `Profile` model
* Endpoints: `add_session_to_wishlist`, `get_sessions_in_wishlist`, `delete_session_in_wishlist`
* Helpers: `_get_wishlist_sessions`, `_get_wishlist_sessions_as_message`

##### Work on indexes and queries

> Make sure the indexes support the type of queries required by the new Endpoints methods.

No additions to `index.yaml` are needed for my implementation of the endpoints methods in tasks one and two. Only the indexes that `Datastore` automatically predefines for each property of each kind are required.

> Think about other types of queries that would be useful for this application. Describe the purpose of 2 new queries and write the code that would perform them.

Query 1:

* To plan their day, users of the `Conference Central` application may be interested in seeing sessions available for a given conference on a particular day with results ordered by time.

```python
sessions = Session.query(ancestor=conference.key).filter(
    Session.date == request.date).order(Session.start_time).fetch()
```

This query would require the following entry in `index.yaml`:

```yaml
- kind: Session
  properties:
  - name: date
  - name: start_time
```

This query is implemented in the endpoint: `get_conference_sessions_by_date`
 
Query 2:

* `Conference Central` users may want to see all the sessions at a conference that are interactive.

```python
# Assuming `workshop`, `hackathon`, and `lab` are the only interactive
# session types
INTERACTIVE_SESSION_TYPES = ('workshop', 'hackathon', 'lab')
sessions = Session.query(ancestor=conference.key).filter(¬             
    Session.type_of_session.IN(INTERACTIVE_SESSION_TYPES)).fetch()
```

This query is implemented in the endpoint: `get_interactive_conference_sessions`

> Let’s say that you don't like workshops and you don't like sessions after 7 pm. How would you handle a query for all non-workshop sessions before 7 pm? What is the problem for implementing this query? What ways to solve it did you think of?

If you were to implement this query the straightforward way you'd recieve an error like this:

 ```python
 BadRequestError: Cannot have inequality filters on multiple properties
 ```

This error is due to a restriction on `Datastore` queries whereby inequality filters are limited to at most one property; we would be using two. The reason for this restriction has to do with how `Datastore` works (index-based query mechanism). On a basic level `Datastore` queries rely on potential results being adjacent to one another to avoid scanning an entire index (very inefficient), so operations that require this are disallowed.

Here are some ways to work around this restriction:

* Create a `BooleanProperty` on `Session` to show whether the session occurs before or after 7 PM. That way you would only need to query for one inequality.

```python
sessions = Session.query().filter(
    Session.type_of_session != 'workshop').filter(
        Session.is_after_7pm == True).fetch()
```

* Query for all sessions that are not workshops, then filter those results programmatically by comparing each session’s time.

```python
sessions = Session.query().filter(
    Session.type_of_session != 'workshop').fetch()
seven_pm = datetime.strptime('19:00', '%H:%M').time()
sessions = [session for session in sessions if session.start_time <= seven_pm]
```

* Determine all non-workshop session types (by hard-coding or querying), and then search for all sessions where type of session is in non-workshop types and occurs before or at 7 PM.

```python
seven_pm = datetime.strptime('19:00', '%H:%M').time()
sessions = Session.query(
    Session.type_of_session.IN(NON_WORKSHOP_TYPES)).filter(
        Session.start_time <= seven_pm).fetch()
```

This solution also requires an additional index:

```yaml
- kind: Session
  properties:
  - name: type_of_session
  - name: start_time
```

This solution is implemented in the endpoint: `get_sessions_nonworkshop_before_7pm`

##### Add a Task

To support a featured speaker I created:

* Endpoints: `get_featured_speaker`
* Handlers: `StoreFeaturedSpeaker`

Handlers can be found in [main.py](https://github.com/brenj/udacity/blob/master/conference_organization_app/conference_central/main.py#L45)

This solution also requires an additional index:

```yaml
- kind: Session
  ancestor: yes
  properties:
  - name: speaker_key
  - name: name
```

Install
-------

SDK install instructions below are for Linux. To install Google App Engine on another platform consult the following: https://cloud.google.com/appengine/downloads.

1. `wget https://storage.googleapis.com/appengine-sdks/featured/google_appengine_1.9.30.zip`
2. `sudo unzip google_appengine_1.9.30.zip -d /usr/local`
3. `export PATH=$PATH:/usr/local/google_appengine/`
4. `git clone https://github.com/brenj/udacity.git && cd udacity/conference_organization_app/conference_central`
5. Update `application` to your app id (aka project id) in `app.yaml` (optional)
6. Add client id to `settings.py` and `static/js/app.js`
7. `appcfg.py -A <app-id> update .` or `appcfg.py update .` (if you performed step five)

APIs Explorer
-------------

*  Navigate to [Conference Central](https://digital-splicer-114902.appspot.com/)
*  Log into `Conference Central`
*  Navigate to [Conference API v1](https://apis-explorer.appspot.com/apis-explorer/?base=https://digital-splicer-114902.appspot.com/_ah/api#p/conference/v1/)

Requirements
------------

* [Google Account](https://accounts.google.com/SignUp?hl=en)
* Python 2.7

Grading (by Udacity)
--------------------

Criteria       |Highest Grade Possible  |Grade Recieved
---------------|------------------------|--------------
App Architecture  |Meets Specifications  |Meets Specifications
Design Choices (Implementation)  |Exceeds Specifications  |Exceeds Specifications
Design Choices (Response)  |Exceeds Specifications  |Exceeds Specifications
Session Wishlist  |Meets Specifications  |Meets Specifications
Additional Queries  |Meets Specifications  |Meets Specifications
Query Problem  |Exceeds Specifications  |Exceeds Specifications
Featured Speaker  |Meets Specifications  |Meets Specifications
Code Quality   |Meets Specifications    |Meets Specifications
Code Readability       |Meets Specifications  |Meets Specifications
Documentation  |Meets Specifications    |Meets Specifications
