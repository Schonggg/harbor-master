import argparse

from harbormaster.graph.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--email-id", default="demo-email")
    parser.add_argument("--degrade", action="store_true")
    args = parser.parse_args()
    print(run_pipeline(args.email_id))


if __name__ == "__main__":
    main()
