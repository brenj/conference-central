#!/usr/bin/env python

"""models.py

Udacity conference server-side Python App Engine data & ProtoRPC models

$Id: models.py,v 1.1 2014/05/24 22:01:10 wesc Exp $

created/forked from conferences.py by wesc on 2014 may 24

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'

import httplib
import endpoints
from protorpc import messages, message_types
from google.appengine.ext import ndb

class ConflictException(endpoints.ServiceException):
    """ConflictException -- exception mapped to HTTP 409 response"""
    http_status = httplib.CONFLICT

class Profile(ndb.Model):
    """Profile -- User profile object"""
    displayName = ndb.StringProperty()
    mainEmail = ndb.StringProperty()
    teeShirtSize = ndb.StringProperty(default='NOT_SPECIFIED')
    conferenceKeysToAttend = ndb.StringProperty(repeated=True)
    sessions_wishlist = ndb.KeyProperty(kind='Session', repeated=True)

class ProfileMiniForm(messages.Message):
    """ProfileMiniForm -- update Profile form message"""
    displayName = messages.StringField(1)
    teeShirtSize = messages.EnumField('TeeShirtSize', 2)

class ProfileForm(messages.Message):
    """ProfileForm -- Profile outbound form message"""
    displayName = messages.StringField(1)
    mainEmail = messages.StringField(2)
    teeShirtSize = messages.EnumField('TeeShirtSize', 3)
    conferenceKeysToAttend = messages.StringField(4, repeated=True)

class StringMessage(messages.Message):
    """StringMessage-- outbound (single) string message"""
    data = messages.StringField(1, required=True)

class BooleanMessage(messages.Message):
    """BooleanMessage-- outbound Boolean value message"""
    data = messages.BooleanField(1)

class Conference(ndb.Model):
    """Conference -- Conference object"""
    name            = ndb.StringProperty(required=True)
    description     = ndb.StringProperty()
    organizerUserId = ndb.StringProperty()
    topics          = ndb.StringProperty(repeated=True)
    city            = ndb.StringProperty()
    startDate       = ndb.DateProperty()
    month           = ndb.IntegerProperty() # TODO: do we need for indexing like Java?
    endDate         = ndb.DateProperty()
    maxAttendees    = ndb.IntegerProperty()
    seatsAvailable  = ndb.IntegerProperty()

class ConferenceForm(messages.Message):
    """ConferenceForm -- Conference outbound form message"""
    name            = messages.StringField(1)
    description     = messages.StringField(2)
    organizerUserId = messages.StringField(3)
    topics          = messages.StringField(4, repeated=True)
    city            = messages.StringField(5)
    startDate       = messages.StringField(6) #DateTimeField()
    month           = messages.IntegerField(7)
    maxAttendees    = messages.IntegerField(8)
    seatsAvailable  = messages.IntegerField(9)
    endDate         = messages.StringField(10) #DateTimeField()
    websafeKey      = messages.StringField(11)
    organizerDisplayName = messages.StringField(12)

class ConferenceForms(messages.Message):
    """ConferenceForms -- multiple Conference outbound form message"""
    items = messages.MessageField(ConferenceForm, 1, repeated=True)

class TeeShirtSize(messages.Enum):
    """TeeShirtSize -- t-shirt size enumeration value"""
    NOT_SPECIFIED = 1
    XS_M = 2
    XS_W = 3
    S_M = 4
    S_W = 5
    M_M = 6
    M_W = 7
    L_M = 8
    L_W = 9
    XL_M = 10
    XL_W = 11
    XXL_M = 12
    XXL_W = 13
    XXXL_M = 14
    XXXL_W = 15

class ConferenceQueryForm(messages.Message):
    """ConferenceQueryForm -- Conference query inbound form message"""
    field = messages.StringField(1)
    operator = messages.StringField(2)
    value = messages.StringField(3)

class ConferenceQueryForms(messages.Message):
    """ConferenceQueryForms -- multiple ConferenceQueryForm inbound form message"""
    filters = messages.MessageField(ConferenceQueryForm, 1, repeated=True)

# begin: brenj additions to models.py
#####################################


class SpeakerRequestMessage(messages.Message):

    """ProtoRPC request message for a speaker."""

    name = messages.StringField(1, required=True)


class SpeakerResponseMessage(messages.Message):

    """ProtoRPC response message for a speaker."""

    id = messages.StringField(1, required=True)
    name = messages.StringField(2, required=True)


class SessionRequestMessage(messages.Message):

    """ProtoRPC request message for a session."""

    name = messages.StringField(1, required=True)
    highlights = messages.StringField(2)
    speaker_key = messages.StringField(3, required=True)
    duration = messages.StringField(4)
    type_of_session = messages.StringField(5, required=True)
    date = messages.StringField(6, required=True)
    start_time = messages.StringField(7, required=True)


class SessionResponseMessage(messages.Message):

    """ProtoRPC response message for a session."""

    id = messages.StringField(1, required=True)
    name = messages.StringField(2, required=True)
    highlights = messages.StringField(3)
    speaker = messages.MessageField(SpeakerResponseMessage, 4, required=True)
    duration = messages.StringField(5)
    type_of_session = messages.StringField(6, required=True)
    date = messages.StringField(7, required=True)
    start_time = messages.StringField(8, required=True)


class SessionsResponseMessage(messages.Message):

    """ProtoRPC message for a collection of sessions."""

    sessions = messages.MessageField(SessionResponseMessage, 1, repeated=True)


class Speaker(ndb.Model):

    """A speaker at a conference session."""

    name = ndb.StringProperty(required=True)

    def to_message(self):
        """Convert a ndb speaker to a speaker response message."""
        return SpeakerResponseMessage(id=self.key.urlsafe(), name=self.name)

    def session_set(self):
        """Set of sessions speaker is participating in."""
        return Session.query(Session.speaker_key == self.key)


class Session(ndb.Model):

    """A session (e.g. talk, workshop) given at a `Conference`."""

    name = ndb.StringProperty(required=True)
    highlights = ndb.StringProperty()
    speaker_key = ndb.KeyProperty(kind='Speaker', required=True)
    duration = ndb.IntegerProperty()
    type_of_session = ndb.StringProperty(default='talk')
    date = ndb.DateProperty(required=True)
    start_time = ndb.TimeProperty(required=True)

    def to_message(self):
        """Convert a ndb session to a session message."""
        speaker = self.speaker_key.get()
        return SessionResponseMessage(
            id=self.key.urlsafe(), name=self.name, highlights=self.highlights,
            speaker=speaker.to_message(), duration=self.duration,
            type_of_session=self.type_of_session, date=str(self.date),
            start_time=str(self.start_time))


# end: brenj additions to models.py
###################################
