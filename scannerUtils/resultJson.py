import json
import os


def load_tickets():
    if not os.path.exists('scanned_tickets.json'):
        save_tickets([])
        return []
    try:
        with open('scanned_tickets.json', 'r') as file:
            return json.load(file)
    except json.JSONDecodeError:
        return []


def save_tickets(tickets):
    with open('scanned_tickets.json', 'w') as file:
        json.dump(tickets, file, indent=4)
