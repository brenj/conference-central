#!/usr/bin/env python

"""
conference.py -- Udacity conference server-side Python App Engine API;
    uses Google Cloud Endpoints

$Id: conference.py,v 1.25 2014/05/24 23:42:19 wesc Exp wesc $

created by wesc on 2014 apr 21

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'


from datetime import datetime
import logging

import endpoints
from protorpc import message_types
from protorpc import remote

from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.ext import ndb

from models import ConflictException
from models import Profile
from models import ProfileMiniForm
from models import ProfileForm
from models import StringMessage
from models import BooleanMessage
from models import Conference
from models import ConferenceForm
from models import ConferenceForms
from models import ConferenceQueryForms
from models import TeeShirtSize
from models import Session
from models import SessionResponseMessage
from models import SessionsResponseMessage
from models import Speaker
from models import SpeakerRequestMessage
from models import SpeakerResponseMessage

import resource_containers as containers

from settings import WEB_CLIENT_ID
from settings import ANDROID_CLIENT_ID
from settings import IOS_CLIENT_ID
from settings import ANDROID_AUDIENCE

from utils import getUserId

EMAIL_SCOPE = endpoints.EMAIL_SCOPE
API_EXPLORER_CLIENT_ID = endpoints.API_EXPLORER_CLIENT_ID
MEMCACHE_ANNOUNCEMENTS_KEY = "RECENT_ANNOUNCEMENTS"
MEMCACHE_FEATURED_SPEAKER = "FEATURED_SPEAKER"
ANNOUNCEMENT_TPL = ('Last chance to attend! The following conferences '
                    'are nearly sold out: %s')
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

DEFAULTS = {
    "city": "Default City",
    "maxAttendees": 0,
    "seatsAvailable": 0,
    "topics": [ "Default", "Topic" ],
}

OPERATORS = {
            'EQ':   '=',
            'GT':   '>',
            'GTEQ': '>=',
            'LT':   '<',
            'LTEQ': '<=',
            'NE':   '!='
            }

FIELDS =    {
            'CITY': 'city',
            'TOPIC': 'topics',
            'MONTH': 'month',
            'MAX_ATTENDEES': 'maxAttendees',
            }

INTERACTIVE_SESSION_TYPES = ('workshop', 'hackathon', 'lab')
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


@endpoints.api(name='conference', version='v1', audiences=[ANDROID_AUDIENCE],
    allowed_client_ids=[WEB_CLIENT_ID, API_EXPLORER_CLIENT_ID, ANDROID_CLIENT_ID, IOS_CLIENT_ID],
    scopes=[EMAIL_SCOPE])
class ConferenceApi(remote.Service):
    """Conference API v0.1"""

# - - - Conference objects - - - - - - - - - - - - - - - - -

    def _copyConferenceToForm(self, conf, displayName):
        """Copy relevant fields from Conference to ConferenceForm."""
        cf = ConferenceForm()
        for field in cf.all_fields():
            if hasattr(conf, field.name):
                # convert Date to date string; just copy others
                if field.name.endswith('Date'):
                    setattr(cf, field.name, str(getattr(conf, field.name)))
                else:
                    setattr(cf, field.name, getattr(conf, field.name))
            elif field.name == "websafeKey":
                setattr(cf, field.name, conf.key.urlsafe())
        if displayName:
            setattr(cf, 'organizerDisplayName', displayName)
        cf.check_initialized()
        return cf


    def _createConferenceObject(self, request):
        """Create or update Conference object, returning ConferenceForm/request."""
        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        if not request.name:
            raise endpoints.BadRequestException("Conference 'name' field required")

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}
        del data['websafeKey']
        del data['organizerDisplayName']

        # add default values for those missing (both data model & outbound Message)
        for df in DEFAULTS:
            if data[df] in (None, []):
                data[df] = DEFAULTS[df]
                setattr(request, df, DEFAULTS[df])

        # convert dates from strings to Date objects; set month based on start_date
        if data['startDate']:
            data['startDate'] = datetime.strptime(data['startDate'][:10], "%Y-%m-%d").date()
            data['month'] = data['startDate'].month
        else:
            data['month'] = 0
        if data['endDate']:
            data['endDate'] = datetime.strptime(data['endDate'][:10], "%Y-%m-%d").date()

        # set seatsAvailable to be same as maxAttendees on creation
        if data["maxAttendees"] > 0:
            data["seatsAvailable"] = data["maxAttendees"]
        # generate Profile Key based on user ID and Conference
        # ID based on Profile key get Conference key from ID
        p_key = ndb.Key(Profile, user_id)
        c_id = Conference.allocate_ids(size=1, parent=p_key)[0]
        c_key = ndb.Key(Conference, c_id, parent=p_key)
        data['key'] = c_key
        data['organizerUserId'] = request.organizerUserId = user_id

        # create Conference, send email to organizer confirming
        # creation of Conference & return (modified) ConferenceForm
        Conference(**data).put()
        taskqueue.add(params={'email': user.email(),
            'conferenceInfo': repr(request)},
            url='/tasks/send_confirmation_email'
        )
        return request


    @ndb.transactional()
    def _updateConferenceObject(self, request):
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}

        # update existing conference
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        # check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)

        # check that user is owner
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can update the conference.')

        # Not getting all the fields, so don't create a new object; just
        # copy relevant fields from ConferenceForm to Conference object
        for field in request.all_fields():
            data = getattr(request, field.name)
            # only copy fields where we get data
            if data not in (None, []):
                # special handling for dates (convert string to Date)
                if field.name in ('startDate', 'endDate'):
                    data = datetime.strptime(data, "%Y-%m-%d").date()
                    if field.name == 'startDate':
                        conf.month = data.month
                # write to Conference object
                setattr(conf, field.name, data)
        conf.put()
        prof = ndb.Key(Profile, user_id).get()
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))


    @endpoints.method(ConferenceForm, ConferenceForm, path='conference',
            http_method='POST', name='createConference')
    def createConference(self, request):
        """Create new conference."""
        return self._createConferenceObject(request)


    @endpoints.method(containers.CONF_POST_REQUEST, ConferenceForm,
            path='conference/{websafeConferenceKey}',
            http_method='PUT', name='updateConference')
    def updateConference(self, request):
        """Update conference w/provided fields & return w/updated info."""
        return self._updateConferenceObject(request)


    @endpoints.method(containers.CONF_GET_REQUEST, ConferenceForm,
            path='conference/{websafeConferenceKey}',
            http_method='GET', name='getConference')
    def getConference(self, request):
        """Return requested conference (by websafeConferenceKey)."""
        # get Conference object from request; bail if not found
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)
        prof = conf.key.parent().get()
        # return ConferenceForm
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))


    @endpoints.method(message_types.VoidMessage, ConferenceForms,
            path='getConferencesCreated',
            http_method='POST', name='getConferencesCreated')
    def getConferencesCreated(self, request):
        """Return conferences created by user."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # create ancestor query for all key matches for this user
        confs = Conference.query(ancestor=ndb.Key(Profile, user_id))
        prof = ndb.Key(Profile, user_id).get()
        # return set of ConferenceForm objects per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, getattr(prof, 'displayName')) for conf in confs]
        )


    def _getQuery(self, request):
        """Return formatted query from the submitted filters."""
        q = Conference.query()
        inequality_filter, filters = self._formatFilters(request.filters)

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Conference.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Conference.name)

        for filtr in filters:
            if filtr["field"] in ["month", "maxAttendees"]:
                filtr["value"] = int(filtr["value"])
            formatted_query = ndb.query.FilterNode(filtr["field"], filtr["operator"], filtr["value"])
            q = q.filter(formatted_query)
        return q


    def _formatFilters(self, filters):
        """Parse, check validity and format user supplied filters."""
        formatted_filters = []
        inequality_field = None

        for f in filters:
            filtr = {field.name: getattr(f, field.name) for field in f.all_fields()}

            try:
                filtr["field"] = FIELDS[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException("Filter contains invalid field or operator.")

            # Every operation except "=" is an inequality
            if filtr["operator"] != "=":
                # check if inequality operation has been used in previous filters
                # disallow the filter if inequality was performed on a different field before
                # track the field on which the inequality operation is performed
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException("Inequality filter is allowed on only one field.")
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters)


    @endpoints.method(ConferenceQueryForms, ConferenceForms,
            path='queryConferences',
            http_method='POST',
            name='queryConferences')
    def queryConferences(self, request):
        """Query for conferences."""
        conferences = self._getQuery(request)

        # need to fetch organiser displayName from profiles
        # get all keys and use get_multi for speed
        organisers = [(ndb.Key(Profile, conf.organizerUserId)) for conf in conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return individual ConferenceForm object per Conference
        return ConferenceForms(
                items=[self._copyConferenceToForm(conf, names[conf.organizerUserId]) for conf in \
                conferences]
        )


# - - - Profile objects - - - - - - - - - - - - - - - - - - -

    def _copyProfileToForm(self, prof):
        """Copy relevant fields from Profile to ProfileForm."""
        # copy relevant fields from Profile to ProfileForm
        pf = ProfileForm()
        for field in pf.all_fields():
            if hasattr(prof, field.name):
                # convert t-shirt string to Enum; just copy others
                if field.name == 'teeShirtSize':
                    setattr(pf, field.name, getattr(TeeShirtSize, getattr(prof, field.name)))
                else:
                    setattr(pf, field.name, getattr(prof, field.name))
        pf.check_initialized()
        return pf


    def _getProfileFromUser(self):
        """Return user Profile from datastore, creating new one if non-existent."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # get Profile from datastore
        user_id = getUserId(user)
        p_key = ndb.Key(Profile, user_id)
        profile = p_key.get()
        # create new Profile if not there
        if not profile:
            profile = Profile(
                key = p_key,
                displayName = user.nickname(),
                mainEmail= user.email(),
                teeShirtSize = str(TeeShirtSize.NOT_SPECIFIED),
            )
            profile.put()

        return profile      # return Profile


    def _doProfile(self, save_request=None):
        """Get user Profile and return to user, possibly updating it first."""
        # get user Profile
        prof = self._getProfileFromUser()

        # if saveProfile(), process user-modifyable fields
        if save_request:
            for field in ('displayName', 'teeShirtSize'):
                if hasattr(save_request, field):
                    val = getattr(save_request, field)
                    if val:
                        setattr(prof, field, str(val))
                        #if field == 'teeShirtSize':
                        #    setattr(prof, field, str(val).upper())
                        #else:
                        #    setattr(prof, field, val)
                        prof.put()

        # return ProfileForm
        return self._copyProfileToForm(prof)


    @endpoints.method(message_types.VoidMessage, ProfileForm,
            path='profile', http_method='GET', name='getProfile')
    def getProfile(self, request):
        """Return user profile."""
        return self._doProfile()


    @endpoints.method(ProfileMiniForm, ProfileForm,
            path='profile', http_method='POST', name='saveProfile')
    def saveProfile(self, request):
        """Update & return user profile."""
        return self._doProfile(request)


# - - - Announcements - - - - - - - - - - - - - - - - - - - -

    @staticmethod
    def _cacheAnnouncement():
        """Create Announcement & assign to memcache; used by
        memcache cron job & putAnnouncement().
        """
        confs = Conference.query(ndb.AND(
            Conference.seatsAvailable <= 5,
            Conference.seatsAvailable > 0)
        ).fetch(projection=[Conference.name])

        if confs:
            # If there are almost sold out conferences,
            # format announcement and set it in memcache
            announcement = ANNOUNCEMENT_TPL % (
                ', '.join(conf.name for conf in confs))
            memcache.set(MEMCACHE_ANNOUNCEMENTS_KEY, announcement)
        else:
            # If there are no sold out conferences,
            # delete the memcache announcements entry
            announcement = ""
            memcache.delete(MEMCACHE_ANNOUNCEMENTS_KEY)

        return announcement


    @endpoints.method(message_types.VoidMessage, StringMessage,
            path='conference/announcement/get',
            http_method='GET', name='getAnnouncement')
    def getAnnouncement(self, request):
        """Return Announcement from memcache."""
        return StringMessage(data=memcache.get(MEMCACHE_ANNOUNCEMENTS_KEY) or "")


# - - - Registration - - - - - - - - - - - - - - - - - - - -

    @ndb.transactional(xg=True)
    def _conferenceRegistration(self, request, reg=True):
        """Register or unregister user for selected conference."""
        retval = None
        prof = self._getProfileFromUser() # get user Profile

        # check if conf exists given websafeConfKey
        # get conference; check that it exists
        wsck = request.websafeConferenceKey
        conf = ndb.Key(urlsafe=wsck).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # register
        if reg:
            # check if user already registered otherwise add
            if wsck in prof.conferenceKeysToAttend:
                raise ConflictException(
                    "You have already registered for this conference")

            # check if seats avail
            if conf.seatsAvailable <= 0:
                raise ConflictException(
                    "There are no seats available.")

            # register user, take away one seat
            prof.conferenceKeysToAttend.append(wsck)
            conf.seatsAvailable -= 1
            retval = True

        # unregister
        else:
            # check if user already registered
            if wsck in prof.conferenceKeysToAttend:

                # unregister user, add back one seat
                prof.conferenceKeysToAttend.remove(wsck)
                conf.seatsAvailable += 1
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        prof.put()
        conf.put()
        return BooleanMessage(data=retval)


    @endpoints.method(message_types.VoidMessage, ConferenceForms,
            path='conferences/attending',
            http_method='GET', name='getConferencesToAttend')
    def getConferencesToAttend(self, request):
        """Get list of conferences that user has registered for."""
        prof = self._getProfileFromUser() # get user Profile
        conf_keys = [ndb.Key(urlsafe=wsck) for wsck in prof.conferenceKeysToAttend]
        conferences = ndb.get_multi(conf_keys)

        # get organizers
        organisers = [ndb.Key(Profile, conf.organizerUserId) for conf in conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return set of ConferenceForm objects per Conference
        return ConferenceForms(items=[self._copyConferenceToForm(conf, names[conf.organizerUserId])\
         for conf in conferences]
        )


    @endpoints.method(containers.CONF_GET_REQUEST, BooleanMessage,
            path='conference/{websafeConferenceKey}',
            http_method='POST', name='registerForConference')
    def registerForConference(self, request):
        """Register user for selected conference."""
        return self._conferenceRegistration(request)


    @endpoints.method(containers.CONF_GET_REQUEST, BooleanMessage,
            path='conference/{websafeConferenceKey}',
            http_method='DELETE', name='unregisterFromConference')
    def unregisterFromConference(self, request):
        """Unregister user for selected conference."""
        return self._conferenceRegistration(request, reg=False)


    @endpoints.method(message_types.VoidMessage, ConferenceForms,
            path='filterPlayground',
            http_method='GET', name='filterPlayground')
    def filterPlayground(self, request):
        """Filter Playground"""
        q = Conference.query()
        # field = "city"
        # operator = "="
        # value = "London"
        # f = ndb.query.FilterNode(field, operator, value)
        # q = q.filter(f)
        q = q.filter(Conference.city=="London")
        q = q.filter(Conference.topics=="Medical Innovations")
        q = q.filter(Conference.month==6)

        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, "") for conf in q]
        )

    # begin: brenj additions to conference.py
    #########################################

    def _get_entity_by_key(self, urlsafe_key):
        """Get an existing entity from a specified key."""
        try:
            entity = ndb.Key(urlsafe=urlsafe_key).get()
        except Exception as error:
            # All kinds of errors can happen with user-provided keys
            logging.error(
                "Failure getting entity using key: '{0}', {1}".format(
                    urlsafe_key, str(error)))
            entity = None

        if not entity:
            raise endpoints.NotFoundException(
                "No entity found with key: {0}.".format(urlsafe_key))

        return entity

    @endpoints.method(
        SpeakerRequestMessage, SpeakerResponseMessage,
        path='speaker', http_method='POST', name='createSpeaker')
    def create_speaker(self, request):
        """Create a new speaker."""
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException("Authorization required.")

        speaker = Speaker(name=request.name)
        speaker.put()

        return speaker.to_message()

    @endpoints.method(
        containers.SESSION_CONFERENCE_REQUEST, SessionResponseMessage,
        path='conference/{conference}/session',
        http_method='POST', name='createSession')
    def create_session(self, request):
        """Create a new session for a specified conference."""
        try:
            date = datetime.strptime(request.date, "%Y-%m-%d").date()
        except ValueError:
            raise endpoints.BadRequestException(
                "Date must be in format YYYY-MM-DD.")
        try:
            start_time = datetime.strptime(request.start_time, '%H:%M').time()
        except ValueError:
            raise endpoints.BadRequestException(
                "Time must be in format HH-MM (24 hour clock).")

        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException("Authorization required.")

        conference = self._get_entity_by_key(request.conference)

        if getUserId(user) != conference.organizerUserId:
            raise endpoints.ForbiddenException(
                "Only the conference organizer can add sessions.")

        speaker = self._get_entity_by_key(request.speaker_key)

        # Logged-in user; can add sessions to this conference

        allocated_id = ndb.Model.allocate_ids(
            size=1, parent=conference.key)[0]
        session_key = ndb.Key(Session, allocated_id, parent=conference.key)

        session = Session(
            key=session_key, name=request.name,
            highlights=request.highlights, speaker_key=speaker.key,
            duration=request.duration,
            type_of_session=request.type_of_session,
            date=date, start_time=start_time)
        session.put()

        taskqueue.add(
            params={
                'speaker_key': speaker.key.urlsafe(),
                'conference_key': conference.key.urlsafe()},
            url='/tasks/store_featured_speaker')

        return session.to_message()

    @endpoints.method(
        containers.CONFERENCE_REQUEST, SessionsResponseMessage,
        path='conference/{conference}/sessions', name='getConferenceSessions',
        http_method='GET')
    def get_conference_sessions(self, request):
        """Get all sessions for a specified conference."""
        conference = self._get_entity_by_key(request.conference)
        conference_sessions = Session.query(ancestor=conference.key)

        return SessionsResponseMessage(
            sessions=[session.to_message() for session in conference_sessions])

    @endpoints.method(
        containers.SESSIONS_BY_TYPE_REQUEST, SessionsResponseMessage,
        path='conference/{conference}/sessions/type/{type_of_session}',
        name='getConferenceSessionsByType', http_method='GET')
    def get_conference_sessions_by_type(self, request):
        """Get all sessions for a conference by the specified type."""
        conference = self._get_entity_by_key(request.conference)
        conference_sessions_by_type = (
            Session.query(ancestor=conference.key).filter(
                Session.type_of_session == request.type_of_session).fetch())

        return SessionsResponseMessage(
            sessions=[session.to_message() for
                      session in conference_sessions_by_type])

    @endpoints.method(
        containers.SESSIONS_BY_SPEAKER_REQUEST, SessionsResponseMessage,
        path='sessions/speaker/{speaker_key}', name='getSessionsBySpeaker',
        http_method='GET')
    def get_sessions_by_speaker(self, request):
        """Get all sessions for a specified speaker."""
        speaker = self._get_entity_by_key(request.speaker_key)

        # Get all the sessions by `speaker`
        sessions = speaker.session_set()

        return SessionsResponseMessage(
            sessions=[session.to_message() for session in sessions])

    @endpoints.method(
        containers.SESSION_REQUEST, SessionsResponseMessage,
        http_method='POST', path='profile/wish/{session}',
        name='addSessionToWishlist')
    def add_session_to_wishlist(self, request):
        """Add a session to a user's wishlist."""
        profile = self._getProfileFromUser()
        session = self._get_entity_by_key(request.session)

        # Make sure session hasn't already been added
        if session.key in profile.sessions_wishlist:
            raise ConflictException(
                "You have already added this session to your wishlist.")

        profile.sessions_wishlist.append(session.key)
        profile.put()

        # Return the new, complete wishlist
        return self._get_wishlist_sessions_as_message(profile)

    def _get_wishlist_sessions(self, profile):
        """Get the wishlist sessions for a specified user (profile)."""
        return ndb.get_multi([key for key in profile.sessions_wishlist])

    def _get_wishlist_sessions_as_message(self, profile):
        """Get the wishlist sessions as a SessionsResponseMessage."""
        wishlist_sessions = self._get_wishlist_sessions(profile)

        return SessionsResponseMessage(
            sessions=[wishlist_session.to_message() for
                      wishlist_session in wishlist_sessions if
                      wishlist_session])

    @endpoints.method(
        message_types.VoidMessage, SessionsResponseMessage,
        path='profile/wishes', name='getSessionsInWishlist',
        http_method='GET')
    def get_sessions_in_wishlist(self, request):
        """Get all sessions from a user's wishlist."""
        profile = self._getProfileFromUser()

        return self._get_wishlist_sessions_as_message(profile)

    @endpoints.method(
        containers.SESSION_REQUEST, SessionsResponseMessage,
        http_method='DELETE', path='profile/wish/{session}',
        name='deleteSessionInWishlist')
    def delete_session_in_wishlist(self, request):
        """Delete a session from a user's wishlist."""
        profile = self._getProfileFromUser()
        session = self._get_entity_by_key(request.session)

        profile.sessions_wishlist.remove(session.key)
        profile.put()

        return self._get_wishlist_sessions_as_message(profile)

    @endpoints.method(
        message_types.VoidMessage, SessionsResponseMessage,
        path='sessions/non-workshop-before-seven',
        name='getSessionsNonWorkshopBefore7pm', http_method='GET')
    def get_sessions_nonworkshop_before_7pm(self, request):
        """Get all non-workshop sessions occurring before or at 7PM."""
        # Ideally we would hard-code a list of supported session types
        non_workshop_sessions = Session.query().filter(
            Session.type_of_session != 'workshop').fetch(
            projection=[Session.type_of_session])
        # Get the unique "list" of actual session types
        non_workshop_sessions = set([
            session.type_of_session for
            session in non_workshop_sessions if session.type_of_session])

        seven_pm = datetime.strptime('19:00', '%H:%M').time()

        sessions = Session.query(
            Session.type_of_session.IN(non_workshop_sessions)).filter(
            Session.start_time <= seven_pm).fetch()

        return SessionsResponseMessage(
            sessions=[session.to_message() for session in sessions])

    @endpoints.method(
        containers.SESSIONS_BY_DATE_REQUEST, SessionsResponseMessage,
        path='conference/{conference}/sessions/date/{date}',
        name='getConferenceSessionsByDate', http_method='GET')
    def get_conference_sessions_by_date(self, request):
        """Get all conference sessions for a specified date."""
        try:
            date = datetime.strptime(request.date, "%Y-%m-%d").date()
        except ValueError:
            raise endpoints.BadRequestException(
                "Date must be in format YYYY-MM-DD.")

        conference = self._get_entity_by_key(request.conference)
        sessions = Session.query(ancestor=conference.key).filter(
            Session.date == date).order(Session.start_time).fetch()

        return SessionsResponseMessage(
            sessions=[session.to_message() for session in sessions])

    @endpoints.method(
        containers.CONFERENCE_REQUEST, SessionsResponseMessage,
        path='conference/{conference}/sessions/interactive',
        name='getInteractiveConferenceSessions', http_method='GET')
    def get_interactive_conference_sessions(self, request):
        """Get all conference sessions that are interactive."""
        conference = self._get_entity_by_key(request.conference)

        sessions = Session.query(ancestor=conference.key).filter(
            Session.type_of_session.IN(INTERACTIVE_SESSION_TYPES)).fetch()

        return SessionsResponseMessage(
            sessions=[session.to_message() for session in sessions])

    @endpoints.method(
        message_types.VoidMessage, StringMessage,
        path='speaker/featured', name='getFeaturedSpeaker', http_method='GET')
    def get_featured_speaker(self, request):
        """Get the speaker to feature from memcache."""
        return StringMessage(
            data=memcache.get(MEMCACHE_FEATURED_SPEAKER) or "")

    # end: brenj additions to conference.py
    #######################################

api = endpoints.api_server([ConferenceApi]) # register API
