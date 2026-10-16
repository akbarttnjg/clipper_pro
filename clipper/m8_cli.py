"""CLI receipts are JSON; tokens are read from environment, never CLI arguments."""
import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from .m8_client import Client, ClientError


def main(argv=None):
    parser = argparse.ArgumentParser(description='Clipper M8 4.0.19')
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    commands = parser.add_subparsers(dest='mode', required=True)
    command = commands.add_parser('command');command.add_argument('action');command.add_argument('--args-file');command.add_argument('--command-id')
    commands.add_parser('mcp')
    worker = commands.add_parser('worker');worker.add_argument('--root', default=str(Path(__file__).resolve().parents[1]));worker.add_argument('--once', action='store_true')
    bootstrap = commands.add_parser('session');bootstrap.add_argument('--root', default=str(Path(__file__).resolve().parents[1]));bootstrap.add_argument('--workspace', default='solo');bootstrap.add_argument('--user', required=True);bootstrap.add_argument('--role', choices=['owner', 'editor', 'reviewer', 'publisher'], required=True);bootstrap.add_argument('--hours', type=int, default=24)
    args = parser.parse_args(argv)
    service = None
    try:
        if args.mode == 'command':
            values = json.loads(Path(args.args_file).read_text(encoding='utf-8')) if args.args_file else {}
            key = args.command_id or str(uuid.uuid4())
            result = Client(args.url).command(args.action, values, key)
            print(json.dumps({'command_id': key, 'result': result}, ensure_ascii=False, allow_nan=False));return 0
        if args.mode == 'mcp':
            from .m8_mcp import serve
            serve(Client(args.url));return 0
        try:
            from dotenv import load_dotenv
            load_dotenv(Path(args.root)/'.env', override=False)
            load_dotenv(Path(args.root)/'.env.pro', override=True)
        except ImportError:
            pass
        from .studio_service import StudioService
        from .config import Config, validate_brand
        from .storage import read_json
        from dataclasses import replace
        config=replace(Config(),**validate_brand(read_json(Path(args.root)/'brand.json',{})))
        service = StudioService(args.root, config, autostart=args.mode=='worker', recover=args.mode=='worker')
        m8 = service.integrations
        if args.mode == 'session':
            result = m8.workspaces.issue_session(m8.local_actor(args.workspace), {'user_id': args.user, 'role': args.role, 'hours': args.hours})
            print(json.dumps(result, ensure_ascii=False));return 0
        if args.once:
            print(json.dumps(m8.worker.tick(), ensure_ascii=False));return 0
        service.queue.start();service.imports.start()
        while True:
            m8.worker.tick();m8.webhooks.tick();m8.automation.tick();time.sleep(2)
    except ClientError as exc:
        print(json.dumps({'error': exc.receipt, 'http_status': exc.status}, ensure_ascii=False));return 3 if exc.status == 403 else 2
    except (ValueError, KeyError, OSError) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False));return 2
    except KeyboardInterrupt:
        return 130
    finally:
        if service:
            service.integrations.close();service.queue.close()
            if 'imports' in service.__dict__:service.imports.close()


if __name__ == '__main__':
    sys.exit(main())
