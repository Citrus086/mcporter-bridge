import argparse
import os
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
        app.run()


if __name__ == "__main__":
    main()

