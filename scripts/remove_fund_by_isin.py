import json
import sys

def remove_fund_by_isin(file_path: str, isin: str) -> None:
    """
    Removes a fund entry from funds_database.json by its ISIN.
    Prints the result to STDOUT.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        funds = data.get("funds_database", [])
        original_count = len(funds)
        
        # Remove the fund with the matching ISIN
        data["funds_database"] = [fund for fund in funds if fund.get("isin") != isin]
        new_count = len(data["funds_database"])

        # Update metadata
        if "metadata" in data:
            data["metadata"]["total_funds_in_db"] = new_count
            data["metadata"]["total_funds_shown"] = new_count
            data["metadata"]["last_updated"] = "2026-06-08"  # Update to today

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        removed = original_count - new_count
        print(f"Removed {removed} fund(s) with ISIN: {isin}")
        if removed == 0:
            print(f"No fund found with ISIN: {isin}")

    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: File '{file_path}' is not valid JSON.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python remove_fund_by_isin.py <path_to_funds_database.json> <ISIN>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    isin = sys.argv[2]
    remove_fund_by_isin(file_path, isin)