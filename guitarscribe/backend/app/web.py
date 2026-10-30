"""Single-host invited web preview; independent work directory, no public dev server."""
import base64
import binascii
import hashlib
import hmac
import json
import os
from pathlib import Path

from fastapi import FastAPI
from starlette.responses import PlainTextResponse
from starlette.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from .api import app as analysis_app
from .services.rate_limit import SubmissionRateLimiter


class InvitationGate:
    def __init__(self, app, username: str, password: str):
        self.app=app
        self.expected=hashlib.sha256(f'{username}:{password}'.encode()).digest()
        self.failures=SubmissionRateLimiter(10,60)

    async def __call__(self,scope,receive,send):
        if scope['type']!='http':
            return await self.app(scope,receive,send)
        headers=dict(scope.get('headers',[]));credential=b''
        try:
            scheme,encoded=headers.get(b'authorization',b'').split(b' ',1)
            if scheme.lower()==b'basic':credential=base64.b64decode(encoded,validate=True)
        except (ValueError,binascii.Error):pass
        if not hmac.compare_digest(hashlib.sha256(credential).digest(),self.expected):
            allowed,retry=self.failures.allow((scope.get('client') or ('unknown',0))[0])
            response=PlainTextResponse('請輸入試用邀請帳號與密碼。' if allowed else '請稍後再試。',status_code=401 if allowed else 429,
                headers={'WWW-Authenticate':'Basic realm="GuitarScribe friends", charset="UTF-8"','Cache-Control':'no-store',**({'Retry-After':str(retry)} if not allowed else {})})
            return await response(scope,receive,send)
        return await self.app(scope,receive,send)


class FrontendFiles(StaticFiles):
    async def get_response(self,path,scope):
        # Only the sanitized production bundle is served. No historical listening packets.
        try:return await super().get_response(path,scope)
        except HTTPException as error:
            if error.status_code!=404:raise
            return await super().get_response('index.html',scope)


def create_app():
    secret=Path(os.environ['GUITARSCRIBE_WEB_ACCESS_FILE'])
    directory=Path(os.environ['GUITARSCRIBE_WEB_STATIC_DIR']).resolve()
    credentials=json.loads(secret.read_text())
    if not credentials.get('username') or len(credentials.get('password',''))<12:
        raise ValueError('Web preview requires a nonempty username and a password of at least 12 characters')
    if not (directory/'index.html').is_file():raise ValueError('Build the web frontend before starting')
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    app.mount('/backend',analysis_app)
    app.mount('/',FrontendFiles(directory=directory,html=True))
    app.add_middleware(InvitationGate,username=credentials['username'],password=credentials['password'])
    return app
