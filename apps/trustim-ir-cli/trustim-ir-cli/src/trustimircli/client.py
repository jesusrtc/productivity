import sys
import time
from urllib.parse import urlencode

import click

from trustimircli.config import get_auth, get_host, get_cert_name


class AuthError(Exception):
    pass


def get_session():
    auth = get_auth()
    if not auth.get('cookies'):
        click.echo('Not logged in. Run: ir auth login', err=True)
        sys.exit(1)
    host = auth.get('host') or get_host()
    return host, auth['cookies']


def list_keychain_identities():
    """List all client TLS identities from the macOS keychain.
    Returns list of (subject_name, identity_ref) tuples.
    """
    try:
        import Security
    except ImportError:
        return []

    query = {
        Security.kSecClass: Security.kSecClassIdentity,
        Security.kSecReturnRef: True,
        Security.kSecMatchLimit: Security.kSecMatchLimitAll,
    }
    status, identities = Security.SecItemCopyMatching(query, None)
    if status != 0 or not identities:
        return []

    results = []
    for ident in identities:
        _, cert_ref = Security.SecIdentityCopyCertificate(ident, None)
        if cert_ref:
            subject = str(Security.SecCertificateCopySubjectSummary(cert_ref) or '')
            if subject:
                results.append((subject, ident))
    return results


def _find_mtls_identity():
    """Find a usable client TLS identity from the macOS keychain.
    If a cert name is configured, uses that. Otherwise auto-detects,
    preferring personal certs (short username-like names) over MDM/localhost.
    Returns the identity ref, or None if not on macOS / not found.
    """
    candidates = list_keychain_identities()
    if not candidates:
        return None

    # If user configured a cert name, match it
    configured = get_cert_name()
    if configured:
        for subject, ident in candidates:
            if subject == configured:
                return ident
        # Partial match
        for subject, ident in candidates:
            if configured.lower() in subject.lower():
                return ident

    # Auto-detect: try matching system username first
    import os
    try:
        username = os.getlogin()
    except OSError:
        username = os.environ.get('USER', '')

    if username:
        for subject, ident in candidates:
            if subject == username:
                return ident

    # Filter out localhost, prefer non-MDM
    usable = [(s, i) for s, i in candidates if s != 'localhost']
    if not usable:
        return None

    for subject, ident in usable:
        if len(subject) < 30 and '-' not in subject and 'MDM' not in subject:
            return ident

    return usable[0][1]


# Cache the identity lookup per process (reset on import)
_cached_identity = None
_identity_resolved = False


def _get_identity():
    global _cached_identity, _identity_resolved
    if not _identity_resolved:
        _cached_identity = _find_mtls_identity()
        _identity_resolved = True
    return _cached_identity


