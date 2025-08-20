import re


def extract_serial_number(data: str):
    match = re.search(r'SNo:\s*(\d+)', data)
    if match:
        return int(match.group(1))
    return None
