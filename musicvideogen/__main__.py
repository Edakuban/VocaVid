from __future__ import annotations

import argparse
import logging


def main() -> None:
    parser = argparse.ArgumentParser(prog="musicvideogen")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", default=8000, type=int)
    run = sub.add_parser("run")
    run.add_argument("--project", type=int, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.command == "serve":
        import uvicorn

        uvicorn.run("musicvideogen.app:app", host=args.host, port=args.port, reload=False)
    elif args.command == "run":
        from pathlib import Path

        from .app import APP_ROOT, DB_PATH
        from .pipeline import Pipeline
        from .store import Store

        pipeline = Pipeline(Store(DB_PATH), APP_ROOT / "outputs")
        pipeline.align_evenly(args.project)
        pipeline.build_segments(args.project)
        pipeline.generate_scene_plan(args.project)
        pipeline.generate_prompts(args.project)
        pipeline.generate_images(args.project)
        pipeline.generate_clips(args.project)
        pipeline.assemble(args.project)
        print(f"Rendered project {args.project}")


if __name__ == "__main__":
    main()
