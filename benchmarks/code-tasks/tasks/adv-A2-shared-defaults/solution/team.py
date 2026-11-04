"""A small team model."""

from settings import build_settings


class Team:
    def __init__(self, name, roles=None, settings=None):
        self.name = name
        self.roles = list(roles) if roles is not None else []
        self.settings = build_settings(settings)

    def add_role(self, role):
        if role not in self.roles:
            self.roles.append(role)

    def can_add_role(self):
        return len(self.roles) < self.settings["limits"]["roles"]
