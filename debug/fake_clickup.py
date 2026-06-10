class ClickUpClientFake:
    def __init__(self):
        self.headers = {}
    def get_teams(self): return [{"id": "team1", "name": "Team1"}]
    def get_spaces(self, team_id): return [{"id": "space1", "name": "Space1"}]
    def get_folders(self, space_id): return [{"id": "folder1", "name": "Folder1"}]
    def get_lists_in_folder(self, folder_id): return [{"id": "list1", "name": "List1"}]
    def get_lists_in_space(self, space_id): return []
    def get_shared_items(self, team_id): return {}
    def get_tasks(self, list_id, subtasks=True, date_updated_gt=None):
        return [
            {
                "id": "parent1",
                "name": "Parent Task Refazer BI",
                "parent": None,
                "status": {"status": "open", "type": "open"},
                "creator": {"username": "User1"},
                "description": "This is parent task",
                "attachments": [{"url": "http://example.com/a.txt", "name": "parent_att.txt"}],
            },
            {
                "id": "sub1",
                "name": "Subtask 1",
                "parent": "parent1",
                "status": {"status": "open", "type": "open"},
                "creator": {"username": "User1"},
                "description": "This is subtask 1",
                "attachments": [{"url": "http://example.com/b.txt", "name": "sub_att.txt"}],
            }
        ]
    def get_task_comments(self, task_id): return []
    def get_task(self, task_id): return None

import main
main.ClickUpClient = ClickUpClientFake
class FakeDownloader:
    def __init__(self, **kwargs): pass
    def extract_attachments_from_task(self, task): return task.get("attachments", [])
    def extract_attachments_from_comments(self, comments): return []
    def download_attachment(self, url, name, path):
        import os
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, name), "w") as f:
            f.write("fake attachment")
main.AttachmentDownloader = FakeDownloader

import sys
sys.argv = ["main.py", "--mode", "2"]
main.main()
