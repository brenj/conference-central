#!/usr/bin/env python

"""
main.py -- Udacity conference server-side Python App Engine
    HTTP controller handlers for memcache & task queue access

$Id$

created by wesc on 2014 may 24

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'

import webapp2
from google.appengine.api import app_identity
from google.appengine.api import mail
from google.appengine.api import memcache
from google.appengine.ext import ndb

from conference import ConferenceApi, MEMCACHE_FEATURED_SPEAKER
from models import Session

class SetAnnouncementHandler(webapp2.RequestHandler):
    def get(self):
        """Set Announcement in Memcache."""
        ConferenceApi._cacheAnnouncement()
        self.response.set_status(204)


class SendConfirmationEmailHandler(webapp2.RequestHandler):
    def post(self):
        """Send email confirming Conference creation."""
        mail.send_mail(
            'noreply@%s.appspotmail.com' % (
                app_identity.get_application_id()),     # from
            self.request.get('email'),                  # to
            'You created a new Conference!',            # subj
            'Hi, you have created a following '         # body
            'conference:\r\n\r\n%s' % self.request.get(
                'conferenceInfo')
        )


# begin: brenj additions to main.py
###################################

class StoreFeaturedSpeaker(webapp2.RequestHandler):

    """Handle storing a featured speaker."""

    def post(self):
        """Store a featured speaker in memcache if meets requirements."""
        conference = ndb.Key(urlsafe=self.request.get('conference_key')).get()
        speaker = ndb.Key(urlsafe=self.request.get('speaker_key')).get()

        # Ancestor query means we get strongly-consistent results, which we
        # need because we just put a new session by this speaker
        conference_sessions_by_speaker = (
            Session.query(ancestor=conference.key).filter(
                Session.speaker_key == speaker.key).fetch(
                projection=[Session.name]))

        if len(conference_sessions_by_speaker) > 1:
            session_names = [session.name for session in
                             conference_sessions_by_speaker]
            featured_speaker_message = "{0}: {1}".format(
                speaker.name, ', '.join(session_names))
            memcache.set(MEMCACHE_FEATURED_SPEAKER, featured_speaker_message)

# end: brenj additions to main.py
#################################


app = webapp2.WSGIApplication([
    ('/crons/set_announcement', SetAnnouncementHandler),
    ('/tasks/send_confirmation_email', SendConfirmationEmailHandler),
    ('/tasks/store_featured_speaker', StoreFeaturedSpeaker)
], debug=True)