class _Response:
    """Minimal response object matching the interface we use."""
    def __init__(self, status_code, text, headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


def _native_request(method, url, cookies, data=None):
    """Make an HTTP request using macOS NSURLSession (supports mTLS via keychain).
    Uses delegate-only approach (no completion handler) since they can't be mixed.
    """
    import objc
    from Foundation import (
        NSObject, NSURLSession, NSURLSessionConfiguration,
        NSMutableURLRequest, NSURL, NSRunLoop, NSDate, NSData,
        NSURLCredential, NSURLSessionAuthChallengeUseCredential,
    )

    identity = _get_identity()

    class _Delegate(NSObject):
        def init(self):
            self = objc.super(_Delegate, self).init()
            if self is None:
                return None
            self.result_data = b''
            self.result_status = None
            self.result_headers = {}
            self.result_error = None
            self.done = False
            return self

        def URLSession_didReceiveChallenge_completionHandler_(self, session, challenge, handler):
            auth_method = challenge.protectionSpace().authenticationMethod()
            if auth_method == 'NSURLAuthenticationMethodClientCertificate' and identity:
                credential = NSURLCredential.credentialWithIdentity_certificates_persistence_(
                    identity, None, 0,
                )
                handler(NSURLSessionAuthChallengeUseCredential, credential)
                return
            handler(0, None)

        def URLSession_dataTask_didReceiveResponse_completionHandler_(self, session, task, response, handler):
            self.result_status = response.statusCode()
            all_headers = response.allHeaderFields()
            if all_headers:
                for key in all_headers:
                    self.result_headers[str(key)] = str(all_headers[key])
            handler(1)  # NSURLSessionResponseAllow

        def URLSession_dataTask_didReceiveData_(self, session, task, data):
            self.result_data += bytes(data)

        def URLSession_task_didCompleteWithError_(self, session, task, error):
            if error:
                self.result_error = str(error)
            self.done = True

    delegate = _Delegate.alloc().init()
    config = NSURLSessionConfiguration.defaultSessionConfiguration()
    session = NSURLSession.sessionWithConfiguration_delegate_delegateQueue_(config, delegate, None)

    ns_url = NSURL.URLWithString_(url)
    req = NSMutableURLRequest.requestWithURL_(ns_url)
    req.setHTTPMethod_(method.upper())
    req.setValue_forHTTPHeaderField_(cookies, 'Cookie')
    req.setValue_forHTTPHeaderField_('text/html', 'Accept')

    if data:
        if isinstance(data, dict):
            body_bytes = urlencode(data).encode('utf-8')
        else:
            body_bytes = data if isinstance(data, bytes) else data.encode('utf-8')
        req.setHTTPBody_(NSData.dataWithBytes_length_(body_bytes, len(body_bytes)))
        req.setValue_forHTTPHeaderField_('application/x-www-form-urlencoded', 'Content-Type')

    task = session.dataTaskWithRequest_(req)
    task.resume()

    deadline = time.time() + 30
    while not delegate.done and time.time() < deadline:
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))

    if not delegate.done:
        task.cancel()
        return _Response(0, '')
    if delegate.result_error and delegate.result_status is None:
        return _Response(0, '')

    body = delegate.result_data.decode('utf-8', errors='replace')
    return _Response(delegate.result_status, body, delegate.result_headers)


def _requests_request(method, url, cookies, data=None):
    """Fallback: plain requests (no mTLS)."""
    import requests as req_lib
    try:
        resp = req_lib.request(
            method, url,
            headers={'Cookie': cookies, 'Accept': 'text/html'},
            data=data,
            allow_redirects=False,
            timeout=30,
        )
    except req_lib.ConnectionError:
        return _Response(0, '')
    except req_lib.Timeout:
        return _Response(0, '')
    return _Response(resp.status_code, resp.text, dict(resp.headers))


def _has_native():
    """Check if we can use NSURLSession."""
    try:
        from Foundation import NSURLSession  # noqa: F401
        return True
    except ImportError:
        return False


def _check_response(resp):
    if resp.status_code == 0:
        raise AuthError('Connection failed. Check VPN and try again.')
    if resp.status_code in (401, 403):
        raise AuthError('Session expired. Run: ir auth login')
    if resp.status_code == 302:
        location = resp.headers.get('Location', '')
        if 'sso' in location.lower() or 'login' in location.lower():
            raise AuthError('Session expired. Run: ir auth login')
    if resp.status_code == 404:
        click.echo('Error: Not found (404)', err=True)
        sys.exit(1)
    if resp.status_code >= 400:
        click.echo(f'Error: HTTP {resp.status_code}', err=True)
        sys.exit(1)


def request(method, path, data=None, params=None):
    host, cookies = get_session()
    url = f'{host.rstrip("/")}{path}'
    if params:
        url += '?' + urlencode(params)

    if _has_native():
        resp = _native_request(method, url, cookies, data=data)
    else:
        resp = _requests_request(method, url, cookies, data=data)

    try:
        _check_response(resp)
    except AuthError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    return resp


def get(path, params=None):
    return request('GET', path, params=params)


def post(path, data=None):
    return request('POST', path, data=data)
