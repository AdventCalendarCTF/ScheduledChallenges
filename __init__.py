from __future__ import division  # Use floating point for math calculations

import math
import datetime

from flask import Blueprint, abort

from CTFd.models import Challenges, Solves, db
from CTFd.plugins import register_plugin_assets_directory
from CTFd.plugins.challenges import CHALLENGE_CLASSES, BaseChallenge
from CTFd.utils.modes import get_model
from CTFd.api.v1.challenges import ChallengeList, Challenge, ChallengeSolves

from CTFd.utils.user import (
    get_current_user_attrs,
    is_admin,
)
from pathlib import Path

from CTFd.utils.plugins import override_template


class ScheduledChallenges(Challenges):
    __mapper_args__ = {"polymorphic_identity": "scheduled"}
    id = db.Column(
        db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE"), primary_key=True
    )
    activation_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def sched_status(self):
        if self.state == "hidden":
            return "hidden"

        now = datetime.datetime.now()
        if now > self.activation_date:
            return "visible"
        return "scheduled"



class ScheduledChallenge(BaseChallenge):
    id = "scheduled"  # Unique identifier used to register challenges
    name = "scheduled"  # Name of a challenge type
    templates = {  # Handlebars templates used for each aspect of challenge editing & viewing
        "create": "/plugins/scheduled_challenges/assets/create.html",
        "update": "/plugins/scheduled_challenges/assets/update.html",
        "view": "/plugins/scheduled_challenges/assets/view.html",
    }
    scripts = {  # Scripts that are loaded when a template is loaded
        "create": "/plugins/scheduled_challenges/assets/create.js",
        "update": "/plugins/scheduled_challenges/assets/update.js",
        "view": "/plugins/scheduled_challenges/assets/view.js",
    }
    # Route at which files are accessible. This must be registered using register_plugin_assets_directory()
    route = "/plugins/scheduled_challenges/assets/"
    # Blueprint used to access the static_folder directory.
    blueprint = Blueprint(
        "scheduled_challenges",
        __name__,
        template_folder="templates",
        static_folder="assets",
    )
    challenge_model = ScheduledChallenges

    @classmethod
    def read(cls, challenge):
        """
        This method is in used to access the data of a challenge in a format processable by the front end.

        :param challenge:
        :return: Challenge object, data dictionary to be returned to the user
        """
        challenge = ScheduledChallenges.query.filter_by(id=challenge.id).first()
        data = {
            "id": challenge.id,
            "name": challenge.name,
            "value": challenge.value,
            "activation_date": challenge.activation_date.isoformat(),
            "description": challenge.description,
            "connection_info": challenge.connection_info,
            "category": challenge.category,
            "state": challenge.state,
            "max_attempts": challenge.max_attempts,
            "type": challenge.type,
            "type_data": {
                "id": cls.id,
                "name": cls.name,
                "templates": cls.templates,
                "scripts": cls.scripts,
            },
        }
        if challenge.state == "visible":
            if datetime.datetime.now() < challenge.activation_date:
                data["state"] = "scheduled"
        return data
    
    @classmethod
    def attempt(cls, challenge, request):
        if get_current_user_attrs():
            if not is_admin():
                now = datetime.datetime.now()
                if challenge.activation_date > now:
                    abort(404)
        return super().attempt(challenge, request)


_previous_get_challenges = ChallengeList.get
_previous_get_challenge = Challenge.get
_previous_get_solves = ChallengeSolves.get

def get_challenges_with_scheduler(self, *args, **kwargs):
    rep = _previous_get_challenges(self, *args, **kwargs)
    if get_current_user_attrs():
        if is_admin():
            return rep
    if not rep['success']:
        return rep
    now = datetime.datetime.now()
    id_to_be_removed = []
    for chal in rep['data']:
        if chal['type'] != 'scheduled':
            continue
        challenge = ScheduledChallenges.query.filter_by(id=chal['id']).first()
        if challenge.activation_date > now:
            id_to_be_removed.append(chal['id'])
    rep['data'] = list(filter(lambda chal: chal['id'] not in id_to_be_removed, rep['data']))
    return rep

def get_challenge_with_scheduler(self, *args, **kwargs):
    rep = _previous_get_challenge(self, *args, **kwargs)
    if get_current_user_attrs():
        if is_admin():
            return rep
    if not rep['success']:
        return rep
    if rep['data']['type'] != 'scheduled':
        return rep
    now = datetime.datetime.now()
    challenge = ScheduledChallenges.query.filter_by(id=rep['data']['id']).first()
    if challenge.activation_date > now:
            abort(404)
    return rep

def get_solves_with_scheduler(self, challenge_id, *args, **kwargs):
    challenge = Challenges.query.filter_by(id=challenge_id).first_or_404()
    if challenge.type != 'scheduled':
        return _previous_get_solves(self, challenge_id, *args, **kwargs)
    now = datetime.datetime.now()
    challenge = ScheduledChallenges.query.filter_by(id=challenge_id).first()
    if challenge.activation_date > now:
            abort(404)
    return _previous_get_solves(self, challenge_id, *args, **kwargs)
    

def load(app):
    app.db.create_all()
    CHALLENGE_CLASSES["scheduled"] = ScheduledChallenge
    register_plugin_assets_directory(
        app, base_path="/plugins/scheduled_challenges/assets/"
    )
    ChallengeList.get = get_challenges_with_scheduler
    Challenge.get = get_challenge_with_scheduler
    ChallengeSolves.get = get_solves_with_scheduler

    dir_path = Path(__file__).parent.resolve()
    template_path = dir_path / 'assets' / 'admin_challenges.html'
    override_template('admin/challenges/challenges.html', open(template_path).read())

