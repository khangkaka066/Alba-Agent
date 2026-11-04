"""A small team model."""

from settings import build_settings


class Team:
    def __init__(self, name, roles=[], settings=None):
        self.name = name
        self.roles = roles
        self.settings = build_settings(settings)

    def add_role(self, role):
        if role not in self.roles:
            self.roles.append(role)

    def can_add_role(self):
        return len(self.roles) < self.settings["limits"]["roles"]
