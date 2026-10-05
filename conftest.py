"""Keep legacy app imports and migration away from a developer's real projects."""
import os
import sys
import tempfile


def pytest_sessionstart(session):
    session.clipper_test_directory = tempfile.TemporaryDirectory(prefix='clipper-tests-')
    session.clipper_original_env = {key: os.environ.get(key) for key in ('WORK_DIR', 'OUT_DIR')}
    for key, child in (('WORK_DIR', 'work'), ('OUT_DIR', 'clips')):
        os.environ[key] = os.path.join(session.clipper_test_directory.name, child)


def pytest_sessionfinish(session, exitstatus):
    app = sys.modules.get('app')
    service = getattr(getattr(getattr(app, 'app', None), 'state', None), 'studio', None)
    if service:
        service.queue.close()
    for key, value in session.clipper_original_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    session.clipper_test_directory.cleanup()
