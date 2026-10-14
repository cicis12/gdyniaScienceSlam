"""ASGI middleware keeps request streaming and body-limit errors intact."""
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse
from site_pages import page_for_path


class PublicContextMiddleware:
    def __init__(self, app, load_context, templates):
        self.app, self.load_context, self.templates = app, load_context, templates

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        request = Request(scope)
        path = scope['path']
        if not path.startswith('/static'):
            request.state.page_visibility, request.state.site_settings = await run_in_threadpool(self.load_context)
            page = page_for_path(path)
            if page and not request.state.page_visibility[page]:
                response = self.templates.TemplateResponse(request, 'client/unavailable.html', {
                    'request': request, 'page_name': 'unavailable',
                    'header_title': 'Strona niedostępna - Gdynia Science Slam',
                }, status_code=404)
                return await response(scope, receive, send)
        await self.app(scope, receive, send)


class AdminAccessMiddleware:
    def __init__(self, app, load_admin):
        self.app, self.load_admin = app, load_admin

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        request = Request(scope)
        path = scope['path']
        if path.startswith('/admin/') and path not in {'/admin/login', '/admin/form-submissions', '/admin/logout'}:
            try:
                admin = await run_in_threadpool(self.load_admin, request)
            except HTTPException:
                return await RedirectResponse('/admin/login', status_code=303)(scope, receive, send)
            request.state.admin = admin
            if not (admin.is_superadmin or admin.is_sysadmin) and not path.startswith(('/admin/uploads/', '/admin/video/', '/admin/admins')):
                response = (RedirectResponse('/admin/form-submissions', status_code=303)
                            if scope['method'] in {'GET', 'HEAD'} else PlainTextResponse('Superadmin access required.', 403))
                return await response(scope, receive, send)

        async def no_cache(message):
            if message['type'] == 'http.response.start' and path.startswith('/admin'):
                MutableHeaders(scope=message)['Cache-Control'] = 'no-store'
            await send(message)
        await self.app(scope, receive, no_cache)
