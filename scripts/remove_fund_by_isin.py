import json
import sys


def remove_funds_by_isin(file_path: str, isins) -> None:
    """
    Removes fund entries from funds_database.json by their ISIN(s).
    Prints the result to STDOUT.
    """
    isins = set(isins)
    if not isins:
        print("Error: No ISINs provided.")
        sys.exit(1)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        funds = data.get("funds_database", [])
        original_count = len(funds)

        # Remove funds whose ISIN is in the requested set
        data["funds_database"] = [
            fund for fund in funds if fund.get("isin") not in isins
        ]
        new_count = len(data["funds_database"])

        # Update metadata
        if "metadata" in data:
            data["metadata"]["total_funds_in_db"] = new_count
            data["metadata"]["total_funds_shown"] = new_count
            data["metadata"]["last_updated"] = "2026-06-10"  # Update to today

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        removed = original_count - new_count
        print(f"Removed {removed} fund(s) for {len(isins)} requested ISIN(s).")
        if removed == 0:
            print("No matching funds found.")

    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: File '{file_path}' is not valid JSON.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def collect_isins(args) -> list:
    """
    Collects ISINs from CLI args. If no args are given, or a single '-' is
    given, reads ISINs from STDIN (whitespace/newline separated).
    """
    if not args or args == ["-"]:
        return sys.stdin.read().split()
    return args


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python remove_fund_by_isin.py <path_to_funds_database.json> [ISIN ...]\n"
            "       If no ISIN is given (or '-'), ISINs are read from STDIN."
        )
        sys.exit(1)

    file_path = sys.argv[1]
    isins = collect_isins(sys.argv[2:])
    remove_funds_by_isin(file_path, isins)
