import os
from clickup_client import ClickUpClient

client = ClickUpClient()
t = client.get_task("86afkmify")
print("PARENT TASK FETCHED:", "YES" if t else "NO")

# Lets try to see what its subtasks look like
if t:
    print("PARENT NAME:", t.get("name"))
    print("PARENT HAS PARENT:", t.get("parent"))
