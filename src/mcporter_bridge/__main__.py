import argparse
import os
import sys
from pathlib import Path

try:
    from mcporter_bridge.server import app
except ImportError:
    # Editable install fallback: some Python distributions (e.g. Anaconda)
    # skip .pth files when the venv directory is marked UF_HIDDEN on macOS.
    # If we detect the typical src/ layout, add it to sys.path manually.
    _src_dir = Path(__file__).resolve().parent.parent
    if _src_dir.name == "src" and (_src_dir / "mcporter_bridge" / "__init__.py").exists():
        sys.path.insert(0, str(_src_dir))
    from mcporter_bridge.server import app


def main() -> None:
    parser = argparse.ArgumentParser(description="mcporter-bridge MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default="stdio",
        help="Transport protocol (default: stdio)"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="HTTP host (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="HTTP port (default: 8765)"
    )
    args = parser.parse_args()

    if args.transport == "http":
        # HTTP 模式运行
        app.run(transport="streamable-http", host=args.host, port=args.port)
    elif args.transport == "sse":
        # SSE 模式运行
        app.run(transport="sse", host=args.host, port=args.port)
    else:
        # 默认 stdio 模式
        app.run(show_banner=False)


if __name__ == "__main__":
    main()
