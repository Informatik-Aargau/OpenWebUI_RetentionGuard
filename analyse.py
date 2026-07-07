import csv
import json


def load_user_counts_csv(filename: str = "user_counts.csv") -> dict[str, int]:
    """
    Load user counts from a semicolon-delimited CSV file.
    
    Args:
        filename: Path to the CSV file
        
    Returns:
        Dictionary mapping email to count
    """
    user_counts = {}
    
    try:
        with open(filename, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile, delimiter=';')
            for row in reader:
                email = row['email']
                count = int(row['count'])
                user_counts[email] = count
        
        return user_counts
    except FileNotFoundError:
        print(f"Error: File {filename} not found")
        return {}
    except Exception as e:
        print(f"Error loading CSV: {str(e)}")
        return {}


def main():
    # Load user counts from CSV
    user_counts = load_user_counts_csv()
    
    # Filter emails with count = 0
    zero_count_emails = {email: count for email, count in user_counts.items() if count == 0}
    
    # Dump dictionary to standard output
    print(json.dumps(zero_count_emails, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
