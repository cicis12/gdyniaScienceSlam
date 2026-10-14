"""Reject excessive public submissions before reading or parsing their bodies."""
import logging
import os
from limits import parse_many
from limits.storage import storage_from_string
from limits.strategies import FixedWindowRateLimiter
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.middleware.body_limit import RequestBodyLimitMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)
form_rate_storage = storage_from_string(os.getenv('RATE_LIMIT_STORAGE_URI', 'memory://'))
form_rate_limiter = FixedWindowRateLimiter(form_rate_storage)
FORM_RATES = parse_many(os.getenv('FORM_SUBMISSION_RATE_LIMIT', '10/minute;100/hour'))


class RequestLimitsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        path = scope['path'].rstrip('/')
        headers = Headers(scope=scope)
        limit = 160 * 1024 * 1024  # Configuration ZIP imports use up to 150 MB.
        if path == '/api/forms/submit' and scope['method'] == 'POST':
            address = (scope.get('client') or ('unknown',))[0]
            def allowed():
                return all(form_rate_limiter.hit(rate, 'form-submissions', address) for rate in FORM_RATES)
            try:
                accepted = await run_in_threadpool(allowed)
            except Exception:
                logger.exception('Form rate limit storage unavailable')
                response = JSONResponse({'detail': 'Formularz jest chwilowo niedostępny.'}, status_code=503)
                return await response(scope, receive, send)
            if not accepted:
                response = JSONResponse({'detail': 'Zbyt wiele prób. Spróbuj ponownie później.'},
                                        status_code=429, headers={'Retry-After': '60'})
                return await response(scope, receive, send)
            limit = 110 * 1024 * 1024 if headers.get('content-type', '').lower().startswith('multipart/form-data') else 256 * 1024
        elif path in {'/adminLogin', '/vote/login'}:
            limit = 16 * 1024
        try:
            declared_size = int(headers.get('content-length', '0'))
        except ValueError:
            declared_size = -1
        if declared_size < 0:
            return await JSONResponse({'detail': 'Nieprawidłowe żądanie.'}, status_code=400)(scope, receive, send)
        if declared_size > limit:
            return await JSONResponse({'detail': 'Przesłane dane są zbyt duże.'}, status_code=413)(scope, receive, send)
        await RequestBodyLimitMiddleware(self.app, max_body_size=limit)(scope, receive, send)
