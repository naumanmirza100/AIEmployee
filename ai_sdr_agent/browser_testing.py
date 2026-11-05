"""What the browser tests (tests_browser.py) need: the frontend built to call the API on its own address, and a test
server that serves that build beside the API, so a real browser drives the real screens against the throwaway test
database, with one address and no CORS.

The build is kept in logs/browser_build and made again only when a file under PaPerProjectFront/src (or the build's
own settings) is newer than it. Without Node or Playwright's Chromium on the machine the browser tests skip and say
why; the API tests do not need either.
"""
import mimetypes
import os
import shutil
import subprocess
from pathlib import Path

from django.conf import settings

FRONTEND = Path(settings.BASE_DIR) / 'PaPerProjectFront'
BUILD_INPUTS = ('src', 'index.html', 'package.json', 'vite.config.js', 'public')


class Unavailable(Exception):
    """The browser tests cannot run on this machine; the message says what is missing."""


def build_dir():
    return Path(getattr(settings, 'BROWSER_TEST_BUILD_DIR', None) or Path(settings.BASE_DIR) / 'logs' / 'browser_build')


def _newest_input():
    newest = 0.0
    for name in BUILD_INPUTS:
        path = FRONTEND / name
        if path.is_file():
            newest = max(newest, path.stat().st_mtime)
        elif path.is_dir():
            for root, _dirs, files in os.walk(path):
                for file in files:
                    newest = max(newest, os.stat(os.path.join(root, file)).st_mtime)
    return newest


def frontend_build():
    """The frontend built with VITE_API_URL=/api; built now if missing or older than its source."""
    out = build_dir()
    stamp = out / 'index.html'
    if stamp.exists() and stamp.stat().st_mtime >= _newest_input():
        return out
    npx = shutil.which('npx') or shutil.which('npx.cmd')
    if not npx or not (FRONTEND / 'node_modules').exists():
        raise Unavailable('Node.js and the frontend packages (npm install in PaPerProjectFront) are needed to build '
                          'the screens.')
    result = subprocess.run(
        [npx, 'vite', 'build', '--outDir', str(out), '--emptyOutDir', '--logLevel', 'error'],
        cwd=FRONTEND, env={**os.environ, 'VITE_API_URL': '/api'}, capture_output=True, text=True,
        encoding='utf-8', errors='replace', timeout=900)
    if result.returncode != 0 or not stamp.exists():
        raise Unavailable(f'The frontend did not build: {(result.stderr or result.stdout)[-1500:]}')
    return out


def chromium():
    """A started Playwright and a headless Chromium, or Unavailable."""
    try:
        from playwright.sync_api import Error, sync_playwright
    except ImportError:
        raise Unavailable('Playwright is not installed: pip install playwright, then playwright install chromium.')
    playwright = sync_playwright().start()
    try:
        return playwright, playwright.chromium.launch()
    except Error:
        pass
    try:  # the full Chromium in headless mode, when only it (not the headless shell) was downloaded
        return playwright, playwright.chromium.launch(channel='chromium')
    except Error as exc:
        playwright.stop()
        raise Unavailable(f'Chromium could not start (run: playwright install chromium): {str(exc)[:300]}')


class BrowserThread:
    """Chromium on a thread of its own, driven step by step from the test.

    Playwright's sync API runs an event loop on the thread that starts it, and Django keeps database connections per
    async context: on the test's thread the test then got a new, empty in-memory database. Here every browser call
    runs on this one thread, and the test's thread stays an ordinary one.
    """

    def __init__(self):
        from concurrent.futures import ThreadPoolExecutor
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='browser')
        try:
            self.playwright, self.browser = self._pool.submit(chromium).result()
        except Exception:
            self._pool.shutdown()
            raise

    def run(self, fn, *args):
        return self._pool.submit(fn, *args).result()

    def close(self):
        def stop():
            self.browser.close()
            self.playwright.stop()
        self.run(stop)
        self._pool.shutdown()


class SpaHandler:
    """WSGI: /api/… (and Django's other paths) go to Django; everything else is a file of the build, or its
    index.html, so the frontend's own routes (/company/login, /ai-sdr/leads …) load the app."""

    DJANGO_PREFIXES = ('/api/', '/admin/', '/static/', '/media/')

    def __init__(self, application):
        self.application = application
        self.root = build_dir().resolve()

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '/')
        if path.startswith(self.DJANGO_PREFIXES):
            return self.application(environ, start_response)
        file = (self.root / path.lstrip('/')).resolve()
        if not file.is_file() or self.root not in file.parents:
            file = self.root / 'index.html'
        content_type = mimetypes.guess_type(str(file))[0] or 'application/octet-stream'
        body = file.read_bytes()
        start_response('200 OK', [('Content-Type', content_type), ('Content-Length', str(len(body)))])
        return [body]
