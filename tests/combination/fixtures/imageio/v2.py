"""Discard CI camera frames; do not claim a recording was produced."""


class Writer:
    def append_data(self, frame):
        pass

    def close(self):
        pass


def get_writer(*args, **kwargs):
    return Writer()
