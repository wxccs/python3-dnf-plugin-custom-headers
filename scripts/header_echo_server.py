#!/usr/bin/env python3
"""Tiny HTTP server used by the smoke test.

Records the request line and all request headers of every incoming
request into a log file. When a document root is given, files under it
are actually served (so package downloads can be exercised end to end);
otherwise every request is answered with 404 - which is still enough to
prove which headers DNF sent upstream.

Usage: header_echo_server.py [port] [logfile] [docroot]
"""

import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18089
LOG_FILE = sys.argv[2] if len(sys.argv) > 2 else '/tmp/header_echo.log'
DOC_ROOT = os.path.realpath(sys.argv[3]) if len(sys.argv) > 3 else None


class HeaderEchoHandler(BaseHTTPRequestHandler):

    def _record(self):
        with open(LOG_FILE, 'a') as log:
            log.write('=== %s %s\n' % (self.command, self.path))
            for name, value in self.headers.items():
                log.write('%s: %s\n' % (name, value))

    def _serve_file(self):
        if DOC_ROOT is None:
            self.send_response(404)
            self.end_headers()
            return
        path = os.path.realpath(
            os.path.join(DOC_ROOT, self.path.lstrip('/')))
        if not path.startswith(DOC_ROOT + os.sep) or not os.path.isfile(path):
            self.send_response(404)
            self.end_headers()
            return
        with open(path, 'rb') as body:
            self.send_response(200)
            self.send_header('Content-Length', str(os.fstat(body.fileno()).st_size))
            self.end_headers()
            if self.command == 'GET':
                self.wfile.write(body.read())

    def do_GET(self):
        self._record()
        self._serve_file()

    do_HEAD = do_GET

    def log_message(self, fmt, *args):
        pass  # keep the console quiet


def main():
    HTTPServer(('127.0.0.1', PORT), HeaderEchoHandler).serve_forever()


if __name__ == '__main__':
    main()
