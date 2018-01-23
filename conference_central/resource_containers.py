"""Resource containers for Conference Central."""

import endpoints
import models
from protorpc import messages
from protorpc import message_types

CONF_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1))

CONF_POST_REQUEST = endpoints.ResourceContainer(
    models.ConferenceForm,
    websafeConferenceKey=messages.StringField(1))

SESSION_CONFERENCE_REQUEST = endpoints.ResourceContainer(
    models.SessionRequestMessage,
    conference=messages.StringField(1))

CONFERENCE_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    conference=messages.StringField(1))

SESSIONS_BY_TYPE_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    conference=messages.StringField(1),
    type_of_session=messages.StringField(2))

SESSIONS_BY_DATE_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    conference=messages.StringField(1),
    date=messages.StringField(2))

SESSIONS_BY_SPEAKER_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    speaker_key=messages.StringField(1))

SESSION_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    session=messages.StringField(1))
