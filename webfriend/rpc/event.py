from __future__ import absolute_import


class Event(object):
    def __init__(self, rpc, event, payload=None):
        self.rpc     = rpc
        self.event   = event
        self.payload = {}

        if isinstance(payload, dict):
            self.payload = payload

    def to_json(self):
        return {
            'event':   str(self),
            'payload': self.payload,
        }

    def get(self, key, fallback=None):
        return self.payload.get(key, fallback)

    def __getitem__(self, key):
        if key == '__payload__':
            return self.payload
        else:
            return self.get(key)

    def __repr__(self):
        return '{}.{}'.format(self.rpc.domain, self.event)

    def __str__(self):
        return self.__repr__()
