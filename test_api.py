import sys
import json
from clickup_client import ClickUpClient

client = ClickUpClient()
teams = client.get_teams()
if not teams: sys.exit()
team_id = teams[0]['id']

# Brute force search for any comment with string 'image.png'
spaces = client.get_spaces(team_id)
for space in spaces:
    folders = client.get_folders(space['id'])
    for folder in folders:
        lists = client.get_lists_in_folder(folder['id'])
        for lst in lists:
            tasks = client.get_tasks(lst['id'])
            for t in tasks:
                comms = client.get_task_comments(t['id'])
                for c in comms:
                    if 'image' in str(c).lower() or 'attachments' in c:
                        print(json.dumps(c, indent=2))
                        sys.exit(0)
                        
    lists = client.get_lists_in_space(space['id'])
    for lst in lists:
        tasks = client.get_tasks(lst['id'])
        for t in tasks:
            comms = client.get_task_comments(t['id'])
            for c in comms:
                if 'image' in str(c).lower() or 'attachments' in c:
                    print(json.dumps(c, indent=2))
                    sys.exit(0)
