from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory


source = Path(__file__).resolve().parents[1] / 'site'
with TemporaryDirectory(prefix='prpl-pages-') as directory:
    root = Path(directory)
    (root / 'prplmesh-lab').symlink_to(source, target_is_directory=True)
    for child in source.iterdir():
        (root / child.name).symlink_to(child, target_is_directory=child.is_dir())
    server = ThreadingHTTPServer(('127.0.0.1', 4178), partial(SimpleHTTPRequestHandler, directory=directory))
    server.serve_forever()
