import argparse

import uvicorn


def main():
    ap = argparse.ArgumentParser(description="Run the MiP dashboard on localhost.")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    uvicorn.run("wowpy.dashboard.server:app", host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
