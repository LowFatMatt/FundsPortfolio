import json
import sys
import csv


def csv_enhance_funds_by_isin(funds_file_path: str, enhancement_file_path: str) -> None:
    """
    Enhances fund entries from funds_database.json looked up by their ISIN(s)
    to enhance their information read from a CSV file.

    For each row in the CSV:
    - Matches the ISIN to find the corresponding fund entry
    - For each column header that matches a key in the fund (case-sensitive)
    - If the CSV value is non-empty, updates the fund's field with that value
    - If the CSV value is empty, leaves the fund's field unchanged

    Prints the result to STDOUT and updates the JSON file in place.
    """

    try:
        with open(funds_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        funds = data.get("funds_database", [])

        # Create a map of ISIN to fund for quick lookup
        isin_to_fund = {fund.get("isin"): fund for fund in funds if fund.get("isin")}

        with open(enhancement_file_path, "r", encoding="utf-8") as f:
            # Use semicolon as delimiter for this CSV
            reader = csv.DictReader(f, delimiter=";")

            updated_count = 0
            for row in reader:
                isin = row.get("isin", "").strip()
                if not isin or isin not in isin_to_fund:
                    continue

                fund = isin_to_fund[isin]
                fields_updated = 0

                # For each column in the CSV row
                for key, value in row.items():
                    # Skip the ISIN column itself
                    if key.lower() == "isin":
                        continue

                    # Only update if the key exists in the fund and the value is non-empty
                    if key in fund and value and value.strip():
                        fund[key] = value.strip()
                        fields_updated += 1

                if fields_updated > 0:
                    updated_count += 1

        # Write the updated data back to the file
        with open(funds_file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"Enhanced {updated_count} fund(s) with data from CSV.")

    except FileNotFoundError as e:
        print(f"Error: File not found - {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: File '{funds_file_path}' is not valid JSON - {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage: python csv_enhance_by_isin.py <path_to_funds_database.json> <path_to_enhancement_data.csv>\n"
        )
        sys.exit(1)

    file_path = sys.argv[1]
    enhancement_file_path = sys.argv[2]
    csv_enhance_funds_by_isin(file_path, enhancement_file_path)
