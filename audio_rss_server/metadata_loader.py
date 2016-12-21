"""
Metadata loading
"""

import datetime
import time


class MetaDataLoader:
    """
    This is a base class for metadata loaders which poll databases for
    relevant metadata.
    """
    #: Minimum delay between requests for the given API endpoint. 
    POLL_DELAY = 0.2
    API_ENDPOINT = None

    def __init__(self, *args, **kwargs):
        self._last_poll = None
        self._poll_delay = datetime.timedelta(seconds=self.POLL_DELAY)

        if self.API_ENDPOINT is None:
            msg = 'This is an abstract base class, all subclasses are reuqired '
                  'to specify a non-None value for API_ENDPOINT.'
            raise NotImplementedError(msg)

    def make_request(self, *args, raise_on_early_=False, **kwargs):
        """
        This is a wrapper around the actual request loader, to enforce polling
        delays.

        :param raise_on_early_:
            If true, a :class:`PollDelayIncomplete` exception will be raised if
            a request is made early.
        """
        if self._last_poll is not None:
            time_elapsed = datetime.datetime.utcnow() - self._last_poll

            remaining_time = self._poll_delay - time_elapsed
            remaining_time /= datetime.timedelta(seconds=1)

            if time_elapsed < self._poll_delay:
                if raise_on_early_:
                    raise PollDelayIncomplete(remaining_time)
                else:
                    time.sleep(remaining_time)

        old_poll = self._last_poll
        self._last_poll = datetime.datetime.utcnow()

        try:
            return self.make_request_raw(self, *args, **kwargs)
        except Exception as e:
            # We'll say last poll only counts if there was no exception.
            self._last_poll = old_poll
            raise e


class PollDelayIncomplete(Exception):
    def __init__(self, *args, time_remaining=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.time_remaining = time_remaining