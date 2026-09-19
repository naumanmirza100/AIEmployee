"""The one error type the PM services raise.

Views turn it into their usual error body — {"status": "error", "message": …}
plus an optional "code" and extra keys — with `ServiceError.response()`.
"""


class ServiceError(Exception):
    """A request the service refuses. Nothing has been saved when this is raised."""

    def __init__(self, message, *, http_status=400, code=None, **extra):
        super().__init__(message)
        self.message = message
        self.http_status = http_status
        self.code = code
        self.extra = extra

    def payload(self):
        body = {'status': 'error', 'message': self.message}
        if self.code:
            body['code'] = self.code
        body.update(self.extra)
        return body

    def response(self):
        from rest_framework.response import Response
        return Response(self.payload(), status=self.http_status)


def not_found(message):
    return ServiceError(message, http_status=404)


def forbidden(message):
    return ServiceError(message, http_status=403)
